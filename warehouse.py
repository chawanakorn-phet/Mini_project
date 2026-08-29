"""Shared helper: make sure olist_dw/dev.duckdb exists before an app reads it.

dev.duckdb is a build artifact (gitignored) — it only exists on a machine
where someone ran `dbt run` first. On Streamlit Community Cloud (and any
other fresh checkout) there's no such step, so the first app to start builds
the warehouse itself by shelling out to dbt.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DBT_PROJECT_DIR = PROJECT_ROOT / "olist_dw"
DB_PATH = DBT_PROJECT_DIR / "dev.duckdb"


def _dbt_executable():
    """Find the dbt CLI installed alongside the current Python interpreter.

    Streamlit doesn't run inside an activated venv shell, so a bare "dbt"
    on PATH isn't guaranteed — but pip always installs the console script
    next to python itself (Scripts/ on Windows, bin/ elsewhere).
    """
    bin_dir = Path(sys.executable).parent
    for name in ("dbt.exe", "dbt"):
        candidate = bin_dir / name
        if candidate.exists():
            return str(candidate)
    return "dbt"  # fall back to PATH lookup


def ensure_warehouse_built():
    """Run `dbt run` in olist_dw/ if dev.duckdb doesn't exist yet.

    Returns (ok: bool, log: str). Safe to call on every app start — it's a
    no-op once dev.duckdb is present.
    """
    if DB_PATH.exists():
        return True, ""

    result = subprocess.run(
        [_dbt_executable(), "run", "--profiles-dir", ".", "--project-dir", "."],
        cwd=str(DBT_PROJECT_DIR),
        capture_output=True,
        text=True,
    )
    ok = result.returncode == 0 and DB_PATH.exists()
    log = result.stdout + "\n" + result.stderr
    return ok, log
