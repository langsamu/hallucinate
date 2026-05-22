import json
import os
import shutil
import subprocess
import tempfile
import textwrap
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

    recovery_runtime = BasicRuntime(program, fault_once_lines={2100})
    recovery_runtime.run(stop_after_prints=1)
    covered.update(recovery_runtime.executed_lines)

    all_lines = sorted(program.lines)
    missing = [line for line in all_lines if line not in covered]
    total = len(all_lines)
    percent = 100.0 if total == 0 else (len(covered) * 100.0 / total)
    return len(covered), total, percent, missing


def hello_bas_transpiled_javascript() -> str:
    program = BasicProgram.from_file(HELLO_BAS)
    return program.transpile_to_javascript()


def _node_executable() -> str:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node is required to validate transpiled JavaScript")
    return node


def assert_hello_bas_transpiled_javascript_compiles() -> None:
    transpiled = hello_bas_transpiled_javascript()
    node = _node_executable()
    with tempfile.TemporaryDirectory() as temp_dir:
        js_path = Path(temp_dir) / "hello_transpiled.js"
        js_path.write_text(transpiled)
        subprocess.run(
            [node, "--check", str(js_path)],
            check=True,
            capture_output=True,
            text=True,
        )


def run_hello_program_transpiled_js(
    *,
    max_steps: int = 100000,
    stop_after_prints: int | None = None,
    start_line: int | None = None,
    initial_vars: dict[str, int | str] | None = None,
    fault_once_lines: set[int] | None = None,
) -> dict[str, object]:
    transpiled = hello_bas_transpiled_javascript()
    harness = textwrap.dedent(
        """
        const source = process.env.TRANSPILED_SOURCE || "";
        const options = JSON.parse(process.argv[1]);
        eval(source + "\\n;globalThis.__runBasicProgram = runBasicProgram;");
        const result = globalThis.__runBasicProgram(options);
        console.log(JSON.stringify(result));
        """
    )
    options = {
        "maxSteps": max_steps,
        "stopAfterPrints": stop_after_prints,
        "startLine": start_line,
        "initialVars": initial_vars or {},
        "faultOnceLines": sorted(fault_once_lines or set()),
    }
    try:
        completed = subprocess.run(
            [_node_executable(), "-e", harness, json.dumps(options)],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "TRANSPILED_SOURCE": transpiled},
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.stderr.strip() or exc.stdout.strip() or str(exc)) from exc
    return json.loads(completed.stdout)


def hello_bas_transpiled_js_line_coverage() -> tuple[int, int, float, list[int]]:
    program = BasicProgram.from_file(HELLO_BAS)
    covered: set[int] = set()

    loop = run_hello_program_transpiled_js(stop_after_prints=2)
    covered.update(int(line) for line in loop["executedLines"])

    recovery = run_hello_program_transpiled_js(fault_once_lines={2100}, stop_after_prints=1)
    covered.update(int(line) for line in recovery["executedLines"])

    all_lines = sorted(program.lines)
    missing = [line for line in all_lines if line not in covered]
    total = len(all_lines)
    percent = 100.0 if total == 0 else (len(covered) * 100.0 / total)
    return len(covered), total, percent, missing
