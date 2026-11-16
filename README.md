# RIS KPI golden

Builds the RIS KPI tables (`ris_view_dw`, `ris_trends_dw`) from the DHMS database (Postgres `dhms_staging.public`)
and the silver defect tables. There are two code flows:

| Flow | Use it when | Outputs |
|---|---|---|
| [`kpi_creation`](kpi_creation/readme.md) | Full RIS KPI creation (new survey data / silver tables) | `ris_view_dw.csv`, `ris_trends_dw.csv` |
| [`defect_status_updation`](defect_status_updation/readme.md) | Only defect statuses changed in the DB (cases closed, assigned, ...) | `ris_view_dw.csv` refreshed |

## 1. `kpi_creation` — RIS KPI creation

```bash
cd kpi_creation
pip install -r requirements.txt
python kpi_creation_driver.py                               # db_data_extraction -> ris_view -> ris_trends
python kpi_creation_driver.py --only ris_view ris_trends    # skip the DB pull (uses the latest snapshots)
```

1. **`db_data_extraction`**: pulls the DB tables (`dlm_defect_case`, `udm_defect_reference`, `master_upc_project`, ...)
   into dated snapshots under `input_data/raw_db_tables/`.
2. **`ris_view`**: runs three steps:
   1. silver status update: adds `defect_reference_id` / `current_status` / `final_status` to the silver defect
      tables (`output_data/silver_data_with_status/`)
   2. intermediate logic: defect flags, affected lengths, defect ids and statuses per reporting-interval window
      (`final_intermediate.csv`)
   3. RIS view (`ris_view_dw.csv`)
3. **`ris_trends`**: roughness / rutting averages, PCI and condition categories (`ris_trends_dw.csv`). Reads only
   the silver tables, not the DB.

## 2. `defect_status_updation` — RIS view update after a defect status change

```bash
cd defect_status_updation
pip install -r requirements.txt
python main.py
```

1. Pulls only `dlm_defect_case` and `udm_defect_reference` from the DB into `input_data/raw_db_tables/`.
2. Re-runs `kpi_creation/ris_view` (the same code, nothing duplicated) so `ris_view_dw.csv` picks up the latest
   statuses.

`ris_trends` is not re-run, because it does not use defect statuses.

## RIS view logic in brief

- **Status (silver):** `udm_defect_reference.defect_id` links a silver defect to a `defect_reference_id` (on silver
  `id`; on silver `defect_id` for `master_roughness_parent`). `dlm_defect_case` gives its `current_status`.
  `final_status` = `Closed` for `CLOSED` / `CANCELLED`, otherwise `Open` (also when there is no case).
- **Status (intermediate):** a row is `Closed` only when every silver defect in it is `Closed`, else `Open`.
- **Defect counts:** distinct breached defects (`breach_flag = 1`) per status, from the silver tables.
- **Affected lengths:** Open from `final_intermediate` (roughness, rutting, cracking; ravelling and pothole 0),
  Closed from the silver tables (breached rows). Cracking Open = Open - Closed. `Total` rows come from
  `final_intermediate`.

Full rules: [kpi_creation/readme.md](kpi_creation/readme.md#ris-view-logic).

## Input data

`input_data/` and `output_data/` are not in the repo (`.gitignore`). After cloning, add:

- `input_data/old_silver_data/`: the silver tables (`master_*.csv`, `master_chainage.csv`, `upc_reporting_intervals.csv`,
  `dlm_threshold_mapping.csv`)
- `input_data/project_master.xlsx`

`input_data/raw_db_tables/` is filled by the DB pull, and `output_data/` is created by the runs.

## Folders

```
RIS_KPI_golden/
├── kpi_creation/             # flow 1: db_data_extraction, ris_view, ris_trends + kpi_creation_driver.py
├── defect_status_updation/   # flow 2: DB status pull + re-run of kpi_creation/ris_view
├── input_data/
│   ├── old_silver_data/      # silver tables (input)
│   ├── raw_db_tables/        # DB snapshots: <table>/<YYYY>/<MM>/<DD>/<table>.csv
│   └── project_master.xlsx
└── output_data/
    ├── silver_data_with_status/   # silver defect tables + status columns
    └── output_kpi_data/           # final_intermediate.csv, ris_view_dw.csv, ris_trends_dw.csv
```

DB credentials (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_SCHEMA`, `DB_USER`, `DB_PASSWORD`) are in one file,
`kpi_creation/db_data_extraction/.env`, read by both flows (copy `.env.example` next to it to create it; it is in
`.gitignore`, and environment variables override it). All other settings are in each step's `utils/config.py`.
Details, steps and settings for each flow are in
its own readme.
