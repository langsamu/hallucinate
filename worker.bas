10  REM ================================================================
20  REM  WORKER.BAS - DISTRIBUTED HELLO WORLD WORKER
30  REM
40  REM  Each worker:
50  REM    1. Sets its OTel service name (OTELSERVICE "worker-<id>")
60  REM    2. Registers with the coordinator (POST /register), which
70  REM       returns the shared hello-world-transaction traceparent
80  REM    3. Starts "worker-lifecycle" as a cross-service child of the
90  REM       coordinator's hello-world-transaction span
100 REM    4. Requests a work ticket (GET /work)
110 REM    5. Runs hello.bas for the assigned number of iterations
120 REM    6. Participates in 2PC: PREPARE → COMMIT (or ABORT on error)
130 REM    7. Loops back to step 4 until WORK_ROUNDS% rounds done
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
340 REM  traceparent that we need before we can start worker-lifecycle.
350 GOSUB 1000
360 IF REG_OK% = 0 THEN END
370 REM
380 REM  START WORKER-LIFECYCLE SPAN AS A CROSS-SERVICE CHILD OF THE
390 REM  COORDINATOR'S hello-world-transaction ROOT SPAN.
400 REM  Using OTELSPANWITH instead of OTELSPAN means this span appears
410 REM  under the coordinator's transaction in Jaeger, linking both
420 REM  workers into one unified distributed trace tree.
430 OTELSPANWITH "worker-lifecycle", REG_TRACEPARENT$
440 OTELLOG "WORKER STARTED"
450 OTELCOUNT "worker.starts"
460 REM
470 REM  MAIN WORK LOOP — one round = get ticket, run, 2PC
480 ROUND% = 0
490 GOSUB 2000
500 ROUND% = ROUND% + 1
510 IF ROUND% < WORK_ROUNDS% THEN GOTO 490
520 REM
530 REM  DONE — flush telemetry and exit
540 OTELEND
550 OTELFLUSH
560 END
1000 REM ================================================================
1010 REM  SUBROUTINE: REGISTER WITH COORDINATOR  (GOSUB 1000)
1020 REM  Sets REG_OK% = 1 on success, 0 on failure.
1025 REM  On success, also sets REG_TRACEPARENT$ to the W3C traceparent
1026 REM  of the coordinator's hello-world-transaction span so the caller
1027 REM  can start worker-lifecycle as a cross-service child.
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
2020 REM  Gets a work ticket, runs hello.bas, performs 2PC.
2025 REM
2026 REM  DISTRIBUTED TRACING: worker-round is started as a plain OTELSPAN
2027 REM  (no explicit traceparent needed) because worker-lifecycle, which
2028 REM  is already a cross-service child of hello-world-transaction, is
2029 REM  the active span context at this point.  Jaeger will show:
2030 REM    hello-world-transaction  (coordinator)
2031 REM      worker-lifecycle       (this worker)
2032 REM        worker-round         (this worker)
2033 REM          worker-run-hello -> hello-world-iteration (hello-bas)
2034 REM          worker-2pc-prepare, worker-2pc-commit
2035 REM ================================================================
2040 GOSUB 3000
2043 IF TICKET_OK% = 0 THEN RETURN
2045 REM --- Start worker-round as a child of the active worker-lifecycle span ---
2046 OTELSPAN "worker-round"
2055 OTELLOG "WORKER ROUND STARTED"
2060 REM --- Run hello.bas for the assigned iteration count ---
2065 GOSUB 4000
2070 REM --- 2PC phase 1: ask coordinator to prepare the transaction ---
2080 GOSUB 5000
2090 IF VOTE$ = "commit" THEN GOSUB 6000
2100 IF VOTE$ <> "commit" THEN GOSUB 7000
2110 OTELEND
2120 RETURN
3000 REM ================================================================
3010 REM  SUBROUTINE: GET WORK TICKET FROM COORDINATOR  (GOSUB 3000)
3020 REM  Sets TICKET_OK%=1, TICKET_TID%, TICKET_COUNT% on success.
3025 REM  Also extracts TICKET_TRACEPARENT$ from the response body so
3026 REM  the caller can start worker-round as a child of the coordinator's
3027 REM  hello-world-transaction span.
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
