"""RIS view: silver status update -> affected-length intermediate -> RIS view, in one run.
All paths and settings are in utils/config.py.

    python main.py        # run from the kpi_creation/ris_view folder

    1. src/code_silver_table_update  raw_db_tables + old_silver_data -> silver_data_with_status
    2. src/code_intermediate_logic   old_silver_data + silver_data_with_status -> final_intermediate.csv
    3. src/code_ris_view             silver_data_with_status + final_intermediate.csv -> ris_view_dw.csv

Exit code 1 when any step fails (the steps after it are not run).
"""
import logging
import sys
import time

from src import code_intermediate_logic, code_ris_view, code_silver_table_update
from utils import config

log = logging.getLogger("ris_view_flow")

STEPS = [
    ("silver table update", code_silver_table_update.run),
    ("intermediate logic", code_intermediate_logic.run),
    ("RIS view", code_ris_view.run),
]


def main():
    # Logs contain characters like '—' / '→' that the Windows console codepage cannot print (logging writes to stderr)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    start = time.time()
    try:
        for i, (name, run) in enumerate(STEPS, 1):
            step_start = time.time()
            log.info("Step %d/%d: %s", i, len(STEPS), name)
            run()
            log.info("Step %d/%d: %s done in %.1fs", i, len(STEPS), name, time.time() - step_start)
    except Exception:
        log.exception("RIS view FAILED after %.1fs", time.time() - start)
        sys.exit(1)
    log.info("RIS view done in %.1fs — %s", time.time() - start, config.RIS_VIEW_DW_PATH)


if __name__ == "__main__":
    main()
