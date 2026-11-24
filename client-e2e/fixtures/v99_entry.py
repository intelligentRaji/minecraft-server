"""PyInstaller entry stub that pins modsync_client.__version__ to 99.0.0 for E2E update tests."""

from __future__ import annotations

import modsync_client

modsync_client.__version__ = "99.0.0"

from modsync_client.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
