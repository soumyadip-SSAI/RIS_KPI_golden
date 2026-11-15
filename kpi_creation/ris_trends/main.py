"""RIS Trends KPI (modular version of code_notebooks/RIS_Trends_v6 in_use.ipynb). All paths and settings are in
utils/config.py.

    python main.py        # run from the kpi_creation/ris_trends folder

Reads the silver tables from config.SILVER_INPUT_DIR and writes config.OUTPUT_DIR/ris_trends_dw.csv.
DB id columns (UPC_ID, Survey_ID, Survey_Source_ID) are not created here; they are added on push.

Exit code 1 when the pipeline fails.
"""
import logging
import sys
import time

from utils import config
from utils.categories import build_category_table, merge_categories
from utils.filters import filter_contract_upcs, filter_pavement_types, filter_upcs, log_table_summary
from utils.io_utils import load_contract_upcs, load_silver_tables, load_threshold_mapping, save_csv
from utils.kpi_metrics import build_ris_trends
from utils.output import finalize_ris_trends
from utils.pci import attach_pci

log = logging.getLogger("ris_trends")


def run():
    # --- 1. Load & filter silver tables ---
    tables = load_silver_tables(config.SILVER_INPUT_DIR)
    tables = filter_upcs(tables, config.KEEP_UPCS)
    tables = filter_pavement_types(tables, config.KEEP_PAVEMENT_TYPES)
    log_table_summary(tables)

    # --- 2. Reference data ---
    cm_upcs = load_contract_upcs(config.PROJECT_MASTER_PATH, config.FILTER_BY_PROJECT_MASTER)
    thresholds = load_threshold_mapping(config.SILVER_INPUT_DIR, config.THRESHOLD_MAPPING_TABLE)

    # --- 3. Roughness_Average / Average_Rutting_Depth per grain ---
    ris_trends_df = build_ris_trends(
        tables["master_roughness_parent"], tables["master_rutting_parent"], config.USE_BREACH_FLAG
    )

    # --- 4. PCI_Value from 1 km chainage buckets ---
    ris_trends_df = attach_pci(
        ris_trends_df,
        tables["master_chainage"],
        [tables["master_roughness_parent"], tables["master_rutting_parent"]],
    )

    # --- 5. Project-master filter ---
    ris_trends_df = filter_contract_upcs(ris_trends_df, cm_upcs)

    # --- 6. CA / IRC condition categories (3 rows per grain) ---
    cat_df = build_category_table(tables, thresholds)
    ris_trends_df = merge_categories(ris_trends_df, cat_df, cm_upcs)

    # --- 7. Final table -> CSV ---
    ris_trends_dw = finalize_ris_trends(ris_trends_df)
    log.info("ris_trends_dw finalised — %s rows × %s cols", f"{len(ris_trends_dw):,}", ris_trends_dw.shape[1])

    return save_csv(ris_trends_dw, config.OUTPUT_DIR, config.RIS_TRENDS_OUTPUT_NAME)


def main():
    # Logs contain characters like '—' / '×' that the Windows console codepage cannot print (logging writes to stderr)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    start = time.time()
    try:
        path = run()
    except Exception:
        log.exception("RIS trends FAILED after %.1fs", time.time() - start)
        sys.exit(1)
    log.info("RIS trends done in %.1fs — %s", time.time() - start, path)


if __name__ == "__main__":
    main()
