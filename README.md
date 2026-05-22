# hallucinate

Single-program, enterprise-grade BASIC infinite loop:

```basic
10 REM STRUCTURED ENTERPRISE HELLO WORLD LOOP (DIJKSTRA-INSPIRED, NO GOTO)
20 ON ERROR GOSUB 1900
30 GOSUB 1000
40 GOSUB 3000
50 GOSUB 40
1000 REM INITIALIZE PROGRAM STATE
1010 MESSAGE$ = "HELLO WORLD"
1020 ITERATION% = 0
1030 RETURN
1900 REM RECOVER MESSAGE AFTER RUNTIME ERROR
1910 MESSAGE$ = "HELLO WORLD"
1920 RESUME NEXT
2000 REM EXECUTE ONE LOOP ITERATION
2010 GOSUB 2100
2020 GOSUB 2200
2030 GOSUB 2300
2040 RETURN
2100 REM GUARD MESSAGE INVARIANT
2110 IF LEN(MESSAGE$) = 0 THEN MESSAGE$ = "HELLO WORLD"
2120 RETURN
2200 REM PRINT CURRENT ITERATION
2210 PRINT ITERATION%; " "; MESSAGE$
2220 RETURN
2300 REM ADVANCE AND WRAP ITERATION COUNTER
2310 ITERATION% = ITERATION% + 1
2320 IF ITERATION% > 9999 THEN ITERATION% = 0
2330 RETURN
3000 REM LOOP DRIVER (STRUCTURED, NO GOTO)
3010 GOSUB 2000
3020 RETURN
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