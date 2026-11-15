"""KPI code flow: runs kpi_creation/ris_view (silver table update -> intermediate logic -> RIS view), which reads the
latest raw_db_tables snapshot and updates ris_view_dw.csv in output_data/output_kpi_data.

ris_view runs as its own process from its own folder (as kpi_creation_driver.py does): it has its own utils package
and takes all its paths from kpi_creation/ris_view/utils/config.py.

    python -m src.kpi_code_flow        # run from the defect_status_updation folder
"""
import logging
import os
import subprocess
import sys
import time

from utils import config

log = logging.getLogger("kpi_code_flow")


def run_ris_view():
    """Run kpi_creation/ris_view/main.py; returns the updated ris_view_dw path.
    Raises RuntimeError when it fails or does not write RIS_VIEW_DW_OUTPUT_PATH."""
    code_dir, script, target = config.RIS_VIEW_CODE_DIR, config.RIS_VIEW_SCRIPT, config.RIS_VIEW_DW_OUTPUT_PATH
    log.info("Running %s", code_dir / script)
    start = time.time()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run([sys.executable, script], cwd=code_dir, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"{code_dir.name}/{script} failed (exit code {proc.returncode})")

    # ris_view takes its output path from its own config: make sure it is the file this flow reports
    if not target.exists() or target.stat().st_mtime < start:
        raise RuntimeError(f"{code_dir.name}/{script} did not update {target} — check RIS_VIEW_DW_PATH in "
                           f"{code_dir / 'utils' / 'config.py'}")
    log.info("Updated %s", target)
    return target


def run_kpi_flow():
    """ris_view (latest DB snapshots -> silver status -> final_intermediate -> ris_view_dw); returns the
    ris_view_dw path."""
    return run_ris_view()


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    try:
        run_kpi_flow()
    except Exception:
        log.exception("Aborted")
        sys.exit(1)
