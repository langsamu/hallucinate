from pathlib import Path

from basic_emulator import BasicProgram, BasicRuntime


REPO_ROOT = Path(__file__).resolve().parent
HELLO_BAS = REPO_ROOT / "hello.bas"


def run_hello_program(
    *,
    max_steps: int = 100000,
    stop_after_prints: int | None = None,
    start_line: int | None = None,
    initial_vars: dict[str, int | str] | None = None,
    fault_once_lines: set[int] | None = None,
) -> BasicRuntime:
    program = BasicProgram.from_file(HELLO_BAS)
    runtime = BasicRuntime(
        program,
        initial_vars=initial_vars,
        fault_once_lines=fault_once_lines,
    )
    runtime.run(
        max_steps=max_steps,
        stop_after_prints=stop_after_prints,
        start_line=start_line,
    )
    return runtime


def hello_bas_line_coverage() -> tuple[int, int, float, list[int]]:
    program = BasicProgram.from_file(HELLO_BAS)
    covered: set[int] = set()

    loop_runtime = BasicRuntime(program)
    loop_runtime.run(stop_after_prints=2)
    covered.update(loop_runtime.executed_lines)

    recovery_runtime = BasicRuntime(program, fault_once_lines={2200})
    recovery_runtime.run(stop_after_prints=1)
    covered.update(recovery_runtime.executed_lines)

    all_lines = sorted(program.lines)
    missing = [line for line in all_lines if line not in covered]
    total = len(all_lines)
    percent = 100.0 if total == 0 else (len(covered) * 100.0 / total)
    return len(covered), total, percent, missing
