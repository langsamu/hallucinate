# hallucinate

The single enterprise-grade BASIC program lives in `hello.bas`.
It is not duplicated here to keep the source of truth in one file.

### Dijkstra (1968) review and overhaul plan

- Keep exactly one BASIC file while removing `GOTO`-driven control flow.
- Organize logic into single-purpose subroutines (initialize, recover, validate, print, advance).
- Use recursive subroutine flow for looping and a structured error-recovery path.
- Preserve required behavior: infinite hello loop, guard behavior, counter wrap, and recovery.
- Enforce quality gates: 100% test pass rate and 100% `hello.bas` line coverage in CI.

Execution-based unit tests are provided via a small BASIC emulator.

- Run locally: `python run_tests.py`
- The test runner reports `hello.bas` line coverage and requires 100%.
- CI runs the same command and coverage check in GitHub Actions (`.github/workflows/tests.yml`)