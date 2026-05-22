# hallucinate

Single-program, enterprise-grade BASIC infinite loop:

```basic
10 REM STRUCTURED ENTERPRISE HELLO WORLD LOOP (DIJKSTRA-INSPIRED, NO GOTO)
20 ON ERROR GOSUB 1900
30 GOSUB 1000
40 GOSUB 3000
50 GOSUB 40
1000 MESSAGE$ = "HELLO WORLD"
1010 ITERATION% = 0
1020 RETURN
1900 MESSAGE$ = "HELLO WORLD"
1910 RESUME NEXT
2000 GOSUB 2100
2010 GOSUB 2200
2020 GOSUB 2300
2030 RETURN
2100 IF LEN(MESSAGE$) = 0 THEN MESSAGE$ = "HELLO WORLD"
2110 RETURN
2200 PRINT ITERATION%; " "; MESSAGE$
2210 RETURN
2300 ITERATION% = ITERATION% + 1
2310 IF ITERATION% > 9999 THEN ITERATION% = 0
2320 RETURN
3000 GOSUB 2000
3010 RETURN
```

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