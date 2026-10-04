"""Test-wide setup: isolate tests from the real database and log file.

Runs before test modules import backend.main / get_settings(), so the
cached Settings pick up these values.
"""

import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="detecto-tests-"))
os.environ["DETECTO_DB_PATH"] = str(_tmp / "detecto.db")
os.environ["DETECTO_LOG_FILE"] = ""
