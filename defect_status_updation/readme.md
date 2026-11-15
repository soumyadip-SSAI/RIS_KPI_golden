# Defect status updation

Refreshes `ris_view_dw` with the latest defect statuses: pulls the defect case tables from the DB, then re-runs
`kpi_creation/ris_view`.

## Run

```bash
cd defect_status_updation
pip install -r requirements.txt
python main.py                     # DB pull + ris_view

python -m src.db_extraction        # DB pull only
python -m src.kpi_code_flow        # ris_view only (latest snapshots already in input_data/raw_db_tables)
```

Exit code 1 when a step fails (the steps after it are not run). `requirements.txt` also covers `kpi_creation/ris_view`,
which `src/kpi_code_flow.py` runs with the same Python.

## Steps

| Step | Reads | Writes |
|---|---|---|
| 1. `src/db_extraction.py` | Postgres `dhms_staging.public`: `dlm_defect_case`, `udm_defect_reference` | `input_data/raw_db_tables/<table>/<YYYY>/<MM>/<DD>/<table>.csv` |
| 2. `src/kpi_code_flow.py` | runs `kpi_creation/ris_view/main.py` (silver table update -> intermediate logic -> RIS view) on the latest snapshots | `output_data/silver_data_with_status/*.csv`, `output_data/output_kpi_data/final_intermediate.csv`, `output_data/output_kpi_data/ris_view_dw.csv` |

## Settings

- DB credentials: the shared `kpi_creation/db_data_extraction/.env` (template: `.env.example` next to it).
  Environment variables with the same names override it.
- `utils/config.py`: `DB_TABLES`, `RAW_DB_DIR`, the ris_view folder to run and the `ris_view_dw.csv`
  path checked after the run.
- `kpi_creation/ris_view/utils/config.py`: everything the RIS view reads and writes (silver input, project master,
  filters, output paths).

## Layout

```
defect_status_updation/
├── main.py
├── requirements.txt
├── readme.md
├── src/
│   ├── db_extraction.py     # DB -> raw_db_tables
│   └── kpi_code_flow.py     # runs kpi_creation/ris_view
└── utils/
    ├── config.py
    ├── db_pull.py           # SQLAlchemy engine, connection check, table read
    └── db_store.py          # date folders, atomic CSV write
```
