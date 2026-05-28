10  REM ================================================================
20  REM  WORKER.BAS - DISTRIBUTED HELLO WORLD WORKER
30  REM
40  REM  Each worker:
50  REM    1. Sets its OTel service name (OTELSERVICE "worker-<id>")
60  REM    2. Registers with the coordinator (POST /register), which
70  REM       returns the shared hello-world-transaction traceparent
80 REM    3. Loops WORK_ROUNDS% times; each round:
90 REM         a. Starts a "worker-round" span as direct cross-service
100 REM            child of the coordinator's hello-world-transaction root
110 REM         b. Requests a work ticket (GET /work)
120 REM         c. Runs hello.bas for the assigned number of iterations
130 REM         d. Participates in 2PC: PREPARE → COMMIT (or ABORT on error)
140 REM
150 REM  The worker ID is read from WORKER_ID$ before execution starts.
160 REM  The coordinator URL is read from COORD_URL$ before execution.
170 REM  WORK_ROUNDS% controls how many work-tickets to process.
180 REM
190 REM  Transport (HTTPPOST, HTTPGET, SLEEP) is provided by the emulator.
200 REM  All business logic — auth, serialisation, 2PC — lives in BASIC.
210 REM ================================================================
220 REM
230 REM  READ CONFIGURATION FROM CALLER-PROVIDED VARIABLES
240 REM  (Tests set these before RUNBASIC / the Docker entrypoint uses env vars)
250 IF WORKER_ID$  = "" THEN WORKER_ID$  = "W1"
260 IF COORD_URL$  = "" THEN COORD_URL$  = "http://localhost:8080"
270 IF WORK_ROUNDS% = 0 THEN WORK_ROUNDS% = 3
280 SECRET$ = "BASIC-SECRET"
290 REM
295 REM  SET OTEL SERVICE NAME FOR THIS WORKER INSTANCE
296 REM  Each worker ID (W1, W2, ...) becomes a separate service in Jaeger,
297 REM  rendered in a distinct colour so the distributed trace is clearly
298 REM  partitioned: coordinator spans (colour A), worker-W1 spans (colour B),
299 REM  worker-W2 spans (colour C), hello-bas spans (colour D).
300 OTELSERVICE "worker-" + WORKER_ID$
310 REM
320 REM  PHASE 0: REGISTER WITH COORDINATOR
330 REM  Register first — the response includes the shared hello-world-transaction
340 REM  traceparent (REG_TRACEPARENT$) that we need to link each worker-round
350 REM  span directly under the coordinator's transaction root in Jaeger.
360 GOSUB 1000
370 IF REG_OK% = 0 THEN END
380 REM
390 REM  MAIN WORK LOOP — one round = get ticket, run hello.bas, 2PC.
400 REM  Each round starts a worker-round span as a cross-service child of
410 REM  the coordinator's hello-world-transaction root span, so both workers
420 REM  (W1 and W2) appear as direct siblings under that root in Jaeger.
430 REM
440 REM  Distributed trace blueprint:
450 REM    hello-world-transaction  (coordinator)
460 REM      worker-round           (worker-W1)
470 REM        worker-get-work      (worker-W1)
480 REM        worker-run-hello     (worker-W1)
490 REM          hello-world-iteration (hello-bas)
500 REM      worker-round           (worker-W2)
510 REM        worker-get-work      (worker-W2)
520 REM        worker-run-hello     (worker-W2)
530 REM          hello-world-iteration (hello-bas)
540 REM
550 OTELCOUNT "worker.starts"
560 OTELLOG "WORKER STARTED"
570 ROUND% = 0
580 GOSUB 2000
590 ROUND% = ROUND% + 1
600 IF ROUND% < WORK_ROUNDS% THEN GOTO 580
610 REM
620 REM  DONE — flush telemetry and exit
630 OTELFLUSH
640 END
1000 REM ================================================================
1010 REM  SUBROUTINE: REGISTER WITH COORDINATOR  (GOSUB 1000)
1020 REM  Sets REG_OK% = 1 on success, 0 on failure.
1025 REM  On success, also sets REG_TRACEPARENT$ to the W3C traceparent
1026 REM  of the coordinator's hello-world-transaction span so the caller
1027 REM  can start worker-round as a direct cross-service child.
1030 REM ================================================================
1040 OTELSPAN "worker-register"
1050 REG_BODY$ = "token=" + SECRET$ + "&worker=" + WORKER_ID$
1060 HTTPPOST COORD_URL$ + "/register", REG_BODY$
1070 REG_OK% = 0
1075 REG_TRACEPARENT$ = ""
1080 IF HTTP_STATUS% = 200 THEN REG_OK% = 1
1090 IF INSTR(HTTP_BODY$, "ok=1") > 0 THEN REG_OK% = 1
1095 REM --- Extract the transaction traceparent (55-char W3C format) ---
1096 P% = INSTR(HTTP_BODY$, "traceparent=") + 12
1097 IF P% > 12 THEN REG_TRACEPARENT$ = MID$(HTTP_BODY$, P%, 55)
1100 OTELEND
1110 RETURN
2000 REM ================================================================
2010 REM  SUBROUTINE: ONE COMPLETE WORK ROUND  (GOSUB 2000)
2020 REM  Starts worker-round as a cross-service child of the coordinator's
2030 REM  hello-world-transaction root span, then gets a work ticket, runs
2040 REM  hello.bas, and performs 2PC — all nested inside worker-round.
2045 REM
2046 REM  Trace structure:
2047 REM    hello-world-transaction  (coordinator)
2048 REM      worker-round           (this worker — direct child via REG_TRACEPARENT$)
2049 REM        worker-get-work      (this worker)
2050 REM        worker-run-hello     (this worker)
2051 REM          hello-world-iteration (hello-bas)
2052 REM            hello-world-guard / hello-world-print / hello-world-advance
2053 REM        worker-2pc-prepare   (this worker)
2054 REM        worker-2pc-commit    (this worker)
2055 REM ================================================================
2056 REM --- Start worker-round as direct child of hello-world-transaction ---
2057 OTELSPANWITH "worker-round", REG_TRACEPARENT$
2058 OTELLOG "WORKER ROUND STARTED"
2059 REM --- Get work ticket from coordinator (inside the round span) ---
2060 GOSUB 3000
2063 IF TICKET_OK% = 0 THEN GOTO 2110
2065 REM --- Run hello.bas for the assigned iteration count ---
2070 GOSUB 4000
2075 REM --- 2PC phase 1: ask coordinator to prepare the transaction ---
2080 GOSUB 5000
2085 IF VOTE$ = "commit" THEN GOSUB 6000
2090 IF VOTE$ <> "commit" THEN GOSUB 7000
2110 OTELEND
2120 RETURN
3000 REM ================================================================
3010 REM  SUBROUTINE: GET WORK TICKET FROM COORDINATOR  (GOSUB 3000)
3020 REM  Sets TICKET_OK%=1, TICKET_TID%, TICKET_COUNT% on success.
3025 REM  Also extracts TICKET_TRACEPARENT$ from the response body (kept
3026 REM  for legacy compatibility; REG_TRACEPARENT$ from /register is
3027 REM  used to link worker-round spans to the coordinator root).
3030 REM ================================================================
3040 OTELSPAN "worker-get-work"
3050 WORK_URL$ = COORD_URL$ + "/work?token=" + SECRET$ + "&worker=" + WORKER_ID$
3060 HTTPGET WORK_URL$
3070 TICKET_OK% = 0
3075 TICKET_TRACEPARENT$ = ""
3080 IF INSTR(HTTP_BODY$, "ok=1") = 0 THEN OTELEND
3085 IF INSTR(HTTP_BODY$, "ok=1") = 0 THEN RETURN
3090 TICKET_OK% = 1
3100 REM --- Extract TID from response like "ok=1&tid=42&count=5&traceparent=..." ---
3110 P% = INSTR(HTTP_BODY$, "tid=") + 4
3120 TICKET_TID% = VAL(MID$(HTTP_BODY$, P%, 6))
3130 REM --- Extract count from response ---
3140 P% = INSTR(HTTP_BODY$, "count=") + 6
3150 TICKET_COUNT% = VAL(MID$(HTTP_BODY$, P%, 4))
3160 IF TICKET_COUNT% = 0 THEN TICKET_COUNT% = 5
3165 REM --- Extract coordinator traceparent (55-char W3C format) ---
3166 P% = INSTR(HTTP_BODY$, "traceparent=") + 12
3167 IF P% > 12 THEN TICKET_TRACEPARENT$ = MID$(HTTP_BODY$, P%, 55)
3170 OTELEND
3180 RETURN
4000 REM ================================================================
4010 REM  SUBROUTINE: RUN HELLO.BAS FOR ASSIGNED ITERATIONS  (GOSUB 4000)
4020 REM  Uses the emulator's RUNBASIC to execute hello.bas and captures
4030 REM  the output count into ACTUAL_PRINTS%.
4040 REM ================================================================
4050 OTELSPAN "worker-run-hello"
4060 _STOPS% = TICKET_COUNT%
4070 RUNBASIC "hello.bas"
4080 ACTUAL_PRINTS% = B_N%
4090 OTELCOUNT "worker.hello_world_prints"
4100 OTELEND
4110 RETURN
5000 REM ================================================================
5010 REM  SUBROUTINE: 2PC PHASE 1 — PREPARE  (GOSUB 5000)
5020 REM  Sends print count to coordinator and captures the vote.
5030 REM ================================================================
5040 OTELSPAN "worker-2pc-prepare"
5050 PREP_BODY$ = "token=" + SECRET$ + "&worker=" + WORKER_ID$
5060 PREP_BODY$ = PREP_BODY$ + "&tid=" + STR$(TICKET_TID%)
5070 PREP_BODY$ = PREP_BODY$ + "&prints=" + STR$(ACTUAL_PRINTS%)
5080 HTTPPOST COORD_URL$ + "/prepare", PREP_BODY$
5090 VOTE$ = "abort"
5100 IF INSTR(HTTP_BODY$, "vote=commit") > 0 THEN VOTE$ = "commit"
5110 OTELEND
5120 RETURN
6000 REM ================================================================
6010 REM  SUBROUTINE: 2PC PHASE 2 — COMMIT  (GOSUB 6000)
6020 REM  Notifies coordinator that this worker commits the transaction.
6030 REM ================================================================
6040 OTELSPAN "worker-2pc-commit"
6050 COMM_BODY$ = "token=" + SECRET$ + "&worker=" + WORKER_ID$
6060 COMM_BODY$ = COMM_BODY$ + "&tid=" + STR$(TICKET_TID%)
6070 COMM_BODY$ = COMM_BODY$ + "&prints=" + STR$(ACTUAL_PRINTS%)
6080 HTTPPOST COORD_URL$ + "/commit", COMM_BODY$
6090 OTELCOUNT "worker.commits"
6100 OTELEND
6110 RETURN
7000 REM ================================================================
7010 REM  SUBROUTINE: 2PC PHASE 2 — ABORT  (GOSUB 7000)
7020 REM  Notifies coordinator that this worker is aborting the transaction.
7030 REM ================================================================
7040 OTELSPAN "worker-2pc-abort"
7050 ABRT_BODY$ = "token=" + SECRET$ + "&worker=" + WORKER_ID$
7060 ABRT_BODY$ = ABRT_BODY$ + "&tid=" + STR$(TICKET_TID%)
7070 HTTPPOST COORD_URL$ + "/abort", ABRT_BODY$
7080 OTELCOUNT "worker.aborts"
7090 OTELEND
7100 RETURN
