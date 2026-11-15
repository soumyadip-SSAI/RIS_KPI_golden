"""Affected lengths per defect row (Open / Closed) and for the Total rows.

Defect rows (per UPC grain + defect_type + status):
  Roughness / Rutting -> final_intermediate: <defect>_ca_length / <defect>_irc_length summed per <defect>_status
                         of the intermediate row (empty status -> NO_STATUS_AS)
  Ravelling           -> 0 (final_intermediate has no ravelling length columns)
  Cracking            -> silver table with status, breached rows (breach_flag == 1): affected_length of the 10m
                         row; 'As per CA' rows -> CA length, 'As per IRC' rows -> IRC length (row's final_status)
  Pothole             -> silver table with status, breached rows: 1 m per row (its affected_length is the area
                         in sqm), same CA / IRC split as cracking

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

# defect_type -> (CA length, IRC length, status) columns of final_intermediate (statuses also used by the Total rows)
DEFECT_LENGTH_COLUMNS = {
    "Roughness": ("roughness_ca_length", "roughness_irc_length", "roughness_status"),
    "Rutting": ("rutting_ca_length", "rutting_irc_length", "rutting_status"),
    "Cracking": ("cracking_ca_length", "cracking_irc_length", "cracking_status"),
}
# defect rows whose lengths come from final_intermediate
INTERMEDIATE_DEFECTS = ["Roughness", "Rutting"]
# defect rows with no length source (no length columns in final_intermediate) -> 0
NO_LENGTH_DEFECTS = {"Ravelling"}

# defect rows whose lengths come from the silver tables with status (breached rows only)
SILVER_COLUMN_DEFECTS = {"Cracking"}  # affected_length of the row
FIXED_LENGTH_M = {"Pothole": 1}       # fixed length per row (pothole affected_length is an area)
LENGTH_COLUMN = "affected_length"
CA, IRC = "As per CA", "As per IRC"

UPC_GRAIN = ["upc", "source_system", "detected_on", "phase", "cycle"]


def _with_km(out):
    out["affected_length_ca_km"] = out["affected_length_ca_m"] / 1000
    out["affected_length_irc_km"] = out["affected_length_irc_m"] / 1000
    return out


def intermediate_defect_lengths(intermediate):
    """Roughness / rutting lengths per UPC grain + status (<defect>_status of the intermediate row;
    empty -> NO_STATUS_AS)."""
    rows = intermediate.rename(columns={"defect_detected_on": "detected_on"})
    parts = []
    for defect in INTERMEDIATE_DEFECTS:
        ca_col, irc_col, status_col = DEFECT_LENGTH_COLUMNS[defect]
        part = (rows.assign(status=rows[status_col].astype("string").fillna(NO_STATUS_AS))
                .groupby(UPC_GRAIN + ["status"], dropna=False)
                .agg(affected_length_ca_m=(ca_col, "sum"), affected_length_irc_m=(irc_col, "sum"))
                .astype("float64").reset_index())
        parts.append(part.assign(defect_type=defect))
    return pd.concat(parts, ignore_index=True)


def _silver_rows(name, df):
    """Breached cracking / pothole rows of one silver table with their CA / IRC length (m) and status."""
    df = df[~df["defect_type"].isin(set(INTERMEDIATE_DEFECTS) | NO_LENGTH_DEFECTS)]
    unknown = sorted(set(df["defect_type"].dropna()) - SILVER_COLUMN_DEFECTS - set(FIXED_LENGTH_M))
    if unknown:
        raise ValueError(f"{name}: no length rule for defect_type {', '.join(map(str, unknown))}")

    rows = df[df["breach_flag"] == 1].drop_duplicates(UPC_GRAIN + ["defect_type", "threshold_name", "id"])
    if rows["defect_type"].isin(SILVER_COLUMN_DEFECTS).any() and LENGTH_COLUMN not in rows.columns:
        raise ValueError(f"{name}: no {LENGTH_COLUMN} column")
    fixed = rows["defect_type"].map(FIXED_LENGTH_M).astype("float64")
    measured = (pd.to_numeric(rows[LENGTH_COLUMN], errors="coerce").fillna(0.0)
                if LENGTH_COLUMN in rows.columns else pd.Series(0.0, index=rows.index))
    length = fixed.fillna(measured)
    return pd.DataFrame({
        **{c: rows[c] for c in UPC_GRAIN + ["defect_type"]},
        "status": rows["final_status"].astype("string").fillna(NO_STATUS_AS),
        "affected_length_ca_m": length.where(rows["threshold_name"] == CA, 0.0),
        "affected_length_irc_m": length.where(rows["threshold_name"] == IRC, 0.0),
    })


def silver_defect_lengths(tables):
    """Cracking / pothole lengths per UPC grain + defect_type + status from the silver tables with status."""
    rows = pd.concat([_silver_rows(name, df) for name, df in tables.items()], ignore_index=True)
    return (rows.groupby(UPC_GRAIN + ["defect_type", "status"], dropna=False)
            [["affected_length_ca_m", "affected_length_irc_m"]].sum().reset_index())


def attach_defect_lengths(counts, tables, intermediate):
    """Per-defect affected lengths joined on the UPC grain + defect_type + status: roughness / rutting from
    final_intermediate, cracking / pothole from the silver tables, ravelling 0; grains without lengths get 0."""
    lengths = _with_km(pd.concat([intermediate_defect_lengths(intermediate), silver_defect_lengths(tables)],
                                 ignore_index=True))
    log.info("aff_len_df — %s rows (roughness / rutting: intermediate, cracking / pothole: silver)",
             f"{len(lengths):,}")

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
