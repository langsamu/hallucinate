#!/usr/bin/env python3
"""docker-entrypoint.py — thin launcher for any BASIC program.

Reads the BASIC filename from argv[1] (or the BASIC_PROGRAM env-var),
maps WORKER_ID / COORD_URL / WORK_ROUNDS environment variables into the
initial BASIC variables so the programs are fully configurable from the
container orchestrator without code changes.
"""
import os
import sys
from pathlib import Path

from basic_emulator import BasicProgram, BasicRuntime

def main() -> None:
    filename = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BASIC_PROGRAM", "coordinator.bas")

    # Expose container-level config as initial BASIC variables.
    initial: dict[str, int | str] = {}
    if "WORKER_ID" in os.environ:
        initial["WORKER_ID$"] = os.environ["WORKER_ID"]
    if "COORD_URL" in os.environ:
        initial["COORD_URL$"] = os.environ["COORD_URL"]
    if "WORK_ROUNDS" in os.environ:
        initial["WORK_ROUNDS%"] = int(os.environ.get("WORK_ROUNDS", "3"))

    prog = BasicProgram.from_file(Path(filename))
    rt = BasicRuntime(prog, initial_vars=initial)
    output = rt.run(max_steps=50_000_000)
    for line in output:
        print(line)

if __name__ == "__main__":
    main()
