10  REM =========================================================
20  REM  TESTS.BAS - ENTERPRISE TEST SUITE FOR HELLO.BAS
30  REM
40  REM  Runs inside the BASIC emulator, which provides special
50  REM  instructions (RUNBASIC, NODERUN, TRANSPILE, NODECHECK,
60  REM  COVCNT, JCOVCNT, CLRCOV, CLRJCOV, OTELSPAN, OTELEND,
65  REM  OTELLOG, OTELCOUNT, OTELFLUSH, SPAWNBASIC, WAITSPAWNED)
70  REM  that let BASIC code drive all testing, coverage,
75  REM  JS-equivalence checks, and OpenTelemetry observability
76  REM  verification.  SPAWNBASIC launches a BASIC worker in a
77  REM  parallel thread (non-blocking); WAITSPAWNED joins all
78  REM  spawned threads and merges their coverage data.
80  REM
90  REM  Classic BASIC idioms used throughout:
100 REM    - Line numbers in multiples of 10
110 REM    - GOSUB / RETURN for all subroutines
120 REM    - Variables in UPPERCASE with type suffixes (% int, $ string)
130 REM    - REM comments before every logical section
140 REM    - GOTO only inside subroutines for conditional branching
150 REM =========================================================
160 REM
170 REM  SHARED INPUT VARIABLES FOR RUNBASIC / NODERUN:
180 REM    _START%  - first line to execute (0 = program default)
190 REM    _STOPS%  - stop after this many PRINTs (0 = run to end)
200 REM    _FAULT%  - inject a one-time fault at this line (0 = none)
210 REM    _SETV%   - 1 = use _IMSG$ / _IITER% as initial variables
220 REM    _IMSG$   - initial MESSAGE$  (when _SETV% = 1)
230 REM    _IITER%  - initial ITERATION% (when _SETV% = 1)
240 REM
250 REM  OUTPUT VARIABLES SET BY RUNBASIC:
260 REM    B_N%          - number of output lines produced
270 REM    B_1$ .. B_9$  - individual output lines
280 REM    B_MSG$        - final MESSAGE$  in the sub-program
290 REM    B_ITER%       - final ITERATION% in the sub-program
300 REM
310 REM  OUTPUT VARIABLES SET BY NODERUN:
320 REM    J_N%          - number of output lines
330 REM    J_1$ .. J_9$  - individual output lines
340 REM    J_MSG$        - final MESSAGE$
350 REM    J_ITER%       - final ITERATION%
360 REM
370 REM  ASSERTION SUBROUTINES:
380 REM    GOSUB 90000   - Assert two strings equal (ASSERT_A$, ASSERT_B$)
390 REM    GOSUB 91000   - Assert two integers equal (ASSERT_I%, ASSERT_J%)
400 REM    Set ASSERT_NAME$ before calling either subroutine.
410 REM =========================================================

420 REM --- INITIALISE GLOBAL TEST COUNTERS ---
430 PASS_CNT% = 0
440 FAIL_CNT% = 0
450 BCOV_OK% = 0
460 JCOV_OK% = 0

470 REM --- PRINT BANNER ---
480 PRINT "=========================================="
490 PRINT "ENTERPRISE HELLO.BAS TEST SUITE"
500 PRINT "=========================================="

54 REM --- DISPATCH: RUN ALL TEST CASES (T1-T10 original, T11-T19 distributed, T20-T21 performance) ---
520 GOSUB 1000
530 GOSUB 2000
540 GOSUB 3000
550 GOSUB 4000
560 GOSUB 5000
570 GOSUB 6000
580 GOSUB 7000
590 GOSUB 8000
600 GOSUB 10000
605 GOSUB 15000
606 GOSUB 20000

610 REM --- DISPLAY TRANSPILED JS SOURCE AND PROGRAM OUTPUTS FOR CI ---
620 GOSUB 11000
630 GOSUB 11200
640 GOSUB 11400
645 GOSUB 11600

650 REM --- PRINT COVERAGE REPORT ---
660 GOSUB 12000

670 REM --- PRINT FINAL SUMMARY AND SET _EXIT_CODE% ---
680 GOSUB 13000
690 END
720 REM  SUBROUTINE: RESET RUNBASIC / NODERUN PARAMETERS  (GOSUB 800)
730 REM  Sets every shared input variable to its inactive default.
740 REM  Call this at the start of every test for clean isolation.
750 REM =========================================================
800 _START% = 0
810 _STOPS% = 0
820 _FAULT% = 0
830 _SETV% = 0
840 _IMSG$ = ""
850 _IITER% = 0
860 RETURN

1000 REM =========================================================
1010 REM  TEST 1: EMULATOR RUNS LOOP AND PRINTS INCREMENTING OUTPUT
1020 REM  Runs hello.bas from the beginning, stops after 3 PRINT
1030 REM  statements, and verifies the output sequence starts at
1040 REM  iteration 0 and increments by 1 on each loop cycle.
1050 REM =========================================================
1060 GOSUB 800
1070 _STOPS% = 3
1080 RUNBASIC "hello.bas"
1090 ASSERT_A$ = B_1$
1100 ASSERT_B$ = "0 HELLO WORLD"
1110 ASSERT_NAME$ = "T1: FIRST OUTPUT IS 0 HELLO WORLD"
1120 GOSUB 90000
1130 ASSERT_A$ = B_2$
1140 ASSERT_B$ = "1 HELLO WORLD"
1150 ASSERT_NAME$ = "T1: SECOND OUTPUT IS 1 HELLO WORLD"
1160 GOSUB 90000
1170 ASSERT_A$ = B_3$
1180 ASSERT_B$ = "2 HELLO WORLD"
1190 ASSERT_NAME$ = "T1: THIRD OUTPUT IS 2 HELLO WORLD"
1200 GOSUB 90000
1210 RETURN

2000 REM =========================================================
2010 REM  TEST 2: GUARD SUBROUTINE RESTORES AN EMPTY MESSAGE$
2020 REM  Starts execution at line 40 (skipping initialisation) with
2030 REM  MESSAGE$ deliberately set to an empty string.  Verifies
2040 REM  that the guard at line 2110 restores MESSAGE$ to HELLO WORLD
2050 REM  before printing, so output is "7 HELLO WORLD".
2060 REM =========================================================
2070 GOSUB 800
2080 _START% = 40
2090 _STOPS% = 1
2100 _SETV% = 1
2110 _IMSG$ = ""
2120 _IITER% = 7
2130 RUNBASIC "hello.bas"
2140 ASSERT_A$ = B_1$
2150 ASSERT_B$ = "7 HELLO WORLD"
2160 ASSERT_NAME$ = "T2: GUARD OUTPUTS 7 HELLO WORLD"
2170 GOSUB 90000
2180 ASSERT_A$ = B_MSG$
2190 ASSERT_B$ = "HELLO WORLD"
2200 ASSERT_NAME$ = "T2: GUARD RESTORES MESSAGE$"
2210 GOSUB 90000
2220 RETURN

3000 REM =========================================================
3010 REM  TEST 3: ITERATION COUNTER WRAPS AROUND AFTER 9999
3020 REM  Starts at line 40 with ITERATION% at 9999, stops after
3030 REM  2 prints.  Verifies that after printing 9999, the advance
3040 REM  subroutine resets the counter to 0 rather than going to 10000.
3050 REM =========================================================
3060 GOSUB 800
3070 _START% = 40
3080 _STOPS% = 2
3090 _SETV% = 1
3100 _IMSG$ = "HELLO WORLD"
3110 _IITER% = 9999
3120 RUNBASIC "hello.bas"
3130 ASSERT_A$ = B_1$
3140 ASSERT_B$ = "9999 HELLO WORLD"
3150 ASSERT_NAME$ = "T3: FIRST OUTPUT AT ITERATION 9999"
3160 GOSUB 90000
3170 ASSERT_A$ = B_2$
3180 ASSERT_B$ = "0 HELLO WORLD"
3190 ASSERT_NAME$ = "T3: SECOND OUTPUT WRAPS TO ITERATION 0"
3200 GOSUB 90000
3210 RETURN

4000 REM =========================================================
4010 REM  TEST 4: ERROR HANDLER RECOVERS FROM A RUNTIME FAULT
4020 REM  Injects a one-time fault at line 2100 (the GUARD entry).
4030 REM  Verifies that ON ERROR GOSUB 1900 fires, the recovery
4040 REM  subroutine restores MESSAGE$, and the loop still produces
4050 REM  one line of correct output.
4060 REM =========================================================
4070 GOSUB 800
4080 _FAULT% = 2100
4090 _STOPS% = 1
4100 RUNBASIC "hello.bas"
4110 ASSERT_A$ = B_1$
4120 ASSERT_B$ = "0 HELLO WORLD"
4130 ASSERT_NAME$ = "T4: RECOVERY PRODUCES 0 HELLO WORLD"
4140 GOSUB 90000
4150 ASSERT_A$ = B_MSG$
4160 ASSERT_B$ = "HELLO WORLD"
4170 ASSERT_NAME$ = "T4: RECOVERY RESTORES MESSAGE$"
4180 GOSUB 90000
4190 RETURN

5000 REM =========================================================
5010 REM  TEST 5: HELLO.BAS HAS 100% BASIC EMULATOR LINE COVERAGE
5020 REM  Clears the coverage accumulator, then runs two scenarios
5030 REM  whose combined executed lines cover all 30 program lines:
5040 REM    Scenario A (normal run, 2 prints):
5050 REM      Covers 10-50, 1000-1030, 2000-2330, 3000-3020
5060 REM    Scenario B (fault at line 2100, 1 print):
5070 REM      Covers error-recovery lines 1900, 1910, 1920
5080 REM  Asserts that accumulated covered count equals total lines.
5090 REM  Sets BCOV_OK% = 1 so the summary can gate the exit code.
5100 REM =========================================================
5110 CLRCOV "hello.bas"
5120 REM --- SCENARIO A: NORMAL EXECUTION ---
5130 GOSUB 800
5140 _STOPS% = 2
5150 RUNBASIC "hello.bas"
5160 REM --- SCENARIO B: FAULT INJECTION AT GUARD ENTRY ---
5170 GOSUB 800
5180 _FAULT% = 2100
5190 _STOPS% = 1
5200 RUNBASIC "hello.bas"
5210 REM --- READ ACCUMULATED COVERAGE AND ASSERT 100% ---
5220 COVCNT "hello.bas"
5230 BCOV_OK% = 0
5240 IF B_COVC% = B_TOTL% THEN BCOV_OK% = 1
5250 ASSERT_I% = B_COVC%
5260 ASSERT_J% = B_TOTL%
5270 ASSERT_NAME$ = "T5: BASIC EMULATOR COVERAGE IS 100%"
5280 GOSUB 91000
5290 RETURN

6000 REM =========================================================
6010 REM  TEST 6: EMULATOR TRANSPILES HELLO.BAS TO JAVASCRIPT
6020 REM  Calls TRANSPILE which produces a JS function mirroring the
6030 REM  BASIC program.  Verifies the output contains expected
6040 REM  structural elements: the function signature, switch cases
6050 REM  for BASIC line numbers, coverage tracking, and the
6060 REM  error-handler setup targeting the recovery subroutine.
6070 REM =========================================================
6080 TRANSPILE "hello.bas"
6090 REM --- ASSERT: Main function signature is present ---
6095 ASSERT_I% = 0
6100 IF INSTR(T_JS$, "function runBasicProgram") > 0 THEN ASSERT_I% = 1
6110 ASSERT_J% = 1
6120 ASSERT_NAME$ = "T6: JS HAS runBasicProgram FUNCTION"
6130 GOSUB 91000
6140 REM --- ASSERT: Switch case for first BASIC line exists ---
6145 ASSERT_I% = 0
6150 IF INSTR(T_JS$, "case 10:") > 0 THEN ASSERT_I% = 1
6160 ASSERT_J% = 1
6170 ASSERT_NAME$ = "T6: JS HAS CASE FOR LINE 10"
6180 GOSUB 91000
6190 REM --- ASSERT: Switch case for PRINT line exists ---
6195 ASSERT_I% = 0
6200 IF INSTR(T_JS$, "case 2210:") > 0 THEN ASSERT_I% = 1
6210 ASSERT_J% = 1
6220 ASSERT_NAME$ = "T6: JS HAS CASE FOR LINE 2210"
6230 GOSUB 91000
6240 REM --- ASSERT: Line-coverage tracking variable is present ---
6245 ASSERT_I% = 0
6250 IF INSTR(T_JS$, "executedLines") > 0 THEN ASSERT_I% = 1
6260 ASSERT_J% = 1
6270 ASSERT_NAME$ = "T6: JS HAS executedLines TRACKING"
6280 GOSUB 91000
6290 REM --- ASSERT: Error handler targets the recovery subroutine ---
6295 ASSERT_I% = 0
6300 IF INSTR(T_JS$, "target: 1900") > 0 THEN ASSERT_I% = 1
6310 ASSERT_J% = 1
6320 ASSERT_NAME$ = "T6: JS ERROR HANDLER TARGETS LINE 1900"
6330 GOSUB 91000
6340 RETURN

7000 REM =========================================================
7010 REM  TEST 7: TRANSPILED JAVASCRIPT IS SYNTACTICALLY VALID
7020 REM  Runs Node.js with the --check flag against the transpiled
7030 REM  output.  This verifies the transpiler produces real
7040 REM  JavaScript syntax, not just non-empty text.
7050 REM =========================================================
7060 NODECHECK "hello.bas"
7070 ASSERT_I% = T_OK%
7080 ASSERT_J% = 1
7090 ASSERT_NAME$ = "T7: TRANSPILED JS IS SYNTACTICALLY VALID"
7100 GOSUB 91000
7110 RETURN

8000 REM =========================================================
8010 REM  TEST 8: TRANSPILED JS RUNTIME IS SEMANTICALLY EQUIVALENT
8020 REM  Runs four scenarios through BOTH the BASIC emulator and
8030 REM  the transpiled JavaScript program.  For each scenario,
8040 REM  asserts that the output lines, final MESSAGE$, and final
8050 REM  ITERATION% are identical, validating semantic equivalence.
8060 REM =========================================================
8070 GOSUB 8200
8080 GOSUB 8600
8090 GOSUB 9100
8100 GOSUB 9500
8110 RETURN

8200 REM --- TEST 8, SCENARIO 1: NORMAL 3-PRINT LOOP ---
8210 REM  Default start, no fault, stop after 3 prints.
8220 GOSUB 800
8230 _STOPS% = 3
8240 RUNBASIC "hello.bas"
8250 BAS_1$ = B_1$
8260 BAS_2$ = B_2$
8270 BAS_3$ = B_3$
8280 BAS_MSG$ = B_MSG$
8290 BAS_ITER% = B_ITER%
8300 NODERUN "hello.bas"
8310 ASSERT_A$ = J_1$
8320 ASSERT_B$ = BAS_1$
8330 ASSERT_NAME$ = "T8 SC1: JS OUTPUT LINE 1 MATCHES BASIC"
8340 GOSUB 90000
8350 ASSERT_A$ = J_2$
8360 ASSERT_B$ = BAS_2$
8370 ASSERT_NAME$ = "T8 SC1: JS OUTPUT LINE 2 MATCHES BASIC"
8380 GOSUB 90000
8390 ASSERT_A$ = J_3$
8400 ASSERT_B$ = BAS_3$
8410 ASSERT_NAME$ = "T8 SC1: JS OUTPUT LINE 3 MATCHES BASIC"
8420 GOSUB 90000
8430 ASSERT_A$ = J_MSG$
8440 ASSERT_B$ = BAS_MSG$
8450 ASSERT_NAME$ = "T8 SC1: JS MESSAGE$ MATCHES BASIC"
8460 GOSUB 90000
8470 ASSERT_I% = J_ITER%
8480 ASSERT_J% = BAS_ITER%
8490 ASSERT_NAME$ = "T8 SC1: JS ITERATION% MATCHES BASIC"
8500 GOSUB 91000
8510 RETURN

8600 REM --- TEST 8, SCENARIO 2: GUARD WITH EMPTY MESSAGE$ ---
8610 REM  Start at line 40, MESSAGE$="", ITERATION%=7, stop after 1 print.
8620 GOSUB 800
8630 _START% = 40
8640 _STOPS% = 1
8650 _SETV% = 1
8660 _IMSG$ = ""
8670 _IITER% = 7
8680 RUNBASIC "hello.bas"
8690 BAS_1$ = B_1$
8700 BAS_MSG$ = B_MSG$
8710 BAS_ITER% = B_ITER%
8720 NODERUN "hello.bas"
8730 ASSERT_A$ = J_1$
8740 ASSERT_B$ = BAS_1$
8750 ASSERT_NAME$ = "T8 SC2: JS OUTPUT MATCHES BASIC"
8760 GOSUB 90000
8770 ASSERT_A$ = J_MSG$
8780 ASSERT_B$ = BAS_MSG$
8790 ASSERT_NAME$ = "T8 SC2: JS MESSAGE$ MATCHES BASIC"
8800 GOSUB 90000
8810 ASSERT_I% = J_ITER%
8820 ASSERT_J% = BAS_ITER%
8830 ASSERT_NAME$ = "T8 SC2: JS ITERATION% MATCHES BASIC"
8840 GOSUB 91000
8850 RETURN

9100 REM --- TEST 8, SCENARIO 3: COUNTER WRAPS AFTER 9999 ---
9110 REM  Start at line 40, ITERATION%=9999, stop after 2 prints.
9120 GOSUB 800
9130 _START% = 40
9140 _STOPS% = 2
9150 _SETV% = 1
9160 _IMSG$ = "HELLO WORLD"
9170 _IITER% = 9999
9180 RUNBASIC "hello.bas"
9190 BAS_1$ = B_1$
9200 BAS_2$ = B_2$
9210 BAS_MSG$ = B_MSG$
9220 BAS_ITER% = B_ITER%
9230 NODERUN "hello.bas"
9240 ASSERT_A$ = J_1$
9250 ASSERT_B$ = BAS_1$
9260 ASSERT_NAME$ = "T8 SC3: JS OUTPUT LINE 1 MATCHES BASIC"
9270 GOSUB 90000
9280 ASSERT_A$ = J_2$
9290 ASSERT_B$ = BAS_2$
9300 ASSERT_NAME$ = "T8 SC3: JS OUTPUT LINE 2 MATCHES BASIC"
9310 GOSUB 90000
9320 ASSERT_A$ = J_MSG$
9330 ASSERT_B$ = BAS_MSG$
9340 ASSERT_NAME$ = "T8 SC3: JS MESSAGE$ MATCHES BASIC"
9350 GOSUB 90000
9360 ASSERT_I% = J_ITER%
9370 ASSERT_J% = BAS_ITER%
9380 ASSERT_NAME$ = "T8 SC3: JS ITERATION% MATCHES BASIC"
9390 GOSUB 91000
9400 RETURN

9500 REM --- TEST 8, SCENARIO 4: ERROR RECOVERY ---
9510 REM  Fault at line 2100, stop after 1 print.
9520 GOSUB 800
9530 _FAULT% = 2100
9540 _STOPS% = 1
9550 RUNBASIC "hello.bas"
9560 BAS_1$ = B_1$
9570 BAS_MSG$ = B_MSG$
9580 BAS_ITER% = B_ITER%
9590 NODERUN "hello.bas"
9600 ASSERT_A$ = J_1$
9610 ASSERT_B$ = BAS_1$
9620 ASSERT_NAME$ = "T8 SC4: JS OUTPUT MATCHES BASIC"
9630 GOSUB 90000
9640 ASSERT_A$ = J_MSG$
9650 ASSERT_B$ = BAS_MSG$
9660 ASSERT_NAME$ = "T8 SC4: JS MESSAGE$ MATCHES BASIC"
9670 GOSUB 90000
9680 ASSERT_I% = J_ITER%
9690 ASSERT_J% = BAS_ITER%
9700 ASSERT_NAME$ = "T8 SC4: JS ITERATION% MATCHES BASIC"
9710 GOSUB 91000
9720 RETURN

10000 REM =========================================================
10010 REM  TEST 9: TRANSPILED JS HAS 100% LINE COVERAGE
10020 REM  Mirrors Test 5 but executes via the JS runtime.  The same
10030 REM  two scenarios (normal run + fault injection) together cover
10040 REM  all 30 BASIC lines through the transpiled code path.
10050 REM  Sets JCOV_OK% = 1 so the summary can gate the exit code.
10060 REM =========================================================
10070 CLRJCOV "hello.bas"
10080 REM --- SCENARIO A: NORMAL EXECUTION ---
10090 GOSUB 800
10100 _STOPS% = 2
10110 NODERUN "hello.bas"
10120 REM --- SCENARIO B: FAULT INJECTION AT GUARD ENTRY ---
10130 GOSUB 800
10140 _FAULT% = 2100
10150 _STOPS% = 1
10160 NODERUN "hello.bas"
10170 REM --- READ ACCUMULATED JS COVERAGE AND ASSERT 100% ---
10180 JCOVCNT "hello.bas"
10190 JCOV_OK% = 0
10200 IF J_COVC% = J_TOTL% THEN JCOV_OK% = 1
10210 ASSERT_I% = J_COVC%
10220 ASSERT_J% = J_TOTL%
10230 ASSERT_NAME$ = "T9: TRANSPILED JS COVERAGE IS 100%"
10240 GOSUB 91000
10250 RETURN

11000 REM =========================================================
11010 REM  DISPLAY: PRINT THE TRANSPILED JAVASCRIPT SOURCE CODE
11020 REM  Makes the generated JS visible in CI logs so reviewers
11030 REM  can inspect the transpiler output directly.
11040 REM =========================================================
11050 PRINT "=========================================="
11060 PRINT "HELLO.BAS TRANSPILED TO JAVASCRIPT:"
11070 PRINT "=========================================="
11080 TRANSPILE "hello.bas"
11090 PRINT T_JS$
11100 RETURN

11200 REM =========================================================
11210 REM  DISPLAY: BASIC EMULATOR OUTPUT (FIRST 5 ITERATIONS)
11220 REM  Runs hello.bas for 5 iterations through the BASIC
11230 REM  emulator and prints each output line for direct observation.
11240 REM =========================================================
11250 PRINT "=========================================="
11260 PRINT "HELLO.BAS BASIC EMULATOR OUTPUT (5 ITERATIONS):"
11270 PRINT "=========================================="
11280 GOSUB 800
11290 _STOPS% = 5
11300 RUNBASIC "hello.bas"
11310 PRINT B_1$
11320 PRINT B_2$
11330 PRINT B_3$
11340 PRINT B_4$
11350 PRINT B_5$
11360 RETURN

11400 REM =========================================================
11410 REM  DISPLAY: TRANSPILED JS OUTPUT (FIRST 5 ITERATIONS)
11420 REM  Runs hello.bas for 5 iterations through the transpiled
11430 REM  JavaScript runtime and prints each output line, confirming
11440 REM  the JS program produces the same output as the BASIC one.
11450 REM =========================================================
11460 PRINT "=========================================="
11470 PRINT "HELLO.BAS TRANSPILED JS OUTPUT (5 ITERATIONS):"
11480 PRINT "=========================================="
11490 GOSUB 800
11500 _STOPS% = 5
11510 NODERUN "hello.bas"
11520 PRINT J_1$
11530 PRINT J_2$
11540 PRINT J_3$
11550 PRINT J_4$
11560 PRINT J_5$
11570 RETURN

12000 REM =========================================================
12010 REM  COVERAGE REPORT: PRINT ACCUMULATED LINE COVERAGE STATS
12020 REM  Re-reads the coverage counters accumulated across all test
12030 REM  runs and prints percentages for both execution paths plus
12040 REM  coverage of the distributed coordinator and worker programs.
12050 REM =========================================================
12060 PRINT "=========================================="
12070 PRINT "LINE COVERAGE REPORT:"
12080 PRINT "=========================================="
12090 COVCNT "hello.bas"
12100 PRINT "BASIC emulator: "; B_COVC%; "/"; B_TOTL%; " lines covered (hello.bas)"
12110 JCOVCNT "hello.bas"
12120 PRINT "Transpiled JS:  "; J_COVC%; "/"; J_TOTL%; " lines covered (hello.bas)"
12130 COVCNT "coordinator.bas"
12140 PRINT "Coordinator:    "; B_COVC%; "/"; B_TOTL%; " lines covered (coordinator.bas)"
12150 COVCNT "worker.bas"
12160 PRINT "Worker:         "; B_COVC%; "/"; B_TOTL%; " lines covered (worker.bas)"
12170 RETURN

13000 REM =========================================================
13010 REM  SUMMARY: PRINT FINAL RESULTS AND SET _EXIT_CODE%
13020 REM  Prints pass/fail counts.  Sets _EXIT_CODE% to 0 only when
13030 REM  ALL of the following conditions are satisfied:
13040 REM    1. No test assertions failed  (FAIL_CNT% = 0)
13050 REM    2. BASIC emulator coverage is 100%  (BCOV_OK% = 1)
13060 REM    3. Transpiled JS coverage is 100%   (JCOV_OK% = 1)
13070 REM  Otherwise _EXIT_CODE% is 1 (failure).
13080 REM =========================================================
13090 PRINT "=========================================="
13100 PRINT "TEST RESULTS:"
13110 PRINT "=========================================="
13120 PRINT "PASSED: "; PASS_CNT%
13130 PRINT "FAILED: "; FAIL_CNT%
13140 REM --- DEFAULT TO FAILURE; RETURN EARLY ON ANY UNMET CONDITION ---
13150 _EXIT_CODE% = 1
13160 IF FAIL_CNT% <> 0 THEN RETURN
13170 IF BCOV_OK% <> 1 THEN RETURN
13180 IF JCOV_OK% <> 1 THEN RETURN
13190 REM --- ALL CONDITIONS MET: DECLARE SUCCESS ---
13200 _EXIT_CODE% = 0
13210 PRINT "ALL TESTS PASSED WITH 100% COVERAGE"
13220 RETURN

90000 REM =========================================================
90010 REM  SUBROUTINE: ASSERT STRING EQUAL  (GOSUB 90000)
90020 REM
90030 REM  Tests that two string values are identical.
90040 REM  Before calling, set:
90050 REM    ASSERT_A$    - the actual string value to test
90060 REM    ASSERT_B$    - the expected string value
90070 REM    ASSERT_NAME$ - a short description of the assertion
90080 REM  After returning:
90090 REM    PASS_CNT% incremented by 1 if values are equal
90100 REM    FAIL_CNT% incremented by 1 and details printed if not
90110 REM =========================================================
90120 IF ASSERT_A$ = ASSERT_B$ THEN GOTO 90200
90130 PRINT "FAIL: "; ASSERT_NAME$
90140 PRINT "      EXPECTED=["; ASSERT_B$; "]"
90150 PRINT "      ACTUAL  =["; ASSERT_A$; "]"
90160 FAIL_CNT% = FAIL_CNT% + 1
90170 RETURN
90200 PRINT "PASS: "; ASSERT_NAME$
90210 PASS_CNT% = PASS_CNT% + 1
90220 RETURN

91000 REM =========================================================
91010 REM  SUBROUTINE: ASSERT INTEGER EQUAL  (GOSUB 91000)
91020 REM
91030 REM  Tests that two integer values are identical.
91040 REM  Before calling, set:
91050 REM    ASSERT_I%    - the actual integer value to test
91060 REM    ASSERT_J%    - the expected integer value
91070 REM    ASSERT_NAME$ - a short description of the assertion
91080 REM  After returning:
91090 REM    PASS_CNT% incremented by 1 if values are equal
91100 REM    FAIL_CNT% incremented by 1 and details printed if not
91110 REM =========================================================
91120 IF ASSERT_I% = ASSERT_J% THEN GOTO 91200
91130 PRINT "FAIL: "; ASSERT_NAME$
91140 PRINT "      EXPECTED="; ASSERT_J%
91150 PRINT "      ACTUAL  ="; ASSERT_I%
91160 FAIL_CNT% = FAIL_CNT% + 1
91170 RETURN
91200 PRINT "PASS: "; ASSERT_NAME$
91210 PASS_CNT% = PASS_CNT% + 1
91220 RETURN

11600 REM =========================================================
11610 REM  DISPLAY: OTEL FLUSH STATUS FOR CI
11620 REM  Calls OTELFLUSH to drain any pending export batches so
11630 REM  the collector has received all signals before CI tries
11640 REM  to dump its output.  Prints whether the flush succeeded.
11650 REM =========================================================
11660 OTELFLUSH
11670 IF OTEL_OK% = 1 THEN GOTO 11700
11680 PRINT "OTEL FLUSH: NOT AVAILABLE (SDK not installed or collector unreachable)"
11690 RETURN
11700 PRINT "OTEL FLUSH: OK - signals exported to collector"
11710 RETURN

15000 REM =========================================================
15010 REM  TEST 10: OTELFLUSH COMPLETES WITHOUT ERROR
15020 REM
15030 REM  Runs hello.bas for 3 iterations through the BASIC emulator
15040 REM  so that OTELSPAN, OTELCOUNT, and OTELLOG all fire at least
15050 REM  once (OTELSPAN + OTELEND per iteration, OTELCOUNT per
15060 REM  iteration, OTELLOG on first fault-injected error recovery).
15070 REM  Then calls OTELFLUSH to drain the export batches.
15080 REM  Asserts that OTEL_OK% = 1, which is true whether a live
15090 REM  collector is present or the SDK gracefully drops the data.
15100 REM =========================================================
15110 GOSUB 800
15120 _STOPS% = 3
15130 RUNBASIC "hello.bas"
15140 OTELFLUSH
15150 ASSERT_I% = OTEL_OK%
15160 ASSERT_J% = 1
15170 ASSERT_NAME$ = "T10: OTEL SIGNALS FLUSH WITHOUT ERROR"
15180 GOSUB 91000
15190 RETURN

20000 REM =========================================================
20010 REM  DISTRIBUTED CLUSTER TESTS (T11-T19) AND PERFORMANCE TESTS (T20-T21)
20020 REM
20030 REM  These tests spin up coordinator.bas as a background HTTP
20040 REM  server via SPAWN, then exercise every route and branch
20050 REM  using HTTPPOST / HTTPGET from within BASIC.
20060 REM
20070 REM  Coordinator port: 8081  (avoids clashing with CI services)
20080 REM
20090 REM  Tests cover:
20100 REM    T11 - SPAWN starts coordinator and port becomes ready
20110 REM    T12 - Bad auth token returns 401
20120 REM    T13 - Worker registration succeeds
20130 REM    T14 - Work ticket distribution returns TID and count
20140 REM    T15 - 2PC PREPARE accepted; vote=commit returned
20150 REM    T16 - 2PC COMMIT accepted; total updated
20160 REM    T17 - 2PC ABORT accepted
20170 REM    T18 - Unknown path returns 404
20180 REM    T19 - Full worker.bas integration (end-to-end)
20185 REM    T20 - Performance baseline: 1 worker x PERF_ROUNDS% rounds
20186 REM    T21 - Performance multi-worker: 2 workers x (PERF_ROUNDS%/2) rounds
20187 REM          each — same total work, expected to complete faster than T20
20188 REM          due to horizontal scale-out and parallel hello.bas execution
20190 REM =========================================================
20200 COORD_PORT% = 8080
20210 COORD_BASE$ = "http://localhost:8080"
20220 SECRET$ = "BASIC-SECRET"
20230 BAD_TOK$ = "WRONG-TOKEN"
20240 REM --- SPAWN COORDINATOR (one background instance for all tests) ---
20250 _SPORT% = 8080
20260 SPAWN "coordinator.bas"
20270 GOSUB 21000
20280 GOSUB 22000
20290 GOSUB 23000
20300 GOSUB 24000
20310 GOSUB 25000
20320 GOSUB 26000
20330 GOSUB 27000
20340 GOSUB 28000
20350 GOSUB 29000
20360 GOSUB 30000
20370 RETURN

21000 REM =========================================================
21010 REM  TEST 11: COORDINATOR STARTS AND ACCEPTS CONNECTIONS
21020 REM =========================================================
21030 PRINT "=========================================="
21040 PRINT "T11: COORDINATOR STARTUP"
21050 PRINT "=========================================="
21060 REM --- Ping via a register request; if coordinator is up we get a response ---
21070 PING_BODY$ = "token=" + SECRET$ + "&worker=PING"
21080 HTTPPOST COORD_BASE$ + "/register", PING_BODY$
21090 ASSERT_I% = HTTP_STATUS%
21100 ASSERT_J% = 200
21110 ASSERT_NAME$ = "T11: COORDINATOR RETURNS HTTP 200"
21120 GOSUB 91000
21130 ASSERT_I% = 0
21131 IF INSTR(HTTP_BODY$, "ok=1") > 0 THEN ASSERT_I% = 1
21140 ASSERT_J% = 1
21150 ASSERT_NAME$ = "T11: COORDINATOR RESPONSE CONTAINS ok=1"
21160 GOSUB 91000
21170 RETURN

22000 REM =========================================================
22010 REM  TEST 12: BAD AUTH TOKEN RETURNS 401 UNAUTHORIZED
22020 REM =========================================================
22030 PRINT "=========================================="
22040 PRINT "T12: AUTH REJECTION"
22050 PRINT "=========================================="
22060 BAD_BODY$ = "token=" + BAD_TOK$ + "&worker=EVIL"
22070 HTTPPOST COORD_BASE$ + "/register", BAD_BODY$
22080 ASSERT_I% = HTTP_STATUS%
22090 ASSERT_J% = 401
22100 ASSERT_NAME$ = "T12: BAD TOKEN GIVES 401"
22110 GOSUB 91000
22120 ASSERT_I% = 0
22121 IF INSTR(HTTP_BODY$, "UNAUTHORIZED") > 0 THEN ASSERT_I% = 1
22130 ASSERT_J% = 1
22140 ASSERT_NAME$ = "T12: ERROR BODY SAYS UNAUTHORIZED"
22150 GOSUB 91000
22160 RETURN

23000 REM =========================================================
23010 REM  TEST 13: WORKER REGISTRATION
23020 REM =========================================================
23030 PRINT "=========================================="
23040 PRINT "T13: WORKER REGISTRATION"
23050 PRINT "=========================================="
23060 REG_BODY$ = "token=" + SECRET$ + "&worker=W1"
23070 HTTPPOST COORD_BASE$ + "/register", REG_BODY$
23080 ASSERT_I% = HTTP_STATUS%
23090 ASSERT_J% = 200
23100 ASSERT_NAME$ = "T13: REGISTRATION RETURNS 200"
23110 GOSUB 91000
23120 ASSERT_I% = 0
23121 IF INSTR(HTTP_BODY$, "workers=") > 0 THEN ASSERT_I% = 1
23130 ASSERT_J% = 1
23140 ASSERT_NAME$ = "T13: RESPONSE INCLUDES WORKER COUNT"
23150 GOSUB 91000
23160 RETURN

24000 REM =========================================================
24010 REM  TEST 14: WORK TICKET DISTRIBUTION
24020 REM =========================================================
24030 PRINT "=========================================="
24040 PRINT "T14: WORK TICKET"
24050 PRINT "=========================================="
24060 WORK_URL$ = COORD_BASE$ + "/work?token=" + SECRET$ + "&worker=W1"
24070 HTTPGET WORK_URL$
24080 ASSERT_I% = HTTP_STATUS%
24090 ASSERT_J% = 200
24100 ASSERT_NAME$ = "T14: WORK RETURNS 200"
24110 GOSUB 91000
24120 ASSERT_I% = 0
24121 IF INSTR(HTTP_BODY$, "tid=") > 0 THEN ASSERT_I% = 1
24130 ASSERT_J% = 1
24140 ASSERT_NAME$ = "T14: WORK RESPONSE HAS TID"
24150 GOSUB 91000
24160 ASSERT_I% = 0
24161 IF INSTR(HTTP_BODY$, "count=") > 0 THEN ASSERT_I% = 1
24170 ASSERT_J% = 1
24180 ASSERT_NAME$ = "T14: WORK RESPONSE HAS COUNT"
24190 GOSUB 91000
24200 REM --- Extract TID for use in subsequent 2PC tests ---
24210 P% = INSTR(HTTP_BODY$, "tid=") + 4
24220 LAST_TID% = VAL(MID$(HTTP_BODY$, P%, 6))
24230 RETURN

25000 REM =========================================================
25010 REM  TEST 15: 2PC PHASE 1 - PREPARE
25020 REM =========================================================
25030 PRINT "=========================================="
25040 PRINT "T15: 2PC PREPARE"
25050 PRINT "=========================================="
25060 PREP_BODY$ = "token=" + SECRET$ + "&worker=W1"
25070 PREP_BODY$ = PREP_BODY$ + "&tid=" + STR$(LAST_TID%)
25080 PREP_BODY$ = PREP_BODY$ + "&prints=5"
25090 HTTPPOST COORD_BASE$ + "/prepare", PREP_BODY$
25100 ASSERT_I% = HTTP_STATUS%
25110 ASSERT_J% = 200
25120 ASSERT_NAME$ = "T15: PREPARE RETURNS 200"
25130 GOSUB 91000
25140 ASSERT_I% = 0
25141 IF INSTR(HTTP_BODY$, "vote=commit") > 0 THEN ASSERT_I% = 1
25150 ASSERT_J% = 1
25160 ASSERT_NAME$ = "T15: COORDINATOR VOTES COMMIT"
25170 GOSUB 91000
25180 RETURN

26000 REM =========================================================
26010 REM  TEST 16: 2PC PHASE 2 - COMMIT
26020 REM =========================================================
26030 PRINT "=========================================="
26040 PRINT "T16: 2PC COMMIT"
26050 PRINT "=========================================="
26060 COMM_BODY$ = "token=" + SECRET$ + "&worker=W1"
26070 COMM_BODY$ = COMM_BODY$ + "&tid=" + STR$(LAST_TID%)
26080 COMM_BODY$ = COMM_BODY$ + "&prints=5"
26090 HTTPPOST COORD_BASE$ + "/commit", COMM_BODY$
26100 ASSERT_I% = HTTP_STATUS%
26110 ASSERT_J% = 200
26120 ASSERT_NAME$ = "T16: COMMIT RETURNS 200"
26130 GOSUB 91000
26140 ASSERT_I% = 0
26141 IF INSTR(HTTP_BODY$, "total=") > 0 THEN ASSERT_I% = 1
26150 ASSERT_J% = 1
26160 ASSERT_NAME$ = "T16: COMMIT RESPONSE HAS TOTAL"
26170 GOSUB 91000
26180 RETURN

27000 REM =========================================================
27010 REM  TEST 17: 2PC PHASE 2 - ABORT
27020 REM =========================================================
27030 PRINT "=========================================="
27040 PRINT "T17: 2PC ABORT"
27050 PRINT "=========================================="
27060 REM --- Get a fresh ticket first so we have a TID to abort ---
27070 WORK_URL$ = COORD_BASE$ + "/work?token=" + SECRET$ + "&worker=W1"
27080 HTTPGET WORK_URL$
27090 P% = INSTR(HTTP_BODY$, "tid=") + 4
27100 ABORT_TID% = VAL(MID$(HTTP_BODY$, P%, 6))
27110 ABRT_BODY$ = "token=" + SECRET$ + "&worker=W1&tid=" + STR$(ABORT_TID%)
27120 HTTPPOST COORD_BASE$ + "/abort", ABRT_BODY$
27130 ASSERT_I% = HTTP_STATUS%
27140 ASSERT_J% = 200
27150 ASSERT_NAME$ = "T17: ABORT RETURNS 200"
27160 GOSUB 91000
27170 ASSERT_I% = 0
27171 IF INSTR(HTTP_BODY$, "ok=1") > 0 THEN ASSERT_I% = 1
27180 ASSERT_J% = 1
27190 ASSERT_NAME$ = "T17: ABORT RESPONSE IS ok=1"
27200 GOSUB 91000
27210 RETURN

28000 REM =========================================================
28010 REM  TEST 18: UNKNOWN PATH RETURNS 404 NOT FOUND
28020 REM =========================================================
28030 PRINT "=========================================="
28040 PRINT "T18: UNKNOWN PATH 404"
28050 PRINT "=========================================="
28060 UNK_BODY$ = "token=" + SECRET$ + "&x=1"
28070 HTTPPOST COORD_BASE$ + "/unknown-route", UNK_BODY$
28080 ASSERT_I% = HTTP_STATUS%
28090 ASSERT_J% = 404
28100 ASSERT_NAME$ = "T18: UNKNOWN PATH GIVES 404"
28110 GOSUB 91000
28120 ASSERT_I% = 0
28121 IF INSTR(HTTP_BODY$, "NOT_FOUND") > 0 THEN ASSERT_I% = 1
28130 ASSERT_J% = 1
28140 ASSERT_NAME$ = "T18: BODY SAYS NOT_FOUND"
28150 GOSUB 91000
28160 RETURN

29000 REM =========================================================
29010 REM  TEST 19: FULL WORKER.BAS INTEGRATION (END-TO-END DISTRIBUTED)
29020 REM  Runs TWO workers (W1 and W2) IN PARALLEL against the coordinator
29030 REM  to demonstrate the distributed trace: each worker independently
29040 REM  picks up work tickets and runs hello.bas concurrently, so the
29050 REM  Jaeger trace shows both workers interleaved under the coordinator's
29060 REM  "hello-world-transaction" root span.  Use SPAWNBASIC (non-blocking)
29065 REM  followed by WAITSPAWNED to achieve true concurrent execution.
29066 REM
29067 REM  Trace blueprint (2 workers x 10 rounds each, non-deterministically interleaved):
29068 REM    hello-world-transaction (coordinator)
29069 REM      worker-round (W1 round 1..10, interleaved with W2) -> hello-world-iteration x5
29071 REM      worker-round (W2 round 1..10, interleaved with W1) -> hello-world-iteration x5
29072 REM  W1 and W2 compete for work tickets concurrently; the order is non-deterministic.
29074 REM =========================================================
29095 PRINT "=========================================="
29096 PRINT "T19: WORKER INTEGRATION (DISTRIBUTED PARALLEL)"
29097 PRINT "=========================================="
29098 GOSUB 800
29099 REM
29100 REM --- Launch worker W1 in a parallel background thread (non-blocking) ---
29110 WORKER_ID$ = "W1"
29120 COORD_URL$ = COORD_BASE$
29130 WORK_ROUNDS% = 10
29140 _STOPS% = 0
29150 SPAWNBASIC "worker.bas"
29160 REM
29170 REM --- Launch worker W2 in a parallel background thread (non-blocking) ---
29180 WORKER_ID$ = "W2"
29190 COORD_URL$ = COORD_BASE$
29200 WORK_ROUNDS% = 10
29210 _STOPS% = 0
29220 SPAWNBASIC "worker.bas"
29230 REM
29235 REM --- Wait for both workers to complete (blocks until all done) ---
29240 WAITSPAWNED
29245 REM
29250 REM --- Verify coordinator still responding after both workers ---
29260 WORK_URL$ = COORD_BASE$ + "/work?token=" + SECRET$ + "&worker=W1"
29270 HTTPGET WORK_URL$
29280 ASSERT_I% = HTTP_STATUS%
29290 ASSERT_J% = 200
29295 ASSERT_NAME$ = "T19: COORDINATOR STILL RESPONDING AFTER PARALLEL WORKER RUN"
29300 GOSUB 91000
29310 RETURN

30000 REM =========================================================
30010 REM  PERFORMANCE TESTS (T20-T21)
30015 REM  Establishes a single-worker baseline (T20), then runs the
30016 REM  same total workload split across two parallel workers (T21)
30017 REM  to demonstrate horizontal scale-out.  All timing spans are
30018 REM  emitted under service "perf-test" so they appear in their
30019 REM  own compact Jaeger trace (not nested in the main transaction).
30020 REM =========================================================
30030 PERF_ROUNDS% = 20
30040 PRINT "=========================================="
30045 PRINT "PERFORMANCE TESTS (T20-T21)"
30050 PRINT "=========================================="
30060 OTELSERVICE "perf-test"
30070 OTELSPANWITH "perf-test-suite", "ROOT"
30080 GOSUB 31000
30090 GOSUB 32000
30100 OTELEND
30110 OTELFLUSH
30120 RETURN

31000 REM =========================================================
31010 REM  TEST 20: PERFORMANCE BASELINE (1 WORKER)
31015 REM  Runs PERF_ROUNDS% complete work rounds on a single worker
31016 REM  and records elapsed wall-clock time into SINGLE_MS%.
31020 REM  TICKMS% returns current time in milliseconds (Unix epoch).
31030 REM =========================================================
31040 PRINT "=========================================="
31050 PRINT "T20: PERFORMANCE BASELINE (1 WORKER)"
31060 PRINT "=========================================="
31070 OTELSPAN "perf-baseline"
31080 START_MS% = TICKMS%
31090 WORKER_ID$ = "W1"
31100 COORD_URL$ = COORD_BASE$
31110 WORK_ROUNDS% = PERF_ROUNDS%
31120 _STOPS% = 0
31130 SPAWNBASIC "worker.bas"
31140 WAITSPAWNED
31150 END_MS% = TICKMS%
31160 SINGLE_MS% = END_MS% - START_MS%
31170 OTELLOG "PERF BASELINE: 1 worker, " + STR$(PERF_ROUNDS%) + " rounds, " + STR$(SINGLE_MS%) + " ms"
31180 OTELEND
31190 PRINT "T20: 1 WORKER x " + STR$(PERF_ROUNDS%) + " ROUNDS = " + STR$(SINGLE_MS%) + " ms"
31200 ASSERT_I% = 0
31205 IF SINGLE_MS% > 0 THEN ASSERT_I% = 1
31210 ASSERT_J% = 1
31220 ASSERT_NAME$ = "T20: PERF BASELINE COMPLETED"
31230 GOSUB 91000
31240 RETURN

32000 REM =========================================================
32010 REM  TEST 21: PERFORMANCE MULTI-WORKER (2 WORKERS IN PARALLEL)
32015 REM  Runs the same total work as T20 but split across two
32016 REM  parallel workers (PERF_ROUNDS% / 2 rounds each).
32017 REM  Both workers are launched via SPAWNBASIC so hello.bas
32018 REM  runs concurrently, demonstrating horizontal scale-out.
32019 REM  Prints speedup relative to the T20 baseline.
32020 REM =========================================================
32030 PRINT "=========================================="
32040 PRINT "T21: PERFORMANCE MULTI-WORKER (2 WORKERS)"
32050 PRINT "=========================================="
32060 HALF_ROUNDS% = 10
32070 OTELSPAN "perf-multi-worker"
32080 START_MS% = TICKMS%
32090 WORKER_ID$ = "W1"
32100 COORD_URL$ = COORD_BASE$
32110 WORK_ROUNDS% = HALF_ROUNDS%
32120 _STOPS% = 0
32130 SPAWNBASIC "worker.bas"
32140 WORKER_ID$ = "W2"
32150 COORD_URL$ = COORD_BASE$
32160 WORK_ROUNDS% = HALF_ROUNDS%
32170 _STOPS% = 0
32180 SPAWNBASIC "worker.bas"
32190 WAITSPAWNED
32200 END_MS% = TICKMS%
32210 MULTI_MS% = END_MS% - START_MS%
32220 OTELLOG "PERF MULTI-WORKER: 2 workers, " + STR$(HALF_ROUNDS%) + " rounds ea, " + STR$(MULTI_MS%) + " ms"
32230 OTELEND
32240 PRINT "T21: 2 WORKERS x " + STR$(HALF_ROUNDS%) + " ROUNDS = " + STR$(MULTI_MS%) + " ms"
32250 PRINT "     SPEEDUP vs BASELINE: " + STR$(SINGLE_MS%) + " ms -> " + STR$(MULTI_MS%) + " ms"
32260 ASSERT_I% = 0
32265 IF MULTI_MS% > 0 THEN ASSERT_I% = 1
32270 ASSERT_J% = 1
32280 ASSERT_NAME$ = "T21: MULTI-WORKER PERF TEST COMPLETED"
32290 GOSUB 91000
32300 RETURN
