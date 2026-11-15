"""Date-wise snapshot folders for the pulled DB tables: <raw_db_dir>/<table>/<YYYY>/<MM>/<DD>/<table>.csv"""
import os


def table_dir(raw_db_dir, table, when):
    """<raw_db_dir>/<table>/<YYYY>/<MM>/<DD>"""
    return raw_db_dir / table / f"{when:%Y}" / f"{when:%m}" / f"{when:%d}"


def save_csv(df, out_dir, name):
    """Written to a temp file first and then renamed, so a failed pull never leaves a half-written snapshot."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.csv"
    tmp = out_dir / f".{name}.csv.tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)
    return path
