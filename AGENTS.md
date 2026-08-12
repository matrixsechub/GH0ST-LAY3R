# AGENTS.md

## Cursor Cloud specific instructions

Ghost Layer Studio is a small, self-contained **Python 3** engine (a CLI/library, no
web server). Source lives in `core/` (engine + substrate/physics/oversoul/output),
`agents/` (the agent constellation), and `scripts/` (demo runner). A single engine
`run()` cycle does: substrate ingestion → dominion physics → agent constellation →
oversoul fusion + recursion → output reactor (returns a JSON-able envelope).

### Dependencies
- **Standard library only** — there are no third-party Python dependencies and no
  `requirements.txt` / `pyproject.toml`. Nothing needs to be installed beyond Python 3
  (developed against 3.12).
- Ignore `REPO_STRUCTURE_COMPLETE.txt` for setup: it describes an unrelated
  TypeScript/Vercel/npm scaffold that is **not** present in this repo.

### Running the app (non-obvious)
Modules use absolute imports (`from core.engine import ...`), so the repo root must be
on `sys.path`. Run from the repo root using one of:
```bash
python3 -m scripts.run_demo          # preferred; root auto-added to sys.path
PYTHONPATH=. python3 scripts/run_demo.py
```
Running `python3 scripts/run_demo.py` directly (without the root on the path) fails with
`ModuleNotFoundError: No module named 'core'`.

### Tests / lint / build
- **No automated test suite** and **no lint config** exist in the repo (no `pytest`,
  `ruff`, etc. are installed). There is nothing to build — it runs directly from source.
- A reasonable sanity check is a compile pass: `python3 -m py_compile core/*.py agents/*.py scripts/*.py`.
