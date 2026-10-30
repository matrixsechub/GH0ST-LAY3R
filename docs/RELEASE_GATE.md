# Release Gate

No deployment or merge claim is valid unless the strict CI workflow passes on the final rebased branch. PR #4 must be rebased after PRs #1 → #2 → #3 and its workflow conflict resolved against final `main`.
