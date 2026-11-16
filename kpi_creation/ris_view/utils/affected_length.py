"""Affected lengths per defect row (Open / Closed) and for the Total rows.

Defect rows (per UPC grain + defect_type + status); the source per defect and status is set in LENGTH_SOURCE:
  "intermediate" -> final_intermediate: <defect>_ca_length / <defect>_irc_length summed per <defect>_status of the
                    intermediate row (empty status -> NO_STATUS_AS); roughness / rutting / cracking only
  "silver"       -> silver table with status, breached rows (breach_flag == 1), row's final_status:
                      roughness / rutting / ravelling: affected_length of the parent row, for both CA and IRC
                                (parent tables hold 'As per CA' rows only and carry the defect status)
                      cracking: end_chainage - start_chainage of the row ('As per CA' rows -> CA,
                                'As per IRC' rows -> IRC)
                      pothole:  1 m per row (its affected_length is the area in sqm), same CA / IRC split
  None           -> 0

  Defect      Open           Closed
  Roughness   intermediate   silver
  Rutting     intermediate   silver
  Ravelling   0              silver        (no ravelling length columns in final_intermediate)
  Cracking    intermediate   silver
  Pothole     0              silver        (no pothole length columns in final_intermediate)

  Then, for SUBTRACT_CLOSED_FROM_OPEN (cracking), Open length = Open - Closed per UPC grain, CA and IRC
  separately (subtract_closed_from_open, run just before ris_view_dw is built; clipped at 0).

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
INTERMEDIATE, SILVER = "intermediate", "silver"
# defect_type -> {status: length source}; None -> 0
LENGTH_SOURCE = {
    "Roughness": {"Open": INTERMEDIATE, "Closed": SILVER},
    "Rutting": {"Open": INTERMEDIATE, "Closed": SILVER},
    "Ravelling": {"Open": None, "Closed": SILVER},
    "Cracking": {"Open": INTERMEDIATE, "Closed": SILVER},
    "Pothole": {"Open": None, "Closed": SILVER},
}

# defect types whose Open length is reduced by their Closed length (subtract_closed_from_open)
SUBTRACT_CLOSED_FROM_OPEN = {"Cracking"}

# silver length rules (breached rows only)
PARENT_DEFECTS = {"Roughness", "Rutting", "Ravelling"}  # LENGTH_COLUMN of the parent row, for CA and IRC
LENGTH_COLUMN = "affected_length"
SPAN_DEFECTS = {"Cracking"}      # end_chainage - start_chainage of the row
FIXED_LENGTH_M = {"Pothole": 1}  # fixed length per row (pothole affected_length is an area)
CA, IRC = "As per CA", "As per IRC"

UPC_GRAIN = ["upc", "source_system", "detected_on", "phase", "cycle"]


def _with_km(out):
    out["affected_length_ca_km"] = out["affected_length_ca_m"] / 1000
    out["affected_length_irc_km"] = out["affected_length_irc_m"] / 1000
    return out


def intermediate_defect_lengths(intermediate):
    """Roughness / rutting / cracking lengths per UPC grain + status (<defect>_status of the intermediate row;
    empty -> NO_STATUS_AS)."""
    rows = intermediate.rename(columns={"defect_detected_on": "detected_on"})
    parts = []
    for defect, (ca_col, irc_col, status_col) in DEFECT_LENGTH_COLUMNS.items():
        part = (rows.assign(status=rows[status_col].astype("string").fillna(NO_STATUS_AS))
                .groupby(UPC_GRAIN + ["status"], dropna=False)
                .agg(affected_length_ca_m=(ca_col, "sum"), affected_length_irc_m=(irc_col, "sum"))
                .astype("float64").reset_index())
        parts.append(part.assign(defect_type=defect))
    return pd.concat(parts, ignore_index=True)


def _silver_rows(name, df):
    """Breached rows of one silver table with their CA / IRC length (m) and status (defect types without a silver
    length rule are skipped)."""
    df = df[df["defect_type"].isin(PARENT_DEFECTS | SPAN_DEFECTS | set(FIXED_LENGTH_M))]
    rows = df[df["breach_flag"] == 1].drop_duplicates(UPC_GRAIN + ["defect_type", "threshold_name", "id"])

    def _numeric(col):
        if col not in rows.columns:
            raise ValueError(f"{name}: no {col} column")
        return pd.to_numeric(rows[col], errors="coerce")

    parent = rows["defect_type"].isin(PARENT_DEFECTS)
    span = rows["defect_type"].isin(SPAN_DEFECTS)
    length = rows["defect_type"].map(FIXED_LENGTH_M).astype("float64")
    if parent.any():
        length = length.where(~parent, _numeric(LENGTH_COLUMN))
    if span.any():
        length = length.where(~span, (_numeric("end_chainage") - _numeric("start_chainage")).abs())
    length = length.fillna(0.0)

    ca_row, irc_row = rows["threshold_name"] == CA, rows["threshold_name"] == IRC
    return pd.DataFrame({
        **{c: rows[c] for c in UPC_GRAIN + ["defect_type"]},
        "status": rows["final_status"].astype("string").fillna(NO_STATUS_AS),
        "affected_length_ca_m": length.where(ca_row, 0.0),
        # parents: the 'As per CA' row is the only row and counts for IRC too
        "affected_length_irc_m": length.where(irc_row | (parent & ca_row), 0.0),
    })


def silver_defect_lengths(tables):
    """Cracking / pothole lengths per UPC grain + defect_type + status from the silver tables with status."""
    rows = pd.concat([_silver_rows(name, df) for name, df in tables.items()], ignore_index=True)
    return (rows.groupby(UPC_GRAIN + ["defect_type", "status"], dropna=False)
            [["affected_length_ca_m", "affected_length_irc_m"]].sum().reset_index())


def _pick_sources(lengths):
    """Keep, per defect_type + status, only the rows of the source set in LENGTH_SOURCE."""
    unknown = sorted(set(lengths["defect_type"].dropna()) - set(LENGTH_SOURCE))
    if unknown:
        raise ValueError(f"No LENGTH_SOURCE for defect_type {', '.join(map(str, unknown))}")
    wanted = [LENGTH_SOURCE[d].get(s) for d, s in zip(lengths["defect_type"], lengths["status"])]
    return lengths[lengths["source"].to_numpy() == pd.Series(wanted, dtype="object").to_numpy()]


def attach_defect_lengths(counts, tables, intermediate):
    """Per-defect affected lengths joined on the UPC grain + defect_type + status, each defect / status taken from
    its LENGTH_SOURCE (final_intermediate or the silver tables; None -> 0); grains without lengths get 0."""
    lengths = pd.concat([intermediate_defect_lengths(intermediate).assign(source=INTERMEDIATE),
                         silver_defect_lengths(tables).assign(source=SILVER)], ignore_index=True)
    lengths = _with_km(_pick_sources(lengths).drop(columns="source"))
    log.info("aff_len_df — %s rows (sources per defect / status: LENGTH_SOURCE)", f"{len(lengths):,}")

    out = counts.merge(lengths, on=UPC_GRAIN + ["defect_type", "status"], how="left", validate="one_to_one")
    out[LENGTH_COLS] = out[LENGTH_COLS].fillna(0)
    log.info("ris_view_df5 — %s rows × %s cols", f"{len(out):,}", out.shape[1])
    return out


def subtract_closed_from_open(defect_rows):
    """For SUBTRACT_CLOSED_FROM_OPEN defects: Open affected length (m, km) = Open - Closed of the same UPC grain,
    CA and IRC separately; a negative result is logged and set to 0."""
    out = defect_rows.copy()
    key = UPC_GRAIN + ["defect_type"]
    target = out["defect_type"].isin(SUBTRACT_CLOSED_FROM_OPEN)
    is_open = (target & (out["status"] == "Open")).to_numpy()
    m_cols = ["affected_length_ca_m", "affected_length_irc_m"]

    closed = out.loc[target & (out["status"] == "Closed"), key + m_cols]
    closed_len = out[key].merge(closed, on=key, how="left", validate="many_to_one")[m_cols].fillna(0.0)
    for std in ("ca", "irc"):
        col = f"affected_length_{std}_m"
        new = out[col].to_numpy() - closed_len[col].to_numpy()
        negative = is_open & (new < 0)
        if negative.any():
            log.warning("%s: Closed > Open on %s rows — Open set to 0", col, int(negative.sum()))
        out.loc[is_open, col] = new[is_open].clip(min=0)
        out[f"affected_length_{std}_km"] = out[col] / 1000
    log.info("Open affected length minus Closed for %s", ", ".join(sorted(SUBTRACT_CLOSED_FROM_OPEN)))
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
