"""Build the combined annual temperature series for The Flattening Well.

Sources:
  - NASA GISTEMP v4 global annual means (anomaly vs 1951-1980), 1880-present
  - ERA5 daily global 2m temperature from C3S Climate Pulse (anomaly vs
    1991-2020), 1940-present, used for the current partial year

ERA5 anomalies are rebaselined to 1951-1980 by adding GISTEMP's mean anomaly
over 1991-2020 (ERA5's own reference period, where its anomalies average zero
by construction).

Outputs:
  data/series.json  - processed series + metadata
  data/series.js    - same payload as `window.VS_DATA = {...}` for index.html

Run: python scripts/build_data.py
"""
import csv
import datetime as dt
import io
import json
import pathlib
import statistics
import urllib.request

GISTEMP_URL = "https://data.giss.nasa.gov/gistemp/tabledata_v4/GLB.Ts+dSST.csv"
ERA5_URL = ("https://sites.ecmwf.int/data/climatepulse/data/series/"
            "era5_daily_series_2t_global.csv")

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "visscience/0.1"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8")


def parse_gistemp(text: str) -> dict[int, float]:
    """Year -> annual (J-D) anomaly in deg C vs 1951-80. Skips incomplete years."""
    lines = text.splitlines()
    reader = csv.DictReader(lines[1:])  # line 0 is the dataset title
    out = {}
    for row in reader:
        jd = (row.get("J-D") or "").strip()
        if jd and jd != "***":
            out[int(row["Year"])] = float(jd)
    return out


def parse_era5_daily(text: str):
    """Returns (year -> mean daily anomaly vs 1991-2020, year -> day count, last_date)."""
    body = "\n".join(l for l in text.splitlines() if not l.startswith("#"))
    reader = csv.DictReader(io.StringIO(body))
    sums, counts, last_date = {}, {}, None
    for row in reader:
        d = dt.date.fromisoformat(row["date"])
        a = float(row["ano_91-20"])
        sums[d.year] = sums.get(d.year, 0.0) + a
        counts[d.year] = counts.get(d.year, 0) + 1
        last_date = d
    means = {y: sums[y] / counts[y] for y in sums}
    return means, counts, last_date


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)

    gistemp_txt = fetch(GISTEMP_URL)
    era5_txt = fetch(ERA5_URL)
    (RAW / "gistemp_glb.csv").write_text(gistemp_txt, encoding="utf-8")
    (RAW / "era5_daily_2t_global.csv").write_text(era5_txt, encoding="utf-8")

    gistemp = parse_gistemp(gistemp_txt)
    era5, era5_days, era5_last = parse_era5_daily(era5_txt)

    # Rebaseline ERA5 (vs 1991-2020) onto GISTEMP's 1951-80 zero.
    offset = statistics.mean(gistemp[y] for y in range(1991, 2021))
    era5_adj = {y: v + offset for y, v in era5.items()}

    # Consistency check over complete overlap years.
    overlap = [y for y in era5_adj if y in gistemp and era5_days[y] >= 360]
    diffs = [gistemp[y] - era5_adj[y] for y in overlap]
    mean_diff = statistics.mean(diffs)
    max_diff = max(abs(d) for d in diffs)

    rows = []
    for y in sorted(gistemp):
        rows.append({"year": y, "anom": round(gistemp[y], 3),
                     "src": "gistemp", "partial": False})
    # Years ERA5 has that GISTEMP's annual table doesn't (the running year).
    for y in sorted(era5_adj):
        if y not in gistemp:
            rows.append({"year": y, "anom": round(era5_adj[y], 3),
                         "src": "era5", "partial": era5_days[y] < 360})

    payload = {
        "meta": {
            "generated": dt.date.today().isoformat(),
            "gistemp_url": GISTEMP_URL,
            "era5_url": ERA5_URL,
            "era5_last_day": era5_last.isoformat(),
            "baseline": "1951-1980 (GISTEMP); ERA5 rebaselined by +%.3f degC" % offset,
            "overlap_check": "mean GISTEMP-ERA5 diff %.3f degC, max %.3f degC over %d complete years"
                             % (mean_diff, max_diff, len(overlap)),
        },
        "rows": rows,
    }

    (DATA / "series.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    (DATA / "series.js").write_text(
        "window.VS_DATA = " + json.dumps(payload) + ";\n", encoding="utf-8")

    print("wrote %d years: %d..%d (last partial=%s, ERA5 through %s)"
          % (len(rows), rows[0]["year"], rows[-1]["year"],
             rows[-1]["partial"], era5_last))
    print("ERA5 rebaseline offset: +%.3f degC" % offset)
    print("overlap check:", payload["meta"]["overlap_check"])


if __name__ == "__main__":
    main()
