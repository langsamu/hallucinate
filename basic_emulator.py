from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


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
        self.pc: int = min(program.lines)
        self.line_order = sorted(program.lines)
        self.fault_once_lines = set(fault_once_lines or set())

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
            statement = self.program.lines[line]
            try:
                if line in self.fault_once_lines:
                    self.fault_once_lines.remove(line)
                    raise RuntimeError("injected fault")
                self._execute_statement(statement)
            except Exception:
                if self.error_handler_line is None:
                    raise
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
        if statement.startswith("REM "):
            self.pc = self._next_line(self.pc)
            return

        if statement.startswith("ON ERROR GOTO "):
            self.error_handler_line = int(statement.removeprefix("ON ERROR GOTO ").strip())
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

        raise RuntimeError(f"unsupported statement: {statement}")

    def _eval_condition(self, text: str) -> bool:
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
        if expr in self.vars:
            return self.vars[expr]
        if expr.endswith("%"):
            return 0
        if expr.endswith("$"):
            return ""
        raise RuntimeError(f"unsupported expression: {expr}")
