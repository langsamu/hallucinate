# hallucinate

```basic
10 PRINT "HELLO WORLD"
20 GOTO 10
```

## Design critique (software design + CS)

- **Strength**: minimal state and constant-time loop body (`O(1)` per iteration).
- **Weakness**: hard-coded control flow and output string make extension/testing awkward.
- **Weakness**: no separation of concerns (loop control and output are fused).

## Improvement plan

- Keep the original minimal program as the canonical “goto 10” version.
- Add a tiny structured variant that isolates output behavior in a subroutine while preserving the infinite-loop vibe.

## Structured variant

```basic
10 MESSAGE$ = "HELLO WORLD"
20 GOSUB 100
30 GOTO 20
100 PRINT MESSAGE$
110 RETURN
```