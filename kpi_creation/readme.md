# KPI creation

Builds the RIS KPI tables `ris_view_dw` and `ris_trends_dw` from the DHMS database and the silver tables.

## Setup

```bash
cd kpi_creation
pip install -r requirements.txt
```

## Run

```bash
python kpi_creation_driver.py                               # db_data_extraction -> ris_view -> ris_trends
python kpi_creation_driver.py --only ris_view ris_trends    # skip the DB pull (uses the latest snapshots)
python kpi_creation_driver.py --keep-going                  # continue after a failure (dependents still skipped)
```

Each step runs as its own process from its own folder. The driver stops at the first failure, prints the error and a
summary, and exits with code 1. `ris_view` needs `db_data_extraction` to succeed; `ris_trends` does not use the DB.

A step can also be run on its own from its folder:

```bash
cd db_data_extraction && python db_extraction.py
cd ris_view           && python main.py                          # all three ris_view steps
cd ris_view           && python -m src.code_intermediate_logic   # one ris_view step
cd ris_trends         && python main.py
```

## Steps

| Step | Reads | Writes |
|---|---|---|
| `db_data_extraction` | Postgres `dhms_staging.public`: `dlm_defect_case`, `udm_defect_reference`, `master_survey_system`, `survey_data_map`, `master_defect_type`, `wfm_survey_schedule`, `master_upc_project` | `input_data/raw_db_tables/<table>/<YYYY>/<MM>/<DD>/<table>.csv` (a second pull on the same day overwrites) |
| `ris_view` 1. `src/code_silver_table_update.py` | latest `dlm_defect_case` / `udm_defect_reference` snapshot, silver defect tables in `input_data/old_silver_data` | `output_data/silver_data_with_status/*.csv` (+ `defect_reference_id`, `current_status`, `final_status`) |
| `ris_view` 2. `src/code_intermediate_logic.py` | `input_data/old_silver_data` (parent / child tables, `master_chainage`, `upc_reporting_intervals`), `output_data/silver_data_with_status` | `output_data/output_kpi_data/final_intermediate.csv` |
| `ris_view` 3. `src/code_ris_view.py` | `output_data/silver_data_with_status` (defect counts, cracking / pothole Closed lengths), child 10m tables in `input_data/old_silver_data` (IRC counts), `input_data/project_master.xlsx`, `final_intermediate.csv` (roughness / rutting / cracking Open lengths, `Total` rows) | `output_data/output_kpi_data/ris_view_dw.csv` |
| `ris_trends` | `master_{roughness,rutting}_{parent,child_10m}`, `master_chainage`, `dlm_threshold_mapping` in `input_data/old_silver_data`, `input_data/project_master.xlsx` | `output_data/output_kpi_data/ris_trends_dw.csv` |

Paths are relative to the `RIS_KPI_golden` folder. DB id columns (`UPC_ID`, `Survey_ID`, ...) are not created
here; they are added when the outputs are pushed to the DB.

## RIS view logic

### 1. Silver status (`utils/status.py`)

| Silver table | `udm_defect_reference.defect_collection` | Matched on silver column |
|---|---|---|
| `master_roughness_parent` | `roughness_parent` | `defect_id` (`SILVER_KEYS`) |
| `master_rutting_parent` | `rutting_parent` | `id` |
| `master_ravelling_parent` | `ravelling_parent` | `id` |
| `master_pothole` | `pothole_child_ca` | `id` |
| `master_cracking` | `cracking_child_ca` | `id` |

- `defect_reference_id`: `udm_defect_reference.id` where `udm_defect_reference.defect_id` = the silver column above.
- `current_status`: `dlm_defect_case.current_status` for that `defect_reference_id`.
- `final_status`: `Closed` for `CLOSED` / `CANCELLED`, `Open` for any other status **and when there is no
  `current_status`** (no DB case = not closed), so it is never empty.

Both joins are left joins on keys that must be unique in the DB tables, so no silver row is duplicated or lost.
The log lists the `CLOSED` / `CANCELLED` cases whose `defect_reference_id` is missing from `udm_defect_reference`
(those cannot reach silver).

### 2. Intermediate statuses (`utils/defect_ids.py`)

- `roughness_status` / `rutting_status`: `final_status` of the parent that holds the row.
- `cracking_status`: over every cracking child (10 m, 'As per CA') in the row: `Open` if any is Open, `Closed`
  only when all are Closed.
- A row with no matching defect has an empty status.

These statuses are used only for the `Total` rows of the RIS view.

### 3. RIS view defect counts (`utils/defect_counts.py`)

`Total_Defects_CA` / `Total_Defects_IRC` = distinct `defect_id` with `breach_flag = 1` on that standard's rows, per
UPC grain / defect type / status. Affected lengths are not checked.

| Defect | CA rows | IRC rows | Status |
|---|---|---|---|
| Cracking | `master_cracking` 'As per CA' | `master_cracking` 'As per IRC' | the row's `final_status` |
| Pothole | `master_pothole` (CA only) | none | the row's `final_status` |
| Roughness / Rutting / Ravelling | parent table (CA only) | child 10m table, 'As per IRC' | IRC children take their parent's `final_status` (matched on `parent_id`, `zone`, `phase`, `cycle`, `source_system`, `detected_on`) |

Every grain gets an `Open` and a `Closed` row (0 when empty). `Total` rows sum the counts of all defect types.

### 4. RIS view affected lengths (`utils/affected_length.py`)

The source is set per defect and status in `LENGTH_SOURCE`:

| Defect | Open | Closed |
|---|---|---|
| Roughness | intermediate | silver |
| Rutting | intermediate | silver |
| Ravelling | 0 (no ravelling length columns in `final_intermediate`) | silver |
| Cracking | intermediate | silver |
| Pothole | 0 (no pothole length columns in `final_intermediate`) | silver |

- **intermediate**: `<defect>_ca_length` / `<defect>_irc_length` of `final_intermediate` summed per the row's
  `<defect>_status`. These lengths come from each reporting-interval window's own flag (window metric >
  threshold), at the CA / IRC reporting interval of the UPC. A `final_intermediate` row gets flag 1 when **at
  least half of it** lies inside breached windows of the same upc / phase / cycle / lane / source_system /
  detected_on (majority overlap, `MIN_COVERED_SHARE` in `utils/spine_flags.py`; adjacent windows are joined), and
  its length = flag × the row's own length (`end_chainage - start_chainage`). Example: breached child 100m window
  254537–254607 on a 50 m grid → 254530–254550 (13 of 20 m) = 1, 254550–254600 = 1, 254600–254650 (7 of 50 m) = 0.
- **Cracking Open minus Closed**: just before `ris_view_dw` is built, cracking Open length = Open - Closed of the
  same UPC / phase / cycle, CA and IRC separately (`SUBTRACT_CLOSED_FROM_OPEN`; a negative result is logged and set
  to 0).
- **silver**: silver table with status, `breach_flag = 1` rows, row's `final_status`. Roughness / rutting /
  ravelling: the parent's `affected_length`, for both CA and IRC (parent tables are 'As per CA' only). Cracking:
  `end_chainage - start_chainage` of 'As per CA' rows -> CA, of 'As per IRC' rows -> IRC. Pothole: 1 m per row (`FIXED_LENGTH_M`; its
  `affected_length` is an area in sqm), 'As per CA' -> CA, 'As per IRC' -> IRC (none today).

`Total` rows come from `final_intermediate`: `total_affected_length_ca` / `_irc` summed per UPC grain; a row is
`Closed` only when its roughness, rutting and cracking statuses are all `Closed`, else `Open`.

## Settings

DB credentials (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_SCHEMA`, `DB_USER`, `DB_PASSWORD`) are in
`db_data_extraction/.env` (template: `db_data_extraction/.env.example`; not committed, see `.gitignore`).
`defect_status_updation` reads the same file. Environment variables with the same names override it. A missing
value stops the DB pull with a message naming the file. All other settings are in each step's own `utils/config.py`.

| Step | Main settings |
|---|---|
| `db_data_extraction` | `.env`: `DB_*` connection; `config.py`: `DB_CONNECT_TIMEOUT`, `DB_TABLES`, `RAW_DB_DIR` |
| `ris_view` | `KEEP_UPCS`, `SILVER_INPUT_DIR`, `RAW_DB_DIR`, `DLM_DEFECT_CASE_FILE` / `UDM_DEFECT_REFERENCE_FILE` (None = latest snapshot), `PROJECT_MASTER_PATH`, `FILTER_BY_PROJECT_MASTER`, `REPORTING_INTERVALS_TABLE`, `DEFAULT_INTERVAL`, `CRACKING_TABLE`, `SILVER_STATUS_DIR`, `KPI_OUTPUT_DIR` |
| `ris_trends` | `KEEP_UPCS`, `KEEP_PAVEMENT_TYPES`, `USE_BREACH_FLAG`, `SILVER_INPUT_DIR`, `THRESHOLD_MAPPING_TABLE`, `PROJECT_MASTER_PATH`, `FILTER_BY_PROJECT_MASTER`, `OUTPUT_DIR` |

## Layout

```
kpi_creation/
├── kpi_creation_driver.py           # runs the steps below in order
├── requirements.txt
├── readme.md
├── db_data_extraction/
│   ├── db_extraction.py             # entry point
│   └── utils/
│       ├── config.py                # DB settings (from ../.env), tables, output path
│       ├── db_pull.py               # SQLAlchemy engine, connection check, table read
│       └── db_store.py              # date folders, atomic CSV write
├── ris_view/
│   ├── main.py                      # runs src steps 1-3
│   ├── src/
│   │   ├── code_silver_table_update.py
│   │   ├── code_intermediate_logic.py
│   │   └── code_ris_view.py
│   └── utils/
│       ├── config.py, io_utils.py, helpers.py                       # all steps
│       ├── raw_tables.py, status.py                                 # step 1: DB snapshots, defect status
│       ├── reporting_intervals.py, defect_report.py, measure_windows.py,
│       │   interval_spine.py, spine_flags.py, defect_ids.py         # step 2: windows, flags, lengths, ids
│       └── project_master.py, defect_counts.py, affected_length.py,
│           output.py                                                # step 3: counts, lengths, ris_view_dw
└── ris_trends/
    ├── main.py                      # steps 1-7
    └── utils/
        ├── config.py, io_utils.py, helpers.py
        ├── filters.py               # UPC / pavement_type / project-master filters
        ├── kpi_metrics.py           # Roughness_Average, Average_Rutting_Depth
        ├── pci.py                   # 1 km chainage buckets -> PCI_Value
        ├── categories.py            # CA / IRC condition categories and lane lengths
        └── output.py                # final ris_trends_dw table
```
