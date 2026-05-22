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
