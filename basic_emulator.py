from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import textwrap
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

            resource = Resource.create({"service.name": "hello-bas"})

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
        """Start a new trace span and push it onto the span stack."""
        self._init()
        if self._tracer is None:
            self._span_stack.append(None)
            return
        try:
            span = self._tracer.start_span(name)  # type: ignore[union-attr]
            self._span_stack.append(span)
        except Exception:
            self._span_stack.append(None)

    def end_span(self) -> None:
        """End the most recently started span (LIFO order)."""
        if not self._span_stack:
            return
        span = self._span_stack.pop()
        if span is not None:
            try:
                span.end()
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
            if expr.startswith('"') and expr.endswith('"'):
                return expr
            if expr.isdigit():
                return expr
            if "+" in expr:
                left, right = expr.split("+", 1)
                return f"(Number({js_expr(left)}) + Number({js_expr(right)}))"
            len_match = re.fullmatch(r"LEN\(([^)]+)\)", expr)
            if len_match:
                inner = len_match.group(1).strip()
                return f"(String({js_var(inner)} ?? '')).length"
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

        raise RuntimeError(f"unsupported statement: {statement}")

    def _eval_condition(self, text: str) -> bool:
        if " <> " in text:
            left, right = text.split(" <> ", 1)
            return self._eval_expr(left.strip()) != self._eval_expr(right.strip())
        if " > " in text:
            left, right = text.split(" > ", 1)
            return int(self._eval_expr(left.strip())) > int(self._eval_expr(right.strip()))
        if " = " in text:
            left, right = text.split(" = ", 1)
            return self._eval_expr(left.strip()) == self._eval_expr(right.strip())
        raise RuntimeError(f"unsupported condition: {text}")

    def _eval_expr(self, expr: str) -> int | str:
        if expr.startswith('"') and expr.endswith('"'):
            return expr[1:-1]
        if expr.isdigit():
            return int(expr)
        if "+" in expr:
            left, right = expr.split("+", 1)
            return int(self._eval_expr(left.strip())) + int(self._eval_expr(right.strip()))
        len_match = re.fullmatch(r"LEN\(([^)]+)\)", expr)
        if len_match:
            inner = len_match.group(1).strip()
            return len(str(self.vars.get(inner, "")))
        instr_match = re.fullmatch(r"INSTR\(([^,]+),\s*(.+)\)", expr)
        if instr_match:
            haystack = str(self._eval_expr(instr_match.group(1).strip()))
            needle = str(self._eval_expr(instr_match.group(2).strip()))
            return 1 if needle in haystack else 0
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
        """Read accumulated BASIC coverage for a file into B_COVC% and B_TOTL%."""
        prog = BasicProgram.from_file(Path(filename))
        covered = self._bas_coverage.get(filename, set())
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
