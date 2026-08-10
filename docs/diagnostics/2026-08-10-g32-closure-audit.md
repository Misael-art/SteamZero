# G32 closure audit — 2026-08-10

- Base commit of tree: `39bd325` (origin/main at branch creation)
- Docs commit on branch: `216f87e`
- G32 fix commit present: `242ba38` (`242ba38d17762b4c43e25a862626f065f53346ee`)
- Branch: `codex/docs-g7-g32-m14`
- Python: `Python 3.14.6`
- Node ids: `tests/integration/test_cast_engine_ipc.py::TestEngineProtocol::test_start_session_already_running` and `tests/integration/test_cast_engine_ipc.py::TestEngineProtocol::test_pause_resume_with_pipeline`
- Method: sequential isolated runs; 50× both G32 tests in one invocation; then 5× full `test_cast_engine_ipc.py`
- Note: earlier aborted attempt used wrong node ids / concurrent kill; discarded
- Smoke (1× both): 2 passed in 11.80s (pre-stress)

## Stress A — 50× both G32 tests together

progress pair 10/50 fails=0
progress pair 20/50 fails=0
progress pair 30/50 fails=0
progress pair 40/50 fails=0
progress pair 50/50 fails=0
pair (both G32 tests): failures=0/50

## Stress B — 5× full test_cast_engine_ipc.py
46 passed in 2.25s
real-state after:  exists=True files=11810 directories=1924 bytes=1096910625 max_mtime_ns=1786132101843430846 source=HOME-default
46 passed in 2.28s
real-state after:  exists=True files=11810 directories=1924 bytes=1096910625 max_mtime_ns=1786132101843430846 source=HOME-default
46 passed in 2.23s
real-state after:  exists=True files=11810 directories=1924 bytes=1096910625 max_mtime_ns=1786132101843430846 source=HOME-default
46 passed in 2.28s
real-state after:  exists=True files=11810 directories=1924 bytes=1096910625 max_mtime_ns=1786132101843430846 source=HOME-default
46 passed in 2.34s
real-state after:  exists=True files=11810 directories=1924 bytes=1096910625 max_mtime_ns=1786132101843430846 source=HOME-default
full cast_engine_ipc: failures=0/5

## Conclusion

PASS: 0 failures in 50 pair runs + 5 full-file runs (46 tests each, ~2.2–2.3 s)
after fix `242ba38`. No timeout increases. Real-state guard: no mutation of host
state home across runs.

**G32 closed** in `docs/KNOWN-GAPS.md` with this evidence (2026-08-10).

`DONE_G32 RESULT=PASS FAIL_PAIR=0 FAIL_FULL=0`
