10  REM ================================================================
20  REM  WORKER.BAS - DISTRIBUTED HELLO WORLD WORKER
30  REM
40  REM  Each worker:
50  REM    1. Registers with the coordinator (POST /register)
60  REM    2. Requests a work ticket (GET /work)
70  REM    3. Runs hello.bas for the assigned number of iterations
80  REM    4. Participates in 2PC: PREPARE → COMMIT (or ABORT on error)
90  REM    5. Loops back to step 2 until WORK_ROUNDS% rounds done
100 REM
110 REM  The worker ID is read from WORKER_ID$ before execution starts.
120 REM  The coordinator URL is read from COORD_URL$ before execution.
130 REM  WORK_ROUNDS% controls how many work-tickets to process.
140 REM
150 REM  Transport (HTTPPOST, HTTPGET, SLEEP) is provided by the emulator.
160 REM  All business logic — auth, serialisation, 2PC — lives in BASIC.
170 REM ================================================================
180 REM
190 REM  READ CONFIGURATION FROM CALLER-PROVIDED VARIABLES
200 REM  (Tests set these before RUNBASIC / the Docker entrypoint uses env vars)
210 IF WORKER_ID$  = "" THEN WORKER_ID$  = "W1"
220 IF COORD_URL$  = "" THEN COORD_URL$  = "http://localhost:8080"
230 IF WORK_ROUNDS% = 0 THEN WORK_ROUNDS% = 3
240 SECRET$ = "BASIC-SECRET"
250 REM
260 REM  INITIALISE WORKER TELEMETRY
270 OTELSPAN "worker-lifecycle"
280 OTELLOG "WORKER STARTED"
290 OTELCOUNT "worker.starts"
300 REM
310 REM  PHASE 0: REGISTER WITH COORDINATOR
320 GOSUB 1000
330 IF REG_OK% = 0 THEN OTELLOG "REGISTRATION FAILED"
335 IF REG_OK% = 0 THEN OTELEND
338 IF REG_OK% = 0 THEN END
340 REM
350 REM  MAIN WORK LOOP — one round = get ticket, run, 2PC
360 ROUND% = 0
370 GOSUB 2000
380 ROUND% = ROUND% + 1
390 IF ROUND% < WORK_ROUNDS% THEN GOTO 370
400 REM
410 REM  DONE — flush telemetry and exit
420 OTELEND
430 OTELFLUSH
440 END
1000 REM ================================================================
1010 REM  SUBROUTINE: REGISTER WITH COORDINATOR  (GOSUB 1000)
1020 REM  Sets REG_OK% = 1 on success, 0 on failure.
1030 REM ================================================================
1040 OTELSPAN "worker-register"
1050 REG_BODY$ = "token=" + SECRET$ + "&worker=" + WORKER_ID$
1060 HTTPPOST COORD_URL$ + "/register", REG_BODY$
1070 REG_OK% = 0
1080 IF HTTP_STATUS% = 200 THEN REG_OK% = 1
1090 IF INSTR(HTTP_BODY$, "ok=1") > 0 THEN REG_OK% = 1
1100 OTELEND
1110 RETURN
2000 REM ================================================================
2010 REM  SUBROUTINE: ONE COMPLETE WORK ROUND  (GOSUB 2000)
2020 REM  Gets a work ticket, runs hello.bas, performs 2PC.
2025 REM
2026 REM  DISTRIBUTED TRACING: the coordinator embeds a W3C traceparent in
2027 REM  the /work response (its "hello-world-transaction" root span).  This
2028 REM  worker extracts that traceparent and starts "worker-round" as a
2029 REM  cross-service child, so the Jaeger trace shows:
2030 REM    hello-world-transaction (coordinator)
2031 REM      worker-round (this worker)
2032 REM        worker-run-hello -> hello-world-iteration -> ...
2033 REM ================================================================
2040 REM --- Get work ticket BEFORE opening worker-round span so we can ---
2041 REM --- use the coordinator's traceparent as the parent context.    ---
2042 GOSUB 3000
2043 IF TICKET_OK% = 0 THEN RETURN
2044 REM --- Start worker-round as a child of the coordinator's span ---
2045 OTELSPANWITH "worker-round", TICKET_TRACEPARENT$
2050 REM --- Log which worker is handling this round ---
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
