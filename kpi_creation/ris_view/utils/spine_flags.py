"""Final table: 10m chainage spine × defect flags from the defected reporting intervals.

Every 10m spine segment that falls inside a defected interval (defect_flag = 1) in the
defect report inherits that defect's flag; affected length = flag × segment length.

majority_covered (used by final_intermediate, utils/interval_spine.py): a row gets flag 1 when at least
MIN_COVERED_SHARE of its length lies inside defected intervals (adjacent / overlapping intervals are joined first),
so rows at the edges of an interval that is not on the row grid are flagged when most of the row is defected.
"""
import logging

import numpy as np
import pandas as pd

from utils.helpers import to_int, upc_slash
from utils.reporting_intervals import RI_KEYS

log = logging.getLogger(__name__)

JOIN_KEYS = ["upc", "phase", "cycle", "lane", "source_system", "detected_on"]
SPINE_KEYS = JOIN_KEYS + ["pavement_type", "start_chainage", "end_chainage"]
DEFECT_TYPES = ["roughness", "rutting", "cracking"]
FLAG_TYPES = [f"{d}_{rt}" for d in DEFECT_TYPES for rt in ("ca", "irc")]

# majority_covered: share of a row's length that must lie inside defected intervals for flag 1
MIN_COVERED_SHARE = 0.5

FINAL_COLUMNS = [
    "upc", "source_system", "defect_detected_on",
    "start_chainage", "end_chainage", "phase", "cycle", "lane", "pavement_type", "length",
    "roughness_interval_ca", "roughness_interval_irc",
    "cracking_interval_ca", "cracking_interval_irc",
    "rutting_interval_ca", "rutting_interval_irc",
    "roughness_ca_flag", "rutting_ca_flag", "cracking_ca_flag", "defect_ca_flag",
    "roughness_irc_flag", "rutting_irc_flag", "cracking_irc_flag", "defect_irc_flag",
    "roughness_ca_length", "rutting_ca_length", "cracking_ca_length", "total_affected_length_ca",
    "roughness_irc_length", "rutting_irc_length", "cracking_irc_length", "total_affected_length_irc",
]


def build_spine(chainage_df):
    """10m spine from master_chainage, with upc converted to the '/' form used by the defect report."""
    spine = pd.DataFrame({
        "upc": upc_slash(chainage_df["upc"]),
        "lane": chainage_df["lane"],
        "phase": chainage_df["phase"],
        "cycle": chainage_df["cycle"],
        "source_system": chainage_df["source_system"],
        "detected_on": chainage_df["defect_detected_on"],
        "start_chainage": pd.to_numeric(chainage_df["start_chainage"], errors="coerce"),
        "end_chainage": pd.to_numeric(chainage_df["end_chainage"], errors="coerce"),
        "pavement_type": chainage_df["pavement_type"],
    })
    log.info("Master spine rows: %s | UPCs: %s | dates: %s",
             f"{len(spine):,}", spine["upc"].nunique(), spine["detected_on"].nunique())
    return spine


def covered(segments, intervals):
    """1 where a segment [_smin, _smax] lies inside any interval [_min, _max] with the same JOIN_KEYS.

    Equivalent to the notebook's range join, without materialising segment × interval pairs:
    among intervals starting at or before the segment, the furthest-reaching end must cover it.
    """
    flags = np.zeros(len(segments), dtype=int)
    intervals = intervals.dropna(subset=["_min", "_max"]).sort_values("_min", kind="stable")
    if intervals.empty:
        return flags
    intervals = intervals.assign(_reach=intervals.groupby(JOIN_KEYS, dropna=False)["_max"].cummax())

    left = segments.dropna(subset=["_smin"]).sort_values("_smin", kind="stable")
    matched = pd.merge_asof(
        left[["_row", "_smin", "_smax"] + JOIN_KEYS],
        intervals[["_min", "_reach"] + JOIN_KEYS],
        left_on="_smin", right_on="_min", by=JOIN_KEYS, direction="backward",
    )
    flags[matched.loc[matched["_reach"] >= matched["_smax"], "_row"].to_numpy()] = 1
    return flags


def _joined_intervals(intervals):
    """Overlapping / adjacent intervals per JOIN_KEYS joined into one, with _before = metres of the joined
    intervals of the same keys that lie before it."""
    w = intervals.dropna(subset=["_min", "_max"]).sort_values(JOIN_KEYS + ["_min"], kind="stable")
    by = [w[k] for k in JOIN_KEYS]
    prev_reach = w["_max"].groupby(by, dropna=False).cummax().groupby(by, dropna=False).shift()
    block = (prev_reach.isna() | (w["_min"] > prev_reach)).cumsum()
    joined = w.groupby(block).agg(**{k: (k, "first") for k in JOIN_KEYS}, _min=("_min", "min"), _max=("_max", "max"))
    length = joined["_max"] - joined["_min"]
    joined["_before"] = length.groupby([joined[k] for k in JOIN_KEYS], dropna=False).cumsum() - length
    return joined.sort_values("_min", kind="stable").reset_index(drop=True)


def _covered_upto(points, joined):
    """Metres of the joined intervals (same JOIN_KEYS) up to chainage _p, per point _row."""
    m = pd.merge_asof(points[["_row", "_p"] + JOIN_KEYS].sort_values("_p", kind="stable"), joined,
                      left_on="_p", right_on="_min", by=JOIN_KEYS, direction="backward")
    inside = np.minimum(m["_p"], m["_max"]) - m["_min"]
    return pd.Series((m["_before"] + inside).fillna(0.0).to_numpy(), index=m["_row"].to_numpy())


def covered_metres(segments, intervals):
    """Metres of each segment [_smin, _smax] that lie inside intervals [_min, _max] with the same JOIN_KEYS
    (overlapping intervals counted once)."""
    metres = np.zeros(len(segments))
    if intervals.empty:
        return metres
    joined = _joined_intervals(intervals)
    if joined.empty:
        return metres
    left = segments.dropna(subset=["_smin", "_smax"])
    upto_end = _covered_upto(left.assign(_p=left["_smax"]), joined)
    upto_start = _covered_upto(left.assign(_p=left["_smin"]), joined)
    rows = left["_row"].to_numpy()
    metres[rows] = (upto_end.reindex(rows).to_numpy() - upto_start.reindex(rows).to_numpy()).round(6)
    return metres


def majority_covered(segments, intervals, share=MIN_COVERED_SHARE):
    """1 where at least `share` of a segment's length lies inside intervals with the same JOIN_KEYS (and more
    than 0 m), else 0; e.g. interval 254537-254607 -> row 254530-254550 (13 of 20 m) = 1,
    254550-254600 (50 of 50 m) = 1, 254600-254650 (7 of 50 m) = 0."""
    metres = covered_metres(segments, intervals)
    length = (segments["_smax"] - segments["_smin"]).to_numpy()
    return ((metres > 0) & (metres >= share * length)).astype(int)


def defected_windows(defect_report):
    """Windows with defect_flag = 1 as [_min, _max] per JOIN_KEYS, with their defect type in _dt."""
    defected = defect_report[defect_report["defect_flag"] == 1]
    return pd.DataFrame({
        **{k: defected[k] for k in ("upc", "phase", "cycle", "lane", "source_system")},
        "detected_on": defected["defect_detected_on"],
        "_min": np.fmin(defected["start_chainage"], defected["end_chainage"]),
        "_max": np.fmax(defected["start_chainage"], defected["end_chainage"]),
        "_dt": defected["defect_type"],
    })


def flag_spine(spine, defect_report):
    """One row per spine segment with a 0/1 flag per defect type and standard."""
    defected = defected_windows(defect_report)

    segments = spine.reset_index(drop=True).assign(
        _row=lambda d: np.arange(len(d)),
        _smin=lambda d: np.fmin(d["start_chainage"], d["end_chainage"]),
        _smax=lambda d: np.fmax(d["start_chainage"], d["end_chainage"]),
    )
    for dt in FLAG_TYPES:
        segments[f"{dt}_flag"] = covered(segments, defected[defected["_dt"] == dt])

    flag_cols = [f"{dt}_flag" for dt in FLAG_TYPES]
    return segments.groupby(SPINE_KEYS, dropna=False)[flag_cols].max().reset_index()


def build_final_table(flags, ri):
    final = flags.merge(ri, on=RI_KEYS, how="left")

    final["length"] = to_int((final["end_chainage"] - final["start_chainage"]).abs())
    for rt in ("ca", "irc"):
        final[f"defect_{rt}_flag"] = final[[f"{d}_{rt}_flag" for d in DEFECT_TYPES]].max(axis=1)

    # Affected length = flag * length for each defect type
    for dt in FLAG_TYPES:
        final[f"{dt}_length"] = final[f"{dt}_flag"] * final["length"]
    for rt in ("ca", "irc"):
        final[f"total_affected_length_{rt}"] = final[f"defect_{rt}_flag"] * final["length"]

    final = (
        final.rename(columns={"detected_on": "defect_detected_on"})[FINAL_COLUMNS]
        .sort_values(["upc", "lane", "start_chainage"], kind="stable")
        .reset_index(drop=True)
    )
    log.info("Final table: %s rows", f"{len(final):,}")
    return final

