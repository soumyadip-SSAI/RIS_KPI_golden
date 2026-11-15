"""RIS view defect status update: pull the status tables from the DB, then re-run kpi_creation/ris_view so
output_data/output_kpi_data/ris_view_dw.csv picks up the latest defect statuses. Settings are in utils/config.py
(DB, raw_db_tables) and kpi_creation/ris_view/utils/config.py (RIS view inputs / outputs).

    python main.py        # run from the defect_status_updation folder

    1. src/db_extraction  DB -> input_data/raw_db_tables/<table>/<YYYY>/<MM>/<DD>/<table>.csv
                          (dlm_defect_case, udm_defect_reference)
    2. src/kpi_code_flow  kpi_creation/ris_view: silver table update -> intermediate logic -> RIS view
                          -> output_data/output_kpi_data/ris_view_dw.csv

Exit code 1 when any step fails (the steps after it are not run).
"""
import logging
import sys
import time

from src.db_extraction import extract_tables
from src.kpi_code_flow import run_kpi_flow

log = logging.getLogger("defect_status")


def main():
    # The KPI code logs characters like '—' / '→' that the Windows console codepage cannot print
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    start = time.time()
    try:
        log.info("Step 1/2: DB extraction")
        extract_tables()
        log.info("Step 2/2: RIS view (kpi_creation/ris_view)")
        ris_view_dw = run_kpi_flow()
    except Exception:
        log.exception("Defect status update FAILED after %.1fs", time.time() - start)
        sys.exit(1)
    log.info("Defect status update done in %.1fs — ris_view_dw: %s", time.time() - start, ris_view_dw)


if __name__ == "__main__":
    main()
