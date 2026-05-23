from __future__ import annotations

import json
import queue
import re
import shutil
import socket
import subprocess
import tempfile
import textwrap
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


class _OtelManager:
    """Manages OpenTelemetry SDK resources for the BASIC emulator.

    Initialised lazily on the first OTEL* instruction.  All methods are
    exception-safe: if the SDK is not installed or the collector is
    unreachable the calls are silent no-ops so the BASIC program still runs.

    A single module-level instance is shared across all BasicRuntime objects
    so that spans started by a sub-program (launched via RUNBASIC) are
    correctly nested inside the caller's active context.
    """

    def __init__(self) -> None:
        self._ready = False
        self._tracer: object = None
        self._meter: object = None
        self._otel_logger: object = None
        self._tracer_provider: object = None
        self._meter_provider: object = None
        self._logger_provider: object = None
        self._span_stack: list[object] = []
        self._counters: dict[str, object] = {}

    def _init(self) -> None:
        """Lazily initialise the OTel SDK.  Called once on the first OTEL* use."""
        if self._ready:
            return
        self._ready = True  # mark ready even on failure so we don't retry
        try:
            import time as _time
            from opentelemetry import trace, metrics
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.sdk._logs import LoggerProvider
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
            from opentelemetry._logs import set_logger_provider
            from opentelemetry.sdk.resources import Resource
            import os as _os  # noqa: PLC0415

            # Allow per-container service names for distributed tracing so that
            # coordinator, worker-1, worker-2 etc. show as separate services in Jaeger.
            service_name = _os.environ.get("OTEL_SERVICE_NAME", "hello-bas")
            resource = Resource.create({"service.name": service_name})

            # --- Traces ---
            tracer_provider = TracerProvider(resource=resource)
            tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
            trace.set_tracer_provider(tracer_provider)
            self._tracer = trace.get_tracer("hello-bas")
            self._tracer_provider = tracer_provider

            # --- Metrics ---
            reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(), export_interval_millis=5000
            )
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(meter_provider)
            self._meter = metrics.get_meter("hello-bas")
            self._meter_provider = meter_provider

            # --- Logs ---
            logger_provider = LoggerProvider(resource=resource)
            logger_provider.add_log_record_processor(
                BatchLogRecordProcessor(OTLPLogExporter())
            )
            set_logger_provider(logger_provider)
            self._otel_logger = logger_provider.get_logger("hello-bas")
            self._logger_provider = logger_provider

        except Exception:
            pass  # graceful degradation: OTel SDK not installed or misconfigured

    def start_span(self, name: str) -> None:
        """Start a new trace span nested under the current active span.

        Uses the OTel context API so that each new span is automatically
        a child of the previously started (not-yet-ended) span.  The span
        is attached to the current context so subsequent OTELSPAN calls
        see it as their parent.  The detach token is stored alongside the
        span so end_span can restore the previous context.
        """
        self._init()
        if self._tracer is None:
            self._span_stack.append((None, None))
            return
        try:
            from opentelemetry import trace, context as otel_context
            # start_span uses the current context, so it automatically
            # becomes a child of whatever span is currently active.
            ctx = otel_context.get_current()
            span = self._tracer.start_span(name, context=ctx)  # type: ignore[union-attr]
            # Activate the new span so the next OTELSPAN call nests inside it.
            token = otel_context.attach(trace.set_span_in_context(span))
            self._span_stack.append((span, token))
        except Exception:
            self._span_stack.append((None, None))

    def end_span(self) -> None:
        """End the most recently started span and restore the previous context."""
        if not self._span_stack:
            return
        entry = self._span_stack.pop()
        span, token = entry if isinstance(entry, tuple) else (entry, None)
        if span is not None:
            try:
                span.end()
            except Exception:
                pass
        if token is not None:
            try:
                from opentelemetry import context as otel_context
                otel_context.detach(token)
            except Exception:
                pass

    def log(self, message: str) -> None:
        """Emit an OTel log record at INFO severity."""
        self._init()
        if self._otel_logger is None:
            return
        try:
            import time as _time
            from opentelemetry.sdk._logs import LogRecord
            from opentelemetry._logs import SeverityNumber
            self._otel_logger.emit(
                LogRecord(
                    timestamp=_time.time_ns(),
                    observed_timestamp=_time.time_ns(),
                    trace_id=0,
                    span_id=0,
                    trace_flags=0,
                    severity_text="INFO",
                    severity_number=SeverityNumber.INFO,
                    body=message,
                    resource=None,
                    attributes={},
                )
            )
        except Exception:
            pass

    def count(self, metric_name: str, value: int = 1) -> None:
        """Increment a named counter metric by value (default 1)."""
        self._init()
        if self._meter is None:
            return
        try:
            if metric_name not in self._counters:
                self._counters[metric_name] = self._meter.create_counter(metric_name)  # type: ignore[union-attr]
            self._counters[metric_name].add(value)  # type: ignore[union-attr]
        except Exception:
            pass

    def flush(self) -> bool:
        """Force-flush all pending OTel signal batches.  Returns True on success."""
        self._init()
        try:
            if self._tracer_provider is not None:
                self._tracer_provider.force_flush()  # type: ignore[union-attr]
            if self._meter_provider is not None:
                self._meter_provider.force_flush()  # type: ignore[union-attr]
            if self._logger_provider is not None:
                self._logger_provider.force_flush()  # type: ignore[union-attr]
            return True
        except Exception:
            return False


# Module-level singleton shared by all BasicRuntime instances so that spans
# started inside sub-programs (RUNBASIC) nest correctly under the caller's context.
_OTEL = _OtelManager()


class _HttpServer:
    """Per-port HTTP server factory for BASIC HTTPSERVE / HTTPRESPOND.

    Each port gets its own pair of queues (request_queue, response_queue) so
    that multiple BASIC programs can serve on different ports concurrently.
    The server threads are daemon threads so they exit when the process does.

    BASIC usage pattern (sequential blocking event-loop):
        HTTPSERVE 8080      <- blocks until a request arrives; sets HTTP_VERB$,
                               HTTP_PATH$, HTTP_BODY$ in the calling runtime
        ...process request...
        HTTPRESPOND 200, R$ <- sends the response to the waiting HTTP client
        GOTO previous line  <- loop back to accept next request
    """

    def __init__(self) -> None:
        # RLock allows the same thread to re-acquire (avoids deadlock when
        # _start_server calls helpers that also acquire the lock).
        self._lock = threading.RLock()
        self._servers: dict[int, object] = {}
        self._queues: dict[int, tuple[queue.Queue, queue.Queue]] = {}

    def _get_or_create_queues(self, port: int) -> tuple[queue.Queue, queue.Queue]:
        """Return the (req_q, resp_q) pair for *port*, creating it if needed.

        Caller MUST NOT hold self._lock when calling this method (or must
        hold it reentrant-safely via RLock).
        """
        with self._lock:
            if port not in self._queues:
                self._queues[port] = (queue.Queue(), queue.Queue())
            return self._queues[port]

    def _start_server(self, port: int) -> None:
        """Start a background HTTP server on *port* if not already running."""
        with self._lock:
            if port in self._servers:
                return
            # Queues are created here (inside the lock) without a nested
            # lock acquisition — direct dict access avoids the deadlock.
            if port not in self._queues:
                self._queues[port] = (queue.Queue(), queue.Queue())
            req_q, resp_q = self._queues[port]

        # Build the handler class OUTSIDE the lock so it can capture the
        # queues freely without risking any secondary lock acquisition.
        rq = req_q
        rsq = resp_q

        from http.server import BaseHTTPRequestHandler, HTTPServer  # noqa: PLC0415

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                pass  # silence access log

            def _dispatch(self) -> None:
                length = int(self.headers.get("Content-Length", 0) or 0)
                body = (self.rfile.read(length).decode("utf-8", errors="replace")
                        if length > 0 else "")
                # Extract OTel W3C trace-context so incoming spans link correctly.
                try:
                    from opentelemetry.propagate import extract as _ex  # noqa: PLC0415
                    from opentelemetry import context as _ctx  # noqa: PLC0415
                    _ctx.attach(_ex({k: v for k, v in self.headers.items()}))
                except Exception:
                    pass
                rq.put((self.command, self.path, body))
                status, resp_body = rsq.get()
                resp_bytes = resp_body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(resp_bytes)))
                self.end_headers()
                self.wfile.write(resp_bytes)

            def do_GET(self) -> None: self._dispatch()   # noqa: E301
            def do_POST(self) -> None: self._dispatch()  # noqa: E301
            def do_HEAD(self) -> None: self._dispatch()  # noqa: E301

        server = HTTPServer(("", port), Handler)
        with self._lock:
            # Double-check: another thread might have started the server while
            # we were building the handler class outside the lock.
            if port not in self._servers:
                t = threading.Thread(target=server.serve_forever, daemon=True)
                t.start()
                self._servers[port] = server

    def accept(self, port: int) -> tuple[str, str, str]:
        """Block until an HTTP request arrives on *port*.

        Returns ``(verb, path, body)`` and leaves the response slot open until
        :meth:`respond` is called.
        """
        self._start_server(port)
        req_q, _ = self._get_or_create_queues(port)
        return req_q.get()

    def respond(self, port: int, status: int, body: str) -> None:
        """Send *body* with HTTP *status* to the client waiting on *port*."""
        _, resp_q = self._get_or_create_queues(port)
        resp_q.put((status, body))

    def port_is_listening(self, port: int) -> bool:
        """Return True if *port* has a server accepting connections."""
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return True
        except OSError:
            return False


# Module-level HTTP server singleton — shared so spawned BASIC programs can
# each serve on their own port without interfering with each other.
_HTTP_SERVER = _HttpServer()

# Registry of spawned BasicRuntime instances, keyed by filename, so that
# COVCNT / JCOVCNT can credit their executed lines to the coverage totals.
_SPAWNED: dict[str, "BasicRuntime"] = {}


def _top_level_plus_split(expr: str) -> tuple[str, str] | None:
    """Split *expr* at the first ``+`` that is not inside parentheses or a
    double-quoted string literal.

    Returns ``(left, right)`` (both un-stripped) or ``None`` if no such ``+``
    exists.  This is the correct way to parse the ``+`` operator in BASIC
    expressions because function arguments may themselves contain ``+``
    (e.g. ``INSTR(A$, "x=" + B$)``).
    """
    depth = 0
    in_str = False
    for i, ch in enumerate(expr):
        if ch == '"' and not in_str:
            in_str = True
        elif ch == '"' and in_str:
            in_str = False
        elif not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "+" and depth == 0:
                return expr[:i], expr[i + 1:]
    return None


def _match_func_call(expr: str, name: str) -> str | None:
    """If *expr* is exactly a call to function *name* with balanced parentheses,
    return the argument string (everything between the outer parens).

    Returns ``None`` if the expression is not a complete call to *name* — e.g.
    if there is content after the closing paren, meaning the *expr* is actually
    a subexpression within a larger ``+`` chain (which the caller must handle
    with ``_top_level_plus_split`` first).

    Example:
        _match_func_call('STR$(X%+1)', 'STR$') -> 'X%+1'
        _match_func_call('STR$(X%) + "foo"', 'STR$') -> None  (trailing content)
    """
    prefix = name + "("
    if not expr.startswith(prefix):
        return None
    depth = 0
    in_str = False
    for i in range(len(prefix) - 1, len(expr)):
        ch = expr[i]
        if ch == '"' and not in_str:
            in_str = True
        elif ch == '"' and in_str:
            in_str = False
        elif not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    if i == len(expr) - 1:
                        return expr[len(prefix):i]
                    return None  # trailing content — not a simple call
    return None  # unbalanced parens


def _http_request(method: str, url: str, body: str = "") -> tuple[int, str]:
    """Make a simple HTTP/HTTPS request and return (status_code, response_body).

    Used by the BASIC HTTPPOST and HTTPGET instructions.  Automatically
    injects OTel trace-context propagation headers so distributed traces
    link coordinator spans to worker spans in Jaeger.
    """
    headers: dict[str, str] = {"Content-Type": "application/x-www-form-urlencoded"}
    # Inject W3C traceparent / tracestate so cross-service spans are linked.
    try:
        from opentelemetry.propagate import inject as _inject  # noqa: PLC0415
        _inject(headers)
    except Exception:
        pass
    data = body.encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    # Accept self-signed TLS certificates (used in the CI nginx TLS terminator).
    import ssl  # noqa: PLC0415
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, str(exc)


@dataclass
class BasicProgram:
    lines: dict[int, str]

    @classmethod
    def from_file(cls, path: Path) -> "BasicProgram":
        lines: dict[int, str] = {}
        for raw_line in path.read_text().splitlines():
            if not raw_line.strip():
                continue
            line_no_text, statement = raw_line.strip().split(" ", 1)
            lines[int(line_no_text)] = statement.strip()
        return cls(lines=lines)

    def transpile_to_javascript(self) -> str:
        line_order = sorted(self.lines)
        next_line_map: dict[int, int | None] = {
            line: (line_order[i + 1] if i + 1 < len(line_order) else None)
            for i, line in enumerate(line_order)
        }

        def js_var(name: str) -> str:
            return f'vars[{name!r}]'

        def js_expr(expr: str) -> str:
            expr = expr.strip()
            # String literal: outer quotes with no inner quotes (BASIC has no escape).
            if expr.startswith('"') and expr.endswith('"') and len(expr) >= 2:
                if '"' not in expr[1:-1]:
                    return expr
            if expr.isdigit():
                return expr

            # STR$(expr) — integer to string
            arg = _match_func_call(expr, "STR$")
            if arg is not None:
                return f"String(Number({js_expr(arg.strip())}))"

            # VAL(str$) — string to integer
            arg = _match_func_call(expr, "VAL")
            if arg is not None:
                return f"(parseInt(String({js_expr(arg.strip())})) || 0)"

            # MID$(str$, start%, len%)
            arg = _match_func_call(expr, "MID$")
            if arg is not None:
                parts = [p.strip() for p in arg.split(",", 2)]
                if len(parts) == 3:
                    s, start, length = js_expr(parts[0]), js_expr(parts[1]), js_expr(parts[2])
                    return f"(String({s}).substring(Number({start})-1, Number({start})-1+Number({length})))"

            # INSTR(haystack, needle) — 1-based position or 0
            arg = _match_func_call(expr, "INSTR")
            if arg is not None:
                comma_pos = None
                depth_i, in_str_i = 0, False
                for ci, ch2 in enumerate(arg):
                    if ch2 == '"' and not in_str_i:
                        in_str_i = True
                    elif ch2 == '"' and in_str_i:
                        in_str_i = False
                    elif not in_str_i:
                        if ch2 == "(":
                            depth_i += 1
                        elif ch2 == ")":
                            depth_i -= 1
                        elif ch2 == "," and depth_i == 0:
                            comma_pos = ci
                            break
                if comma_pos is not None:
                    h = js_expr(arg[:comma_pos].strip())
                    n = js_expr(arg[comma_pos + 1:].strip())
                    return f"((String({h}).indexOf(String({n})) + 1))"

            # LEN(var$)
            arg = _match_func_call(expr, "LEN")
            if arg is not None:
                return f"(String({js_var(arg.strip())} ?? '')).length"

            # + operator: use JS string concat when either side is a string type.
            # Use top-level split to avoid splitting inside function args.
            split_res = _top_level_plus_split(expr)
            if split_res is not None:
                left, right = split_res
                lv = js_expr(left)
                rv = js_expr(right)
                if left.strip().endswith("$") or right.strip().endswith("$") \
                        or left.strip().startswith('"') or right.strip().startswith('"'):
                    return f"(String({lv}) + String({rv}))"
                return f"(Number({lv}) + Number({rv}))"

            if expr.endswith("%"):
                return f"({js_var(expr)} ?? 0)"
            if expr.endswith("$"):
                return f"({js_var(expr)} ?? '')"
            return f"({js_var(expr)} ?? null)"

        def js_condition(text: str) -> str:
            if " > " in text:
                left, right = text.split(" > ", 1)
                return f"(Number({js_expr(left)}) > Number({js_expr(right)}))"
            if " = " in text:
                left, right = text.split(" = ", 1)
                return f"({js_expr(left)} === {js_expr(right)})"
            raise RuntimeError(f"unsupported condition for transpilation: {text}")

        def js_next_line(line: int) -> str:
            next_line = next_line_map[line]
            return "null" if next_line is None else str(next_line)

        def js_statement(statement: str, line: int, indent: str = "          ") -> list[str]:
            if statement.startswith("REM "):
                return [
                    f"{indent}// {statement.removeprefix('REM ').strip()}",
                    f"{indent}pc = {js_next_line(line)};",
                ]
            if statement.startswith("ON ERROR GOTO "):
                target = int(statement.removeprefix("ON ERROR GOTO ").strip())
                return [
                    f'{indent}errorHandler = {{ mode: "goto", target: {target} }};',
                    f"{indent}pc = {js_next_line(line)};",
                ]
            if statement.startswith("ON ERROR GOSUB "):
                target = int(statement.removeprefix("ON ERROR GOSUB ").strip())
                return [
                    f'{indent}errorHandler = {{ mode: "gosub", target: {target} }};',
                    f"{indent}pc = {js_next_line(line)};",
                ]
            if statement.startswith("GOSUB "):
                target = int(statement.removeprefix("GOSUB ").strip())
                return [
                    f"{indent}const returnLine_{line} = nextLine(pc);",
                    f"{indent}if (returnLine_{line} === null) throw new Error('GOSUB has no return line');",
                    f"{indent}callStack.push(returnLine_{line});",
                    f"{indent}pc = {target};",
                ]
            if statement.startswith("GOTO "):
                target = int(statement.removeprefix("GOTO ").strip())
                return [f"{indent}pc = {target};"]
            if statement == "RETURN":
                return [
                    f"{indent}if (!callStack.length) throw new Error('RETURN without GOSUB');",
                    f"{indent}pc = callStack.pop();",
                ]
            if statement == "RESUME NEXT":
                return [
                    f"{indent}if (resumeLine === null) throw new Error('RESUME NEXT without active error');",
                    f"{indent}pc = resumeLine;",
                    f"{indent}resumeLine = null;",
                ]
            if statement.startswith("RESUME "):
                target = int(statement.removeprefix("RESUME ").strip())
                return [
                    f"{indent}if (resumeLine === null) throw new Error('RESUME without active error');",
                    f"{indent}pc = {target};",
                    f"{indent}resumeLine = null;",
                ]
            if statement.startswith("PRINT "):
                parts = [part.strip() for part in statement.removeprefix("PRINT ").split(";")]
                rendered = " + ".join(f"String({js_expr(part)})" for part in parts) or '""'
                return [
                    f"{indent}output.push({rendered});",
                    f"{indent}pc = {js_next_line(line)};",
                ]
            if statement.startswith("IF ") and " THEN " in statement:
                condition_text, then_statement = statement[3:].split(" THEN ", 1)
                then_lines = js_statement(then_statement.strip(), line, indent + "  ")
                return [
                    f"{indent}if {js_condition(condition_text.strip())} {{",
                    *then_lines,
                    f"{indent}}} else {{",
                    f"{indent}  pc = {js_next_line(line)};",
                    f"{indent}}}",
                ]
            if "=" in statement:
                name, expr = statement.split("=", 1)
                return [
                    f"{indent}{js_var(name.strip())} = {js_expr(expr.strip())};",
                    f"{indent}pc = {js_next_line(line)};",
                ]
            # OTEL* instructions are no-ops in the transpiled JS path: they emit
            # a comment so the generated code remains readable, then simply advance
            # the program counter.  The JS runtime therefore stays behaviourally
            # equivalent to the BASIC emulator for output and variable assertions.
            if (
                statement.startswith("OTELSPAN ")
                or statement == "OTELEND"
                or statement.startswith("OTELLOG ")
                or statement.startswith("OTELCOUNT ")
                or statement == "OTELFLUSH"
            ):
                return [
                    f"{indent}// otel (no-op in js): {statement}",
                    f"{indent}pc = {js_next_line(line)};",
                ]
            # HTTP/network and SLEEP/SPAWN instructions are no-ops in the
            # transpiled JS path (JS has no BASIC networking runtime).  They
            # emit descriptive comments so the generated source stays readable.
            if (
                statement.startswith("HTTPPOST ")
                or statement.startswith("HTTPGET ")
                or statement.startswith("HTTPSERVE ")
                or statement.startswith("HTTPRESPOND ")
                or statement.startswith("SLEEP ")
                or statement.startswith("SPAWN ")
            ):
                return [
                    f"{indent}// network (no-op in js): {statement}",
                    f"{indent}pc = {js_next_line(line)};",
                ]
            raise RuntimeError(f"unsupported statement for transpilation: {statement}")

        js_lines: list[str] = [
            "function runBasicProgram({",
            "  maxSteps = 100000,",
            "  stopAfterPrints = null,",
            "  startLine = null,",
            "  initialVars = {},",
            "  faultOnceLines = []",
            "} = {}) {",
            "  const vars = Object.assign(Object.create(null), initialVars);",
            "  const output = [];",
            "  const callStack = [];",
            "  const executedLines = new Set();",
            "  const faultOnceSet = new Set(faultOnceLines);",
            "  let errorHandler = null;",
            "  let resumeLine = null;",
            f"  const entryLine = {line_order[0] if line_order else 'null'};",
            "  let pc = startLine === null ? entryLine : startLine;",
            f"  const lineOrder = [{', '.join(str(line) for line in line_order)}];",
            "  const nextLine = (line) => {",
            "    const i = lineOrder.indexOf(line);",
            "    return i >= 0 && i + 1 < lineOrder.length ? lineOrder[i + 1] : null;",
            "  };",
            "  let steps = 0;",
            "  while (lineOrder.includes(pc)) {",
            "    if (steps >= maxSteps) throw new Error('execution exceeded max steps');",
            "    steps += 1;",
            "    const currentLine = pc;",
            "    executedLines.add(currentLine);",
            "    try {",
            "      if (faultOnceSet.has(currentLine)) {",
            "        faultOnceSet.delete(currentLine);",
            "        throw new Error('injected fault');",
            "      }",
            "      switch (pc) {",
        ]

        for line in line_order:
            js_lines.append(f"        case {line}:")
            js_lines.extend(js_statement(self.lines[line], line))
            js_lines.append("          break;")

        js_lines.extend(
            [
                "        default:",
                "          throw new Error(`unknown line ${pc}`);",
                "      }",
                "    } catch (err) {",
                "      if (!errorHandler) throw err;",
                "      if (errorHandler.mode === 'gosub') resumeLine = nextLine(currentLine);",
                "      pc = errorHandler.target;",
                "    }",
                "    if (stopAfterPrints !== null && output.length >= stopAfterPrints) break;",
                "  }",
                "  return { vars, output, pc, executedLines: Array.from(executedLines) };",
                "}",
            ]
        )
        return "\n".join(js_lines)


class BasicRuntime:
    def __init__(
        self,
        program: BasicProgram,
        *,
        initial_vars: dict[str, int | str] | None = None,
        fault_once_lines: set[int] | None = None,
    ) -> None:
        self.program = program
        self.vars: dict[str, int | str] = dict(initial_vars or {})
        self.output: list[str] = []
        self.call_stack: list[int] = []
        self.error_handler_line: int | None = None
        self.error_handler_mode: str | None = None
        self.resume_line: int | None = None
        self.pc: int = min(program.lines)
        self.line_order = sorted(program.lines)
        self.fault_once_lines = set(fault_once_lines or set())
        self.executed_lines: set[int] = set()
        # Coverage stores: accumulated executed lines per filename across RUNBASIC/NODERUN calls.
        self._bas_coverage: dict[str, set[int]] = {}
        self._js_coverage: dict[str, set[int]] = {}
        # Current port being served (set by HTTPSERVE, read by HTTPRESPOND).
        self._current_serve_port: int = 8080

    def run(
        self,
        *,
        max_steps: int = 100000,
        stop_after_prints: int | None = None,
        start_line: int | None = None,
    ) -> list[str]:
        if start_line is not None:
            self.pc = start_line

        steps = 0
        while self.pc in self.program.lines:
            if steps >= max_steps:
                raise RuntimeError("execution exceeded max steps")
            steps += 1

            line = self.pc
            self.executed_lines.add(line)
            statement = self.program.lines[line]
            try:
                if line in self.fault_once_lines:
                    self.fault_once_lines.remove(line)
                    raise RuntimeError("injected fault")
                self._execute_statement(statement)
            except Exception:
                if self.error_handler_line is None:
                    raise
                if self.error_handler_mode == "gosub":
                    self.resume_line = self._next_line(line)
                self.pc = self.error_handler_line

            if stop_after_prints is not None and len(self.output) >= stop_after_prints:
                return self.output
        return self.output

    def _next_line(self, line: int) -> int | None:
        index = self.line_order.index(line)
        if index + 1 >= len(self.line_order):
            return None
        return self.line_order[index + 1]

    def _execute_statement(self, statement: str) -> None:
        if statement.startswith("REM ") or statement == "REM":
            self.pc = self._next_line(self.pc)
            return

        if statement == "END":
            # Halt execution by moving PC to a line that does not exist.
            self.pc = -1
            return

        if statement.startswith("ON ERROR GOTO "):
            self.error_handler_line = int(statement.removeprefix("ON ERROR GOTO ").strip())
            self.error_handler_mode = "goto"
            self.pc = self._next_line(self.pc)
            return

        if statement.startswith("ON ERROR GOSUB "):
            self.error_handler_line = int(statement.removeprefix("ON ERROR GOSUB ").strip())
            self.error_handler_mode = "gosub"
            self.pc = self._next_line(self.pc)
            return

        if statement.startswith("GOSUB "):
            target = int(statement.removeprefix("GOSUB ").strip())
            next_line = self._next_line(self.pc)
            if next_line is None:
                raise RuntimeError("GOSUB has no return line")
            self.call_stack.append(next_line)
            self.pc = target
            return

        if statement.startswith("GOTO "):
            self.pc = int(statement.removeprefix("GOTO ").strip())
            return

        if statement == "RETURN":
            if not self.call_stack:
                raise RuntimeError("RETURN without GOSUB")
            self.pc = self.call_stack.pop()
            return

        if statement == "RESUME NEXT":
            if self.resume_line is None:
                raise RuntimeError("RESUME NEXT without active error")
            self.pc = self.resume_line
            self.resume_line = None
            return

        if statement.startswith("RESUME "):
            self.pc = int(statement.removeprefix("RESUME ").strip())
            return

        if statement.startswith("PRINT "):
            rendered = []
            for part in statement.removeprefix("PRINT ").split(";"):
                rendered.append(str(self._eval_expr(part.strip())))
            self.output.append("".join(rendered))
            self.pc = self._next_line(self.pc)
            return

        if statement.startswith("IF ") and " THEN " in statement:
            condition_text, then_statement = statement[3:].split(" THEN ", 1)
            if self._eval_condition(condition_text.strip()):
                self._execute_statement(then_statement.strip())
            else:
                self.pc = self._next_line(self.pc)
            return

        if "=" in statement:
            name, expr = statement.split("=", 1)
            self.vars[name.strip()] = self._eval_expr(expr.strip())
            self.pc = self._next_line(self.pc)
            return

        # ---- New system instructions used by tests.bas -------------------------

        if statement.startswith('RUNBASIC "') and statement.endswith('"'):
            self._exec_runbasic(statement[len('RUNBASIC "'):-1])
            return

        if statement.startswith('NODERUN "') and statement.endswith('"'):
            self._exec_noderun(statement[len('NODERUN "'):-1])
            return

        if statement.startswith('TRANSPILE "') and statement.endswith('"'):
            self._exec_transpile(statement[len('TRANSPILE "'):-1])
            return

        if statement.startswith('NODECHECK "') and statement.endswith('"'):
            self._exec_nodecheck(statement[len('NODECHECK "'):-1])
            return

        if statement.startswith('COVCNT "') and statement.endswith('"'):
            self._exec_covcnt(statement[len('COVCNT "'):-1])
            return

        if statement.startswith('JCOVCNT "') and statement.endswith('"'):
            self._exec_jcovcnt(statement[len('JCOVCNT "'):-1])
            return

        if statement.startswith('CLRCOV "') and statement.endswith('"'):
            self._bas_coverage.pop(statement[len('CLRCOV "'):-1], None)
            self.pc = self._next_line(self.pc)
            return

        if statement.startswith('CLRJCOV "') and statement.endswith('"'):
            self._js_coverage.pop(statement[len('CLRJCOV "'):-1], None)
            self.pc = self._next_line(self.pc)
            return

        # ---- OpenTelemetry instructions ----------------------------------------
        # These let a BASIC program emit distributed observability signals.
        # All instructions delegate to the module-level _OTEL singleton so that
        # traces/metrics/logs flow through a single SDK provider regardless of
        # how many BasicRuntime objects are active at the same time.

        if statement.startswith('OTELSPAN "') and statement.endswith('"'):
            # Start a new trace span with the given name and push it on the stack.
            _OTEL.start_span(statement[len('OTELSPAN "'):-1])
            self.pc = self._next_line(self.pc)
            return

        if statement == "OTELEND":
            # End the most recently started span (LIFO order).
            _OTEL.end_span()
            self.pc = self._next_line(self.pc)
            return

        if statement.startswith('OTELLOG "') and statement.endswith('"'):
            # Emit an OTel log record at INFO severity with the given message.
            _OTEL.log(statement[len('OTELLOG "'):-1])
            self.pc = self._next_line(self.pc)
            return

        if statement.startswith('OTELCOUNT "') and statement.endswith('"'):
            # Increment the named counter metric by 1.
            _OTEL.count(statement[len('OTELCOUNT "'):-1])
            self.pc = self._next_line(self.pc)
            return

        if statement == "OTELFLUSH":
            # Force-flush all pending OTel export batches.
            # Sets OTEL_OK% = 1 on success, 0 if flush raised an exception.
            self.vars["OTEL_OK%"] = 1 if _OTEL.flush() else 0
            self.pc = self._next_line(self.pc)
            return

        # ---- Distributed networking instructions ----------------------------
        # HTTPPOST url$, body$  — HTTP POST; sets HTTP_STATUS%, HTTP_BODY$
        # HTTPGET  url$         — HTTP GET;  sets HTTP_STATUS%, HTTP_BODY$
        # HTTPSERVE port%       — blocks until a request arrives; sets
        #                         HTTP_VERB$, HTTP_PATH$, HTTP_BODY$
        # HTTPRESPOND code%, body$ — sends the response for the pending request
        # SLEEP ms%             — pause execution for the given milliseconds
        # SPAWN "prog.bas"      — run a BASIC program as a background service;
        #                         reads _SPORT% for the port to wait on

        if statement.startswith("HTTPPOST "):
            rest = statement[len("HTTPPOST "):].strip()
            url_expr, body_expr = rest.split(",", 1)
            url = str(self._eval_expr(url_expr.strip()))
            body = str(self._eval_expr(body_expr.strip()))
            status, response = _http_request("POST", url, body)
            self.vars["HTTP_STATUS%"] = status
            self.vars["HTTP_BODY$"] = response
            self.pc = self._next_line(self.pc)
            return

        if statement.startswith("HTTPGET "):
            url = str(self._eval_expr(statement[len("HTTPGET "):].strip()))
            status, response = _http_request("GET", url)
            self.vars["HTTP_STATUS%"] = status
            self.vars["HTTP_BODY$"] = response
            self.pc = self._next_line(self.pc)
            return

        if statement.startswith("HTTPSERVE "):
            port = int(self._eval_expr(statement[len("HTTPSERVE "):].strip()))
            self._current_serve_port = port
            verb, path, body = _HTTP_SERVER.accept(port)
            self.vars["HTTP_VERB$"] = verb
            self.vars["HTTP_PATH$"] = path
            self.vars["HTTP_BODY$"] = body
            self.pc = self._next_line(self.pc)
            return

        if statement.startswith("HTTPRESPOND "):
            rest = statement[len("HTTPRESPOND "):].strip()
            code_expr, body_expr = rest.split(",", 1)
            code = int(self._eval_expr(code_expr.strip()))
            body = str(self._eval_expr(body_expr.strip()))
            port = getattr(self, "_current_serve_port", 8080)
            _HTTP_SERVER.respond(port, code, body)
            self.pc = self._next_line(self.pc)
            return

        if statement.startswith("SLEEP "):
            ms = int(self._eval_expr(statement[len("SLEEP "):].strip()))
            time.sleep(ms / 1000.0)
            self.pc = self._next_line(self.pc)
            return

        if statement.startswith('SPAWN "') and statement.endswith('"'):
            self._exec_spawn(statement[len('SPAWN "'):-1])
            return

        raise RuntimeError(f"unsupported statement: {statement}")

    def _eval_condition(self, text: str) -> bool:
        # Check multi-char operators first (longest-match).
        if " <> " in text:
            left, right = text.split(" <> ", 1)
            return self._eval_expr(left.strip()) != self._eval_expr(right.strip())
        if " >= " in text:
            left, right = text.split(" >= ", 1)
            return int(self._eval_expr(left.strip())) >= int(self._eval_expr(right.strip()))
        if " <= " in text:
            left, right = text.split(" <= ", 1)
            return int(self._eval_expr(left.strip())) <= int(self._eval_expr(right.strip()))
        if " > " in text:
            left, right = text.split(" > ", 1)
            return int(self._eval_expr(left.strip())) > int(self._eval_expr(right.strip()))
        if " < " in text:
            left, right = text.split(" < ", 1)
            return int(self._eval_expr(left.strip())) < int(self._eval_expr(right.strip()))
        if " = " in text:
            left, right = text.split(" = ", 1)
            return self._eval_expr(left.strip()) == self._eval_expr(right.strip())
        raise RuntimeError(f"unsupported condition: {text}")

    def _eval_expr(self, expr: str) -> int | str:
        # String literal: starts and ends with " and has no inner " chars
        # (classic BASIC strings have no escape mechanism).
        if expr.startswith('"') and expr.endswith('"') and len(expr) >= 2:
            inner = expr[1:-1]
            if '"' not in inner:
                return inner
        if expr.isdigit():
            return int(expr)

        # ---- Standard BASIC string functions (minimal additions) -------------
        # These are checked BEFORE the + operator so that function arguments
        # that themselves contain + (e.g. INSTR(A$, "x=" + B$)) are parsed
        # correctly rather than split at the inner +.
        # _match_func_call ensures we only match a COMPLETE call (no trailing
        # content), so STR$(X%) in "STR$(X%) + Y$" is NOT matched here —
        # instead it falls through to _top_level_plus_split.

        # STR$(expr) — convert integer to its decimal string
        arg = _match_func_call(expr, "STR$")
        if arg is not None:
            return str(int(self._eval_expr(arg.strip())))

        # VAL(str$) — convert leading digits of string to integer
        arg = _match_func_call(expr, "VAL")
        if arg is not None:
            raw = str(self._eval_expr(arg.strip())).lstrip()
            m = re.match(r"^-?\d+", raw)
            return int(m.group()) if m else 0

        # MID$(str$, start%, len%) — n chars at 1-based position
        arg = _match_func_call(expr, "MID$")
        if arg is not None:
            # Split arg on commas at the top level of the MID$ call.
            parts = [p.strip() for p in arg.split(",", 2)]
            if len(parts) == 3:
                s = str(self._eval_expr(parts[0]))
                start = max(0, int(self._eval_expr(parts[1])) - 1)
                length = int(self._eval_expr(parts[2]))
                return s[start: start + length]

        # LEN(var$)
        arg = _match_func_call(expr, "LEN")
        if arg is not None:
            return len(str(self.vars.get(arg.strip(), "")))

        # INSTR(haystack$, needle$) — 1-based position, 0 if not found
        arg = _match_func_call(expr, "INSTR")
        if arg is not None:
            # Split on the first comma at the top level of the INSTR args.
            split = _top_level_plus_split(arg.replace(",", "+", 1))
            # Use a dedicated top-level-comma split instead.
            comma_pos = None
            depth2, in_str2 = 0, False
            for ci, ch2 in enumerate(arg):
                if ch2 == '"' and not in_str2:
                    in_str2 = True
                elif ch2 == '"' and in_str2:
                    in_str2 = False
                elif not in_str2:
                    if ch2 == "(":
                        depth2 += 1
                    elif ch2 == ")":
                        depth2 -= 1
                    elif ch2 == "," and depth2 == 0:
                        comma_pos = ci
                        break
            if comma_pos is not None:
                haystack = str(self._eval_expr(arg[:comma_pos].strip()))
                needle = str(self._eval_expr(arg[comma_pos + 1:].strip()))
                pos = haystack.find(needle)
                return (pos + 1) if pos >= 0 else 0

        # ---- + operator: arithmetic or string concatenation ----------------
        # Split only at a top-level + so nested function args are preserved.
        spl = _top_level_plus_split(expr)
        if spl is not None:
            left, right = spl
            lv = self._eval_expr(left.strip())
            rv = self._eval_expr(right.strip())
            if isinstance(lv, str) or isinstance(rv, str):
                return str(lv) + str(rv)
            return int(lv) + int(rv)

        if expr in self.vars:
            return self.vars[expr]
        if expr.endswith("%"):
            return 0
        if expr.endswith("$"):
            return ""
        raise RuntimeError(f"unsupported expression: {expr}")

    # ---- Helper methods for the new system instructions -----------------------

    def _get_run_params(self) -> tuple[int | None, int | None, set[int], dict[str, int | str]]:
        """Read the shared run-parameter variables set by the calling BASIC program.

        Convention (all prefixed with underscore to avoid clashing with BASIC
        program variables):
          _START%  - first line to execute (0 = use the program's own first line)
          _STOPS%  - stop after this many PRINT statements (0 = run to completion)
          _FAULT%  - inject a one-time fault at this line number (0 = none)
          _SETV%   - 1 = seed initial variables from _IMSG$ and _IITER%; 0 = don't
          _IMSG$   - initial value for MESSAGE$  (only used when _SETV% = 1)
          _IITER%  - initial value for ITERATION% (only used when _SETV% = 1)
        """
        start = int(self.vars.get("_START%", 0)) or None
        stops = int(self.vars.get("_STOPS%", 0)) or None
        fault = int(self.vars.get("_FAULT%", 0))
        set_vars = int(self.vars.get("_SETV%", 0))
        initial_vars: dict[str, int | str] = {}
        if set_vars:
            initial_vars["MESSAGE$"] = self.vars.get("_IMSG$", "")
            initial_vars["ITERATION%"] = int(self.vars.get("_IITER%", 0))
        fault_once = {fault} if fault else set()
        return start, stops, fault_once, initial_vars

    def _exec_runbasic(self, filename: str) -> None:
        """Run another BASIC program and store results in B_* variables.

        Reads run parameters from _START%, _STOPS%, _FAULT%, _SETV%, _IMSG$,
        _IITER% (see _get_run_params).  After execution:
          B_N%          - number of output lines produced
          B_1$ .. B_9$  - individual output lines (empty string if fewer than 9)
          B_MSG$        - final value of MESSAGE$ in the sub-program
          B_ITER%       - final value of ITERATION% in the sub-program
        Also accumulates executed line numbers into self._bas_coverage[filename].
        """
        start, stops, fault_once, initial_vars = self._get_run_params()
        prog = BasicProgram.from_file(Path(filename))
        rt = BasicRuntime(prog, initial_vars=initial_vars, fault_once_lines=fault_once)
        rt.run(max_steps=100000, stop_after_prints=stops, start_line=start)
        self.vars["B_N%"] = len(rt.output)
        for i in range(9):
            self.vars[f"B_{i + 1}$"] = rt.output[i] if i < len(rt.output) else ""
        self.vars["B_MSG$"] = rt.vars.get("MESSAGE$", "")
        self.vars["B_ITER%"] = int(rt.vars.get("ITERATION%", 0))
        self._bas_coverage.setdefault(filename, set()).update(rt.executed_lines)
        self.pc = self._next_line(self.pc)

    def _exec_noderun(self, filename: str) -> None:
        """Transpile a BASIC program to JS and run it, storing results in J_* variables.

        Uses the same _* run parameters as _exec_runbasic.  After execution:
          J_N%          - number of output lines produced
          J_1$ .. J_9$  - individual output lines
          J_MSG$        - final value of MESSAGE$
          J_ITER%       - final value of ITERATION%
        Also accumulates executed line numbers into self._js_coverage[filename].
        """
        start, stops, fault_once, initial_vars = self._get_run_params()
        prog = BasicProgram.from_file(Path(filename))
        js = prog.transpile_to_javascript()
        harness = textwrap.dedent(
            """
            const options = JSON.parse(process.argv[2]);
            const result = runBasicProgram(options);
            console.log(JSON.stringify(result));
            """
        )
        options = {
            "maxSteps": 100000,
            "stopAfterPrints": stops,
            "startLine": start,
            "initialVars": initial_vars,
            "faultOnceLines": sorted(fault_once),
        }
        node = shutil.which("node")
        if not node:
            raise RuntimeError("node is required to run transpiled JavaScript")
        with tempfile.TemporaryDirectory() as tmp:
            js_path = Path(tmp) / "run.js"
            js_path.write_text(js + "\n" + harness)
            try:
                completed = subprocess.run(
                    [node, str(js_path), json.dumps(options)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(exc.stderr.strip() or str(exc)) from exc
        data = json.loads(completed.stdout)
        output = data["output"]
        self.vars["J_N%"] = len(output)
        for i in range(9):
            self.vars[f"J_{i + 1}$"] = output[i] if i < len(output) else ""
        self.vars["J_MSG$"] = data["vars"].get("MESSAGE$", "")
        self.vars["J_ITER%"] = int(data["vars"].get("ITERATION%", 0))
        executed = {int(ln) for ln in data["executedLines"]}
        self._js_coverage.setdefault(filename, set()).update(executed)
        self.pc = self._next_line(self.pc)

    def _exec_transpile(self, filename: str) -> None:
        """Transpile a BASIC program to JavaScript and store the source in T_JS$."""
        prog = BasicProgram.from_file(Path(filename))
        self.vars["T_JS$"] = prog.transpile_to_javascript()
        self.pc = self._next_line(self.pc)

    def _exec_nodecheck(self, filename: str) -> None:
        """Transpile a BASIC program and syntax-check the JS with node --check.

        Sets T_OK% = 1 if the generated JS is syntactically valid, 0 otherwise.
        """
        prog = BasicProgram.from_file(Path(filename))
        js = prog.transpile_to_javascript()
        node = shutil.which("node")
        if not node:
            self.vars["T_OK%"] = 0
            self.pc = self._next_line(self.pc)
            return
        with tempfile.TemporaryDirectory() as tmp:
            js_path = Path(tmp) / "check.js"
            js_path.write_text(js)
            result = subprocess.run([node, "--check", str(js_path)], capture_output=True)
        self.vars["T_OK%"] = 1 if result.returncode == 0 else 0
        self.pc = self._next_line(self.pc)

    def _exec_covcnt(self, filename: str) -> None:
        """Read accumulated BASIC coverage for a file into B_COVC% and B_TOTL%.

        Also includes lines executed by a SPAWN-ed runtime for *filename* so
        that coverage of long-running server programs (e.g. coordinator.bas)
        is visible even though they never exit.
        """
        prog = BasicProgram.from_file(Path(filename))
        covered = set(self._bas_coverage.get(filename, set()))
        if filename in _SPAWNED:
            covered.update(_SPAWNED[filename].executed_lines)
        self.vars["B_COVC%"] = len(covered)
        self.vars["B_TOTL%"] = len(prog.lines)
        self.pc = self._next_line(self.pc)

    def _exec_jcovcnt(self, filename: str) -> None:
        """Read accumulated JS coverage for a file into J_COVC% and J_TOTL%."""
        prog = BasicProgram.from_file(Path(filename))
        covered = self._js_coverage.get(filename, set())
        self.vars["J_COVC%"] = len(covered)
        self.vars["J_TOTL%"] = len(prog.lines)
        self.pc = self._next_line(self.pc)

    def _exec_spawn(self, filename: str) -> None:
        """Start a BASIC program as a background daemon service.

        The program runs in a daemon thread (exits when the process does) and
        accumulates line coverage in the module-level _SPAWNED registry so
        COVCNT can report it.

        _SPORT% (read from the calling program's variables) specifies a TCP
        port to wait on before returning.  If _SPORT% = 0 (or absent) the
        instruction returns immediately after starting the thread.
        """
        prog = BasicProgram.from_file(Path(filename))
        rt = BasicRuntime(prog)
        _SPAWNED[filename] = rt

        def _run() -> None:
            try:
                rt.run(max_steps=50_000_000)
            except Exception:
                pass  # background service exit is silent

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        # Optionally wait until the specified port is accepting connections.
        port = int(self.vars.get("_SPORT%", 0))
        if port > 0:
            deadline = time.time() + 10.0
            while time.time() < deadline:
                if _HTTP_SERVER.port_is_listening(port):
                    break
                time.sleep(0.05)

        self.pc = self._next_line(self.pc)

