---
name: lint-check
description: Agent lint guide mapping file types to their corresponding linters, type checkers, and syntax validators. Use whenever running lint or verifying modified files.
---

# Lint & Static Check Reference

Run the checks matching every modified file type and resolve any reported errors or warnings.

| File Type | Check Command(s) | Notes |
| :--- | :--- | :--- |
| **Python (`*.py`, `*.spec`)** | `uv run --no-sync ruff check .` (or `uv run --no-sync ruff check <paths>` / `make lint`)<br>`pyright <paths>` (or `pyright`, `uv run --no-sync pyright`, `basedpyright`, or `npx pyright` if available)<br>`python3 -m py_compile <paths>` (for standalone scripts or `.spec` files without tests) | Ruff checks lint, import order, and annotations (including `.spec`); Pyright performs static type and narrowing checks. Report explicitly if `pyright`/`basedpyright` is unavailable locally. |
| **Docker Compose (`docker-compose.yml`)** | `docker compose config --quiet` | Validates compose syntax and variable interpolation. |
