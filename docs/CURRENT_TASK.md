# CURRENT_TASK

## Stage

Fix QuickBooks sync regression after removing dummy data.

## Current task

**Complete.** Fixed `pull_raw_records` in `core/quickbooks/client.py` so the QuickBooks client is passed to `model.all(qb=...)` correctly. Added a regression test in `core/tests/test_quickbooks.py`. Full suite: 148 tests pass.

## Branch

`feature/close-assistant-build`

## Next step

Commit the fix and push to `feature/close-assistant-build`.
