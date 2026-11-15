"""Affected lengths: defect rows from the silver tables with status, Total rows from final_intermediate.

Defect rows (per UPC grain + defect_type + final_status of the silver row; only rows with breach_flag == 1):
  Roughness / Rutting / Ravelling -> affected_length of the parent row. Parent tables hold 'As per CA' rows only
                                     and the defect status lives on the parent, so a breached parent counts for
                                     both CA and IRC, whatever the CA / IRC reporting interval
  Cracking                        -> affected_length of the 10m row: 'As per CA' rows -> CA length,
                                     'As per IRC' rows -> IRC length (each row has its own status)
  Pothole                         -> 1 m per row (its affected_length is the area in sqm), same CA / IRC split
                                     as cracking
  Chainages are not used.

Total rows -> summed from total_affected_length_<std> of final_intermediate per UPC grain and status; a row is
              'Closed' only when roughness / rutting / cracking status are all Closed, else 'Open' (empty
              status counts as Open)

Grain: upc / source_system / detected_on / phase / cycle (pavement_type is not used: final_intermediate
takes it from master_chainage, which does not match the pavement types of the defect tables).
"""
import logging

import pandas as pd

from utils.defect_counts import COUNT_COLS, NO_STATUS_AS, STATUSES
from utils.project_master import PROJECT_COLUMNS

log = logging.getLogger(__name__)

LENGTH_COLS = ["affected_length_ca_m", "affected_length_irc_m", "affected_length_ca_km", "affected_length_irc_km"]

# silver column with the affected length (m) of one breached row
LENGTH_COLUMN = "affected_length"
# defect_type -> fixed length (m) per breached row instead of LENGTH_COLUMN (pothole affected_length is an area)
FIXED_LENGTH_M = {"Pothole": 1}
# defect types measured from LENGTH_COLUMN
COLUMN_DEFECTS = {"Roughness", "Rutting", "Ravelling", "Cracking"}
# parent-level defects: one 'As per CA' row counts for both CA and IRC
PARENT_DEFECTS = {"Roughness", "Rutting", "Ravelling"}
CA, IRC = "As per CA", "As per IRC"

# defect_type -> (CA length, IRC length, status) columns of final_intermediate (statuses used by the Total rows)
DEFECT_LENGTH_COLUMNS = {
    "Roughness": ("roughness_ca_length", "roughness_irc_length", "roughness_status"),
    "Rutting": ("rutting_ca_length", "rutting_irc_length", "rutting_status"),
    "Cracking": ("cracking_ca_length", "cracking_irc_length", "cracking_status"),
}
UPC_GRAIN = ["upc", "source_system", "detected_on", "phase", "cycle"]


def _silver_rows(name, df):
    """Breached rows of one silver table with their CA / IRC length (m) and status."""
    unknown = sorted(set(df["defect_type"].dropna()) - COLUMN_DEFECTS - set(FIXED_LENGTH_M))
    if unknown:
        raise ValueError(f"{name}: no length rule for defect_type {', '.join(map(str, unknown))} "
                         "(COLUMN_DEFECTS / FIXED_LENGTH_M)")

    rows = df[df["breach_flag"] == 1].drop_duplicates(UPC_GRAIN + ["defect_type", "threshold_name", "id"])
    if rows["defect_type"].isin(COLUMN_DEFECTS).any() and LENGTH_COLUMN not in rows.columns:
        raise ValueError(f"{name}: no {LENGTH_COLUMN} column")
    fixed = rows["defect_type"].map(FIXED_LENGTH_M).astype("float64")
    measured = (pd.to_numeric(rows[LENGTH_COLUMN], errors="coerce").fillna(0.0)
                if LENGTH_COLUMN in rows.columns else pd.Series(0.0, index=rows.index))
    unit = fixed.fillna(measured)
    parent = rows["defect_type"].isin(PARENT_DEFECTS)
    ca_row, irc_row = rows["threshold_name"] == CA, rows["threshold_name"] == IRC
    return pd.DataFrame({
        **{c: rows[c] for c in UPC_GRAIN + ["defect_type"]},
        "status": rows["final_status"].astype("string").fillna(NO_STATUS_AS),
        "affected_length_ca_m": unit.where(ca_row, 0.0),
        # parents: the CA row is the only row and counts for IRC too
        "affected_length_irc_m": unit.where(irc_row | (parent & ca_row), 0.0),
    })


def silver_defect_lengths(tables):
    """Affected lengths per UPC grain + defect_type + status from the silver tables with status."""
    rows = pd.concat([_silver_rows(name, df) for name, df in tables.items()], ignore_index=True)
    out = (rows.groupby(UPC_GRAIN + ["defect_type", "status"], dropna=False)
           [["affected_length_ca_m", "affected_length_irc_m"]].sum().reset_index())
    out["affected_length_ca_km"] = out["affected_length_ca_m"] / 1000
    out["affected_length_irc_km"] = out["affected_length_irc_m"] / 1000
    return out


def attach_defect_lengths(counts, tables):
    """Per-defect affected lengths (silver_defect_lengths) joined on the UPC grain + defect_type + status;
    grains without breached rows get 0."""
    lengths = silver_defect_lengths(tables)
    log.info("aff_len_df — %s rows (from silver tables)", f"{len(lengths):,}")

    out = counts.merge(lengths, on=UPC_GRAIN + ["defect_type", "status"], how="left", validate="one_to_one")
    out[LENGTH_COLS] = out[LENGTH_COLS].fillna(0)
    log.info("ris_view_df5 — %s rows × %s cols", f"{len(out):,}", out.shape[1])
    return out


def _total_status(intermediate):
    """Status of each 10m row's total affected length: 'Closed' only when roughness_status,
    rutting_status and cracking_status are all Closed; otherwise 'Open' (empty status -> NO_STATUS_AS)."""
    all_closed = pd.Series(True, index=intermediate.index)
    for _, _, status_col in DEFECT_LENGTH_COLUMNS.values():
        all_closed &= intermediate[status_col].astype("string").fillna(NO_STATUS_AS) == "Closed"
    return all_closed.map({True: "Closed", False: "Open"})


def _total_lengths(intermediate):
    """total_affected_length_<std> per UPC grain and status (_total_status of the 10m row);
    both statuses present for every UPC grain (0 when none)."""
    rows = intermediate.rename(columns={"defect_detected_on": "detected_on"})
    sums = (
        rows.assign(status=_total_status(rows))
        .groupby(UPC_GRAIN + ["status"], dropna=False)
        .agg(affected_length_ca_m=("total_affected_length_ca", "sum"),
             affected_length_irc_m=("total_affected_length_irc", "sum"))
        .reset_index()
    )

    out = rows[UPC_GRAIN].drop_duplicates().merge(pd.DataFrame({"status": STATUSES}), how="cross")
    out = out.merge(sums, on=UPC_GRAIN + ["status"], how="left", validate="one_to_one")
    for std in ("ca", "irc"):
        out[f"affected_length_{std}_m"] = out[f"affected_length_{std}_m"].fillna(0).astype("float64")
        out[f"affected_length_{std}_km"] = out[f"affected_length_{std}_m"] / 1000
    return out


def build_total_rows(intermediate, defect_rows):
    """'Total' rows per UPC grain and status (Open / Closed): total affected lengths split by the
    10m row status (_total_status), zone / project details taken from the defect rows, and the defect
    counts of that status summed over all defect types."""
    totals = _total_lengths(intermediate)
    totals["defect_type"] = "Total"

    enrich_cols = ["zone"] + list(PROJECT_COLUMNS)
    lookup = defect_rows[UPC_GRAIN + enrich_cols].drop_duplicates(UPC_GRAIN)
    defect_totals = defect_rows.groupby(UPC_GRAIN + ["status"], dropna=False)[COUNT_COLS].sum().reset_index()

    totals = (totals.merge(lookup, on=UPC_GRAIN, how="left")
              .merge(defect_totals, on=UPC_GRAIN + ["status"], how="left", validate="one_to_one"))
    totals[COUNT_COLS] = totals[COUNT_COLS].fillna(0).astype("int64")
    log.info("df_interm_rollup2 — %s rows", f"{len(totals):,}")
    return totals
