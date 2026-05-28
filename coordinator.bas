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
385 REM  TXN_TRACEPARENT$ holds the W3C traceparent of the current
386 REM  hello-world-transaction span, shared across all /work requests.
387 REM  Created once on the first worker registration; all workers start
388 REM  their worker-lifecycle spans as cross-service children using it.
390 TXN_TRACEPARENT$ = ""
395 REM
400 REM  IDENTIFY THIS COMPONENT AS THE COORDINATOR SERVICE IN JAEGER
401 REM  (must be before the first OTELSPAN so the startup span is tagged)
402 OTELSERVICE "coordinator"
403 REM
404 REM  EMIT STARTUP TELEMETRY
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
3025 REM
3026 REM  DISTRIBUTED TRACING: on the very first registration, a root
3027 REM  "hello-world-transaction" span is created under the coordinator
3028 REM  service.  Its W3C traceparent is stored in TXN_TRACEPARENT$ and
3029 REM  embedded in the response so workers can start their
3030 REM  "worker-lifecycle" spans as cross-service children, producing a
3031 REM  single distributed trace tree:
3032 REM    hello-world-transaction  (coordinator, colour A)
3033 REM      worker-lifecycle       (worker-W1,   colour B)
3034 REM        worker-register      (worker-W1)
3035 REM        worker-round         (worker-W1)
3036 REM          worker-run-hello   (worker-W1)
3037 REM            hello-world-iteration (hello-bas, colour D)
3038 REM      worker-lifecycle       (worker-W2,   colour C)
3039 REM        ...
3040 REM ================================================================
3050 WORKER_CNT% = WORKER_CNT% + 1
3060 TID% = TID% + 1
3070 OTELLOG "WORKER REGISTERED"
3080 OTELCOUNT "coordinator.workers"
3090 REM --- Create the shared transaction span on the first registration ---
3100 IF TXN_TRACEPARENT$ = "" THEN GOSUB 3500
3110 RESPONSE$ = "ok=1&workers=" + STR$(WORKER_CNT%) + "&tid_seed=" + STR$(TID%) + "&traceparent=" + TXN_TRACEPARENT$
3120 RETURN
3500 REM ================================================================
3510 REM  SUBROUTINE: CREATE HELLO-WORLD-TRANSACTION SPAN  (GOSUB 3500)
3520 REM  Called once on the first worker registration.  Creates a new
3530 REM  root span for the entire distributed hello-world transaction
3540 REM  using the coordinator service, captures its W3C traceparent,
3550 REM  and immediately ends the span so it is exported to Jaeger.
3560 REM  Workers receive the traceparent and start their lifecycle spans
3570 REM  as cross-service children — linking all spans into one trace.
3580 REM ================================================================
3590 OTELSPANWITH "hello-world-transaction", "ROOT"
3600 TXN_TRACEPARENT$ = OTELCONTEXT$
3610 OTELEND
3620 OTELLOG "HELLO-WORLD TRANSACTION STARTED"
3630 RETURN
4000 REM ================================================================
4010 REM  SUBROUTINE: HANDLE GET /work  (GOSUB 4000)
4020 REM  Issues a new work ticket (TID + iteration count) to the caller.
4025 REM  Returns TXN_TRACEPARENT$ so the worker can continue nesting its
4026 REM  spans under the shared hello-world-transaction root.
4030 REM ================================================================
4040 TID% = TID% + 1
4050 OTELLOG "WORK ASSIGNED"
4060 OTELCOUNT "coordinator.work_items"
4070 RESPONSE$ = "ok=1&tid=" + STR$(TID%) + "&count=5&traceparent=" + TXN_TRACEPARENT$
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
