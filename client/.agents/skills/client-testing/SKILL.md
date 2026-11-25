---
name: client-testing
description: >-
  Project-scoped unit testing standards for the ModSync client test suite under
  client/tests/. Enforces mirroring client/src/modsync_client/, hermetic
  monkeypatch/tmp_path isolation, dependency injection, reuse of conftest.py
  fixtures and co-located fakes (FakeTransport, httpx.MockTransport),
  parameterized test cases, PyInstaller/cross-platform coverage, and
  deterministic assertions alongside root ruff.toml. Use whenever writing,
  refactoring, or reviewing unit tests in client/tests/.
---

# ModSync Client Unit Testing Guide (`client/tests/`)

Project-specific unit testing practices for `client/tests/`, complementing `test-expertise` and root [ruff.toml](file:///home/wakaria/dev/minecraft-server/ruff.toml).

---

## 1. Scope, Structure, Linting & Execution

- **Mirror Production Layout:** Keep `client/tests/` strictly mirroring `client/src/modsync_client/` (`conftest.py` + `test_<module>.py`, configured with `testpaths = ["tests"]` and `pythonpath = ["src"]` in `client/pyproject.toml`). Do **not** add a `client/tests/helpers/` directory.
- **Boundary:** Keep `client/tests/` fast and in-process (`pytest`, `httpx.MockTransport`, stdlib only); reserve compiled PyInstaller binary and OS GUI/installer runs for `client-e2e/`.
- **Enforced by [ruff.toml](file:///home/wakaria/dev/minecraft-server/ruff.toml):** Import sorting and `from __future__ import annotations` (`I`), Python `>=3.11` typing syntax (`UP`), full function/fixture annotations including `ANN401` (`ANN`), `pytest` conventions (`PT`), and banning `unittest.mock` (`TID251`).
- **`Any` (`ANN401`) Policy:** Prefer concrete types, `Protocol`s, `StatusCallback`, or `object` in signatures. When `Any` is genuinely needed (e.g., dynamically reloaded module handles in `tray_env`), suppress explicitly per line (`# noqa: ANN401`) or per file (`# ruff: noqa: ANN401`) rather than weakening `ruff.toml`.
- **Verification:**
  ```bash
  uv run ruff check client/
  uv --directory client run pytest -v
  ```

---

## 2. Reusable Fixtures & Co-Located Utilities

Shared cross-module fixtures live in [conftest.py](file:///home/wakaria/dev/minecraft-server/client/tests/conftest.py), while single-module doubles and builders stay co-located inside their own `test_<module>.py`:

| Utility | Location | Purpose |
| :--- | :--- | :--- |
| `isolate_host_env` (`autouse=True`) | `client/tests/conftest.py` | Clears `MODSYNC_*` vars, redirects `HOME`/`USERPROFILE`/`APPDATA`/`LOCALAPPDATA`/`XDG_CONFIG_HOME` under `tmp_path / "env"`, patches `Path.home()`, removes `sys.frozen` |
| `mods_dir`, `staging_dir` | `client/tests/conftest.py` | Isolated per-test `mods/` (pre-created) and `staging/` paths |
| `make_sample_update` | `client/tests/conftest.py` | Shared `UpdateInfo` factory used by `test_main.py` and `test_tray.py` |
| `FakeTransport`, `make_syncer`, `_build_remote`, `_write_managed_state`, `_make_forge_jar_bytes` | `client/tests/test_syncer.py` | In-memory `HttpTransport` double, `ModSyncer` factory, manifest/managed-state seeders, and Forge `.jar` builder |
| `install_fake_tk`, `_disable_host_mc_scan` | `client/tests/test_config.py` | `sys.modules` `tkinter` stub; `autouse` guard disabling `detect_minecraft_dirs` host scans |
| `FakeMenuItem`, `FakeMenu`, `FakeIcon`, `FakeService`, `tray_env`, `_find_menu_item` | `client/tests/test_tray.py` | `pystray` + `ModSyncService` doubles, reloadable `modsync_client.tray` fixture, and menu lookup |
| `_FakeSyncer`, `_FakeService`, `stub_logging_basic_config`, `_raise` | `client/tests/test_main.py` | CLI lifecycle doubles, `autouse` `logging.basicConfig` stub, and exception-raiser helper |
| `_release_payload` | `client/tests/test_updater.py` | GitHub Releases JSON payload builder for `httpx.MockTransport` |

- **Co-Location Rule:** Promote a fixture or factory to `client/tests/conftest.py` only when multiple test files share it; keep single-module fakes and builders private (`_prefix` or module-local classes) inside `test_<module>.py`.

---

## 3. Hermetic Isolation & Platform Simulation

- **Never Bypass `isolate_host_env`:** Rely on `conftest.py` plus module-level `autouse` guards for host scanners or global side effects so tests never touch real user configs or launchers.
- **Simulate OS & Frozen Mode:** Test Windows, macOS, Linux, and frozen branches via `monkeypatch.setattr(sys, "platform", ...)` and `monkeypatch.setattr(sys, "frozen", True, raising=False)`. Guard filesystem-level assertions only when the host OS primitive genuinely differs (e.g., `if os.name == "posix":` for `0o755` modes in `test_updater.py`).

---

## 4. Dependency Injection, Test Doubles & Assertions

- **DI Before Monkeypatching:** Pass `HttpTransport`, `mc_running_check`, `httpx.Client`, `executable_path`, or `platform` directly when supported by the SUT; reserve `monkeypatch` for CLI wiring, module globals, `sys.*`, and `builtins.input`.
- **Use `httpx.MockTransport` for `httpx` Callers:** Test `httpx`-backed functions with `httpx.Client(transport=httpx.MockTransport(handler))` (`test_updater.py`).
- **Stub Optional/GUI Imports via `types.ModuleType`:** Assign stubs with `# type: ignore[attr-defined]` and `monkeypatch.setitem(sys.modules, ...)`.
- **Fail-Fast Guards:** Stub callbacks that must not execute with `pytest.fail("<symbol> must not run ...")` rather than silent no-ops.
- **PyInstaller Packaging Invariants:** Verify `main.py` executes cleanly as `__main__` via `runpy.run_path(..., run_name="__main__")` (`test_main.py`), and verify `relaunch_executable` strips `_PYI_*`, `_MEIPASS2`, and bundled `TCL_LIBRARY` while keeping unrelated env vars (`test_updater.py`).
- **Bounded Thread Sync & Complete Outcomes:** Use `threading.Event` + `assert event.wait(timeout=2.0)` (`test_tray.py`) instead of `time.sleep()`. Assert return values, `SystemExit.code` (`0` on intentional cancel), `capsys.readouterr().out`/`.err`, ordered event logs, and exact disk state (`.part`/`.tmp` cleanup and preserved unmanaged files).
