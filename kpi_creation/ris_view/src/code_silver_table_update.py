"""Step 1 — silver status update (modular version of code_notebooks/silver_status_update.ipynb).

Reads udm_defect_reference and dlm_defect_case from the DB snapshots (latest in config.RAW_DB_DIR, or
config.DLM_DEFECT_CASE_FILE / UDM_DEFECT_REFERENCE_FILE), adds defect_reference_id / current_status / final_status
to the silver defect tables in config.SILVER_INPUT_DIR and writes them to config.SILVER_STATUS_DIR.
No DB connection here: kpi_creation/db_data_extraction pulls the tables.

    python -m src.code_silver_table_update        # run from the kpi_creation/ris_view folder (this step only)
"""
import logging

from utils import config
from utils.helpers import filter_upcs
from utils.io_utils import load_silver_table, save_csv
from utils.raw_tables import load_db_tables
from utils.status import SILVER_KEYS, STATUS_TABLES, add_status, case_status, log_closed_case_check

log = logging.getLogger("silver_table_update")


def run():
    """Returns {table: silver table with status}."""
    # --- 1. DB tables (snapshots of db_data_extraction) ---
    db = load_db_tables(config.RAW_DB_DIR, {"udm_defect_reference": config.UDM_DEFECT_REFERENCE_FILE,
                                            "dlm_defect_case": config.DLM_DEFECT_CASE_FILE})
    udm_defect_reference, dlm_defect_case = db["udm_defect_reference"], db["dlm_defect_case"]
    cases = case_status(dlm_defect_case)
    if not config.KEEP_UPCS:
        log.info("KEEP_UPCS empty — all UPCs kept")

    # --- 2. Silver tables + status columns -> SILVER_STATUS_DIR ---
    outputs = {}
    for table, defect_collection in STATUS_TABLES.items():
        silver = filter_upcs(load_silver_table(config.SILVER_INPUT_DIR, table), config.KEEP_UPCS)
        outputs[table] = add_status(silver, defect_collection, udm_defect_reference, cases,
                                    silver_key=SILVER_KEYS.get(table, "id"))
        save_csv(outputs[table], config.SILVER_STATUS_DIR, table)

    # --- 3. Check: CLOSED / CANCELLED cases found in udm_defect_reference ---
    log_closed_case_check(udm_defect_reference, dlm_defect_case)
    return outputs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    run()
