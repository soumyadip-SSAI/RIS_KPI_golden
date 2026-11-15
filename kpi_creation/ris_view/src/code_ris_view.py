"""Step 3 — RIS view (modular version of code_notebooks/RIS View Pipeline_v2 in_use.ipynb).

Reads the silver defect tables with status from config.SILVER_STATUS_DIR (output of step 1), the child 10m tables
from config.SILVER_INPUT_DIR (IRC counts of ravelling / roughness / rutting), the project master and
config.INTERMEDIATE_PATH (output of step 2), and writes config.RIS_VIEW_DW_PATH.
DB id columns are not created here; they are added when the output is pushed to Postgres.

    python -m src.code_ris_view        # run from the kpi_creation/ris_view folder (this step only)
"""
import logging

from utils import config
from utils.affected_length import attach_defect_lengths, build_total_rows
from utils.defect_counts import CHILD_COLUMNS, combine_defects, count_defects
from utils.helpers import filter_upcs
from utils.io_utils import load_defect_table, load_intermediate, save_csv
from utils.output import build_ris_view_dw
from utils.project_master import filter_project_upcs, load_project_master

log = logging.getLogger("ris_view")

DEFECT_TABLES = ["master_pothole", "master_ravelling_parent", "master_roughness_parent", "master_rutting_parent"]
# parent table (SILVER_STATUS_DIR) -> child 10m table (SILVER_INPUT_DIR) that gives its IRC counts
CHILD_TABLES = {
    "master_ravelling_parent": "master_ravelling_child_10m",
    "master_roughness_parent": "master_roughness_child_10m",
    "master_rutting_parent": "master_rutting_child_10m",
}


def run():
    """Returns ris_view_dw."""
    # --- 1. Load sources ---
    names = [config.CRACKING_TABLE] + DEFECT_TABLES
    tables = {name: load_defect_table(config.SILVER_STATUS_DIR, name) for name in names}
    children = {child: load_defect_table(config.SILVER_INPUT_DIR, child, columns=CHILD_COLUMNS)
                for child in CHILD_TABLES.values()}
    project_info = load_project_master(config.PROJECT_MASTER_PATH)
    intermediate = load_intermediate(config.INTERMEDIATE_PATH)

    # Optional UPC filter (KEEP_UPCS empty = all UPCs); every output row belongs to one UPC
    if config.KEEP_UPCS:
        log.info("KEEP_UPCS: %s", ", ".join(config.KEEP_UPCS))
        tables = {name: filter_upcs(df, config.KEEP_UPCS) for name, df in tables.items()}
        children = {name: filter_upcs(df, config.KEEP_UPCS) for name, df in children.items()}
        intermediate = filter_upcs(intermediate, config.KEEP_UPCS)

    # --- 2. Keep only project-master UPCs ---
    tables = filter_project_upcs(tables, project_info, config.FILTER_BY_PROJECT_MASTER)
    children = filter_project_upcs(children, project_info, config.FILTER_BY_PROJECT_MASTER)

    # --- 3. Defect rows (IRC of ravelling/roughness/rutting from child 10m) + project details
    #        -> breached-defect counts per grain ---
    children = {parent: children[child] for parent, child in CHILD_TABLES.items()}
    counts = count_defects(combine_defects(tables, children), project_info)

    # --- 4. Affected lengths: roughness / rutting defect rows and 'Total' rows from final_intermediate,
    #        cracking / pothole defect rows from the silver tables with status ---
    defect_rows = attach_defect_lengths(counts, tables, intermediate)
    total_rows = build_total_rows(intermediate, defect_rows)

    # --- 5. Final table -> CSV ---
    ris_view_dw = build_ris_view_dw(defect_rows, total_rows)
    log.info("ris_view_dw — %s rows × %s cols", f"{len(ris_view_dw):,}", ris_view_dw.shape[1])

    save_csv(ris_view_dw, config.RIS_VIEW_DW_PATH.parent, config.RIS_VIEW_DW_PATH.stem)
    return ris_view_dw


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    run()
