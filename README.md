# hallucinate

Single-program, enterprise-grade BASIC infinite loop:

```basic
10 REM ENTERPRISE-GRADE HELLO WORLD LOOP
20 ON ERROR GOTO 900
30 MESSAGE$ = "HELLO WORLD"
40 ITERATION% = 0
50 GOSUB 200
60 GOTO 50
200 IF LEN(MESSAGE$) = 0 THEN MESSAGE$ = "HELLO WORLD"
210 PRINT ITERATION%; " "; MESSAGE$
220 ITERATION% = ITERATION% + 1
230 IF ITERATION% > 9999 THEN ITERATION% = 0
240 RETURN
900 MESSAGE$ = "HELLO WORLD"
910 RESUME 50
```

Execution-based unit tests are provided via a small BASIC emulator.

- Run locally: `python run_tests.py`
- CI runs the same command in GitHub Actions (`.github/workflows/tests.yml`)