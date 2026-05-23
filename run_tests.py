"""Test runner: executes tests.bas through the BASIC emulator.

This file is intentionally minimal.  All test logic, coverage tracking,
transpilation checks, and JS-equivalence validation live in tests.bas.
The emulator (basic_emulator.py) provides the BASIC runtime plus the
extended instructions (RUNBASIC, NODERUN, TRANSPILE, NODECHECK, …) that
the BASIC test suite depends on.
"""

import sys
from pathlib import Path

from basic_emulator import BasicProgram, BasicRuntime


def main() -> int:
    program = BasicProgram.from_file(Path("tests.bas"))
    runtime = BasicRuntime(program)
    runtime.run()
    for line in runtime.output:
        print(line)
    return int(runtime.vars.get("_EXIT_CODE%", 1))


if __name__ == "__main__":
    sys.exit(main())
