10  REM ================================================================
20  REM  COORDINATOR.BAS - DISTRIBUTED HELLO WORLD COORDINATOR
30  REM
40  REM  Implements a single-threaded, blocking HTTP event-loop server
50  REM  in pure BASIC.  Transport (HTTPSERVE / HTTPRESPOND) is provided
60  REM  by the emulator; all protocol logic lives here.
70  REM
80  REM  Responsibilities
90  REM  ----------------
100 REM  * Bearer-token authentication on every request
110 REM  * Worker registration and tracking
120 REM  * Work-item distribution (pull-based message queue)
130 REM  * ACID two-phase commit (2PC) coordination:
140 REM      Phase 1 - PREPARE: coordinator votes yes/no
150 REM      Phase 2 - COMMIT / ABORT: finalises the transaction
160 REM  * OpenTelemetry tracing, metrics and logs on all paths
170 REM
180 REM  Protocol (all bodies are key=value pairs joined by &)
190 REM  -----------------------------------------------------
200 REM  POST /register  token=<t>&worker=<id>
210 REM  GET  /work      token=<t>&worker=<id>   (in query string)
220 REM  POST /prepare   token=<t>&worker=<id>&tid=<n>&prints=<n>
230 REM  POST /commit    token=<t>&worker=<id>&tid=<n>&prints=<n>
240 REM  POST /abort     token=<t>&worker=<id>&tid=<n>
250 REM  * any other path -> 404
260 REM  * bad / missing token    -> 401
270 REM ================================================================
280 REM
290 REM  INITIALISE STATE VARIABLES
300 REM  --------------------------
310 SECRET$       = "BASIC-SECRET"
320 PORT%         = 8080
330 WORKER_CNT%   = 0
340 TID%          = 0
350 TOTAL_PRINTS% = 0
360 PHASE_STATE%  = 0
370 PHASE_TID%    = 0
380 PHASE_WORKER$ = ""
390 REM
400 REM  EMIT STARTUP TELEMETRY
410 OTELSPAN "coordinator-startup"
420 OTELLOG "COORDINATOR STARTED"
430 OTELCOUNT "coordinator.starts"
440 OTELEND
450 REM
460 REM  MAIN REQUEST-HANDLER LOOP
470 REM  One GOSUB per iteration handles exactly one HTTP request.
480 REM  GOTO loops back to repeat — the only GOTO in the program,
490 REM  used here as a structured infinite loop-driver (cf. hello.bas).
500 GOSUB 1000
510 GOTO 500
1000 REM ================================================================
1010 REM  SUBROUTINE: HANDLE ONE HTTP REQUEST  (GOSUB 1000)
1020 REM  Blocks at HTTPSERVE until a request arrives, then dispatches.
1030 REM ================================================================
1040 HTTPSERVE PORT%
1050 RCODE% = 200
1060 RESPONSE$ = "ok=1"
1070 OTELSPAN "coordinator-request"
1080 OTELCOUNT "coordinator.requests"
1090 GOSUB 2000
1100 IF AUTH_OK% = 0 THEN RCODE% = 401
1110 IF AUTH_OK% = 0 THEN RESPONSE$ = "ok=0&error=UNAUTHORIZED"
1120 IF AUTH_OK% = 1 THEN GOSUB 2500
1130 OTELEND
1140 HTTPRESPOND RCODE%, RESPONSE$
1150 RETURN
2000 REM ================================================================
2010 REM  SUBROUTINE: AUTHENTICATE REQUEST  (GOSUB 2000)
2020 REM  Sets AUTH_OK%=1 when the shared secret appears in the request
2030 REM  body OR in the URL path (for GET requests whose params are in
2040 REM  the query string rather than a body).
2050 REM ================================================================
2060 AUTH_OK% = 0
2070 IF INSTR(HTTP_BODY$, "token=" + SECRET$) > 0 THEN AUTH_OK% = 1
2080 IF INSTR(HTTP_PATH$, "token=" + SECRET$) > 0 THEN AUTH_OK% = 1
2090 RETURN
2500 REM ================================================================
2510 REM  SUBROUTINE: ROUTE REQUEST TO HANDLER  (GOSUB 2500)
2520 REM  Matches HTTP_PATH$ against known routes and delegates.
2530 REM  Unknown paths receive a 404 response.
2540 REM ================================================================
2550 ROUTE$ = ""
2560 IF INSTR(HTTP_PATH$, "register") > 0 THEN ROUTE$ = "register"
2570 IF INSTR(HTTP_PATH$, "/work")     > 0 THEN ROUTE$ = "work"
2580 IF INSTR(HTTP_PATH$, "prepare")   > 0 THEN ROUTE$ = "prepare"
2590 IF INSTR(HTTP_PATH$, "commit")    > 0 THEN ROUTE$ = "commit"
2600 IF INSTR(HTTP_PATH$, "abort")     > 0 THEN ROUTE$ = "abort"
2610 IF ROUTE$ = "register" THEN GOSUB 3000
2620 IF ROUTE$ = "work"     THEN GOSUB 4000
2630 IF ROUTE$ = "prepare"  THEN GOSUB 5000
2640 IF ROUTE$ = "commit"   THEN GOSUB 6000
2650 IF ROUTE$ = "abort"    THEN GOSUB 7000
2660 IF ROUTE$ = "" THEN RCODE% = 404
2670 IF ROUTE$ = "" THEN RESPONSE$ = "ok=0&error=NOT_FOUND"
2680 RETURN
3000 REM ================================================================
3010 REM  SUBROUTINE: HANDLE POST /register  (GOSUB 3000)
3020 REM  Registers a new worker and returns the current TID seed.
3030 REM ================================================================
3040 WORKER_CNT% = WORKER_CNT% + 1
3050 TID% = TID% + 1
3060 OTELLOG "WORKER REGISTERED"
3070 OTELCOUNT "coordinator.workers"
3080 RESPONSE$ = "ok=1&workers=" + STR$(WORKER_CNT%) + "&tid_seed=" + STR$(TID%)
3090 RETURN
4000 REM ================================================================
4010 REM  SUBROUTINE: HANDLE GET /work  (GOSUB 4000)
4020 REM  Issues a new work ticket (TID + iteration count) to the caller.
4030 REM ================================================================
4040 TID% = TID% + 1
4050 OTELLOG "WORK ASSIGNED"
4060 OTELCOUNT "coordinator.work_items"
4070 RESPONSE$ = "ok=1&tid=" + STR$(TID%) + "&count=5"
4080 RETURN
5000 REM ================================================================
5010 REM  SUBROUTINE: HANDLE POST /prepare  (GOSUB 5000)
5020 REM  2PC Phase 1: coordinator records the prepare and votes commit.
5030 REM ================================================================
5040 PHASE_TID%    = TID%
5050 PHASE_STATE%  = 1
5060 P%            = INSTR(HTTP_BODY$, "worker=") + 7
5070 PHASE_WORKER$ = MID$(HTTP_BODY$, P%, 10)
5080 OTELLOG "2PC PREPARE RECEIVED"
5090 OTELCOUNT "coordinator.2pc.prepares"
5100 RESPONSE$ = "ok=1&vote=commit"
5110 RETURN
6000 REM ================================================================
6010 REM  SUBROUTINE: HANDLE POST /commit  (GOSUB 6000)
6020 REM  2PC Phase 2 - commit: accumulates the worker's print count
6030 REM  into the cluster total and clears the in-flight phase state.
6040 REM ================================================================
6050 P%            = INSTR(HTTP_BODY$, "prints=") + 7
6060 PRINTS_STR$   = MID$(HTTP_BODY$, P%, 6)
6070 TOTAL_PRINTS% = TOTAL_PRINTS% + VAL(PRINTS_STR$)
6080 PHASE_STATE%  = 0
6090 OTELLOG "2PC COMMIT COMPLETE"
6100 OTELCOUNT "coordinator.2pc.commits"
6110 RESPONSE$ = "ok=1&total=" + STR$(TOTAL_PRINTS%)
6120 RETURN
7000 REM ================================================================
7010 REM  SUBROUTINE: HANDLE POST /abort  (GOSUB 7000)
7020 REM  2PC Phase 2 - abort: resets in-flight state; no prints counted.
7030 REM ================================================================
7040 PHASE_STATE% = 0
7050 OTELLOG "2PC ABORT"
7060 OTELCOUNT "coordinator.2pc.aborts"
7070 RESPONSE$ = "ok=1"
7080 RETURN
