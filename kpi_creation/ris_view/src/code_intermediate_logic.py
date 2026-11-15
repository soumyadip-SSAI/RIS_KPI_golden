"""Step 2 — affected-length intermediate (modular version of
code_notebooks/Affected length intermediate logic v3 in_use.ipynb, on the smallest-reporting-interval grain).

Reads the silver tables and the reporting intervals from config.SILVER_INPUT_DIR and the silver defect ids /
statuses from config.SILVER_STATUS_DIR (output of step 1), and writes config.INTERMEDIATE_PATH: one row per
smallest-reporting-interval window of each upc / zone / phase / cycle, with defect flags, affected lengths, ids
and statuses.

    python -m src.code_intermediate_logic        # run from the kpi_creation/ris_view folder (this step only)
"""
import logging

from utils import config
from utils.defect_ids import attach_segment_ids
from utils.defect_report import SOURCE_TABLES, SRC_COLS, build_defect_report, prepare_source
from utils.helpers import filter_upcs
from utils.interval_spine import build_interval_spine, flag_interval_spine
from utils.io_utils import load_table, save_csv
from utils.reporting_intervals import load_reporting_intervals

log = logging.getLogger("intermediate_logic")

# id columns of final_intermediate (statuses follow in the same order)
ID_COLUMNS = ["roughness_parent_defect_id", "rutting_parent_defect_id", "cracking_defect_id"]


def run():
    """Returns final_intermediate."""
    # --- 1. Load sources ---
    # Roughness / rutting parent and child tables are optional: a missing one is treated as empty and routing
    # falls back to the next source. Cracking uses only the child 10m table (CRACKING_TABLE)
    sources = {key: prepare_source(load_table(config.SILVER_INPUT_DIR, name, optional=True, columns=SRC_COLS))
               for key, name in SOURCE_TABLES.items()}
    sources["cracking"] = prepare_source(load_table(config.SILVER_INPUT_DIR, config.CRACKING_TABLE))
    chainage = load_table(config.SILVER_INPUT_DIR, "master_chainage")
    ri = load_reporting_intervals(config.SILVER_INPUT_DIR, config.REPORTING_INTERVALS_TABLE, config.DEFAULT_INTERVAL)

    # Optional UPC filter (KEEP_UPCS empty = all UPCs); every row grain includes upc, so UPCs are independent
    if config.KEEP_UPCS:
        log.info("KEEP_UPCS: %s", ", ".join(config.KEEP_UPCS))
        sources = {key: filter_upcs(df, config.KEEP_UPCS) for key, df in sources.items()}
        chainage = filter_upcs(chainage, config.KEEP_UPCS)
        ri = filter_upcs(ri, config.KEEP_UPCS)
        log.info("master_chainage rows after KEEP_UPCS: %s", f"{len(chainage):,}")

    # --- 2. Metric per reporting-interval window, flagged against the threshold
    #        (parent / child 100m as-is, else the child measures inputs averaged per window, then the formula) ---
    defect_report = build_defect_report(sources, ri)

    # --- 3. Rows on the smallest reporting interval per upc / zone / phase / cycle -> flags, affected lengths ---
    final = flag_interval_spine(build_interval_spine(chainage, ri, config.DEFAULT_INTERVAL), defect_report)

    # --- 4. Roughness / rutting parent and cracking ids + statuses (tables from step 1);
    #        cracking_status: Open if any cracking child in the row is Open, Closed if all are Closed ---
    final = attach_segment_ids(final, config.SILVER_STATUS_DIR, config.CRACKING_TABLE, ID_COLUMNS,
                               rollup_status=["cracking_defect_id"])
    save_csv(final, config.INTERMEDIATE_PATH.parent, config.INTERMEDIATE_PATH.stem)
    return final


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    run()
