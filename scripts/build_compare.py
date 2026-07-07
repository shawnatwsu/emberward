"""Build the six-dataset global temperature comparison for compare.html.

Fetches the six series behind the WMO's annual global temperature assessment:

  GISTEMP v4      NASA            1880-   station+ship obs   vs 1951-1980
  HadCRUT5        UK Met Office   1850-   station+ship obs   vs 1961-1990
  NOAAGlobalTemp  NOAA (v6)       1850-   station+ship obs   vs 1971-2000
  Berkeley Earth  Berkeley        1850-   station+ship obs   vs 1951-1980
  ERA5            ECMWF/C3S       1940-   reanalysis         vs 1991-2020
  JMA             Japan Met       1891-   station+ship obs   vs 1991-2020

Each series is rebaselined to a common 1951-1980 zero by subtracting its own
mean over that period, so the curves are directly comparable. The running year
is included only for ERA5 (year-to-date mean, flagged partial).

Outputs data/compare.json and data/compare.js (window.VS_COMPARE).

Run: python scripts/build_compare.py
"""
import csv
import datetime as dt
import io
import json
import pathlib
import re
import statistics
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"

BASE_LO, BASE_HI = 1951, 1980

GISTEMP_URL = "https://data.giss.nasa.gov/gistemp/tabledata_v4/GLB.Ts+dSST.csv"
HADCRUT_URL = ("https://www.metoffice.gov.uk/hadobs/hadcrut5/data/HadCRUT.5.0.2.0/"
               "analysis/diagnostics/HadCRUT.5.0.2.0.analysis.summary_series.global.annual.csv")
NOAA_DIR = "https://www.ncei.noaa.gov/data/noaa-global-surface-temperature/v6/access/timeseries/"
BERKELEY_URL = ("https://berkeley-earth-temperature.s3.us-west-1.amazonaws.com/"
                "Global/Land_and_Ocean_summary.txt")
ERA5_URL = ("https://sites.ecmwf.int/data/climatepulse/data/series/"
            "era5_daily_series_2t_global.csv")
JMA_URL = "https://www.data.jma.go.jp/tcc/tcc/products/gwp/temp/list/csv/year_wld.csv"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "visscience/0.1"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8")


def save_raw(name: str, text: str) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / name).write_text(text, encoding="utf-8")


def parse_gistemp(text: str) -> dict[int, float]:
    reader = csv.DictReader(text.splitlines()[1:])
    out = {}
    for row in reader:
        jd = (row.get("J-D") or "").strip()
        if jd and jd != "***":
            out[int(row["Year"])] = float(jd)
    return out


def parse_hadcrut(text: str) -> dict[int, float]:
    reader = csv.DictReader(io.StringIO(text))
    return {int(r["Time"]): float(r["Anomaly (deg C)"]) for r in reader}


def parse_noaa() -> tuple[dict[int, float], str]:
    listing = fetch(NOAA_DIR)
    names = sorted(set(re.findall(
        r"aravg\.ann\.land_ocean\.90S\.90N\.v[\d.]+\.\d{6}\.asc", listing)))
    latest = names[-1]
    text = fetch(NOAA_DIR + latest)
    save_raw("noaa_" + latest, text)
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            out[int(parts[0])] = float(parts[1])
    return out, NOAA_DIR + latest


def parse_berkeley(text: str) -> dict[int, float]:
    out = {}
    for line in text.splitlines():
        if line.strip().startswith("%") or not line.strip():
            continue
        parts = line.split()
        year, anom = int(parts[0]), parts[1]
        if anom.lower() != "nan":
            out[year] = float(anom)
    return out


def parse_era5(text: str):
    body = "\n".join(l for l in text.splitlines() if not l.startswith("#"))
    reader = csv.DictReader(io.StringIO(body))
    sums, counts, last = {}, {}, None
    for row in reader:
        d = dt.date.fromisoformat(row["date"])
        sums[d.year] = sums.get(d.year, 0.0) + float(row["ano_91-20"])
        counts[d.year] = counts.get(d.year, 0) + 1
        last = d
    return {y: sums[y] / counts[y] for y in sums}, counts, last


def parse_jma(text: str) -> dict[int, float]:
    reader = csv.DictReader(io.StringIO(text))
    return {int(r["Year"]): float(r["Global"]) for r in reader}


def rebaseline(series: dict[int, float]) -> tuple[dict[int, float], float]:
    ref = [series[y] for y in range(BASE_LO, BASE_HI + 1) if y in series]
    off = statistics.mean(ref)
    return {y: v - off for y, v in series.items()}, off


def main() -> None:
    gistemp_txt = fetch(GISTEMP_URL);  save_raw("gistemp_glb.csv", gistemp_txt)
    hadcrut_txt = fetch(HADCRUT_URL);  save_raw("hadcrut5.csv", hadcrut_txt)
    berkeley_txt = fetch(BERKELEY_URL); save_raw("berkeley.txt", berkeley_txt)
    era5_txt = fetch(ERA5_URL);        save_raw("era5_daily_2t_global.csv", era5_txt)
    jma_txt = fetch(JMA_URL);          save_raw("jma.csv", jma_txt)

    era5_ann, era5_days, era5_last = parse_era5(era5_txt)
    noaa_raw, noaa_url = parse_noaa()

    sources = [
        # id, label, native baseline, series dict, partial-year day counts
        ("gistemp",  "NASA GISTEMP v4",   "1951-1980", parse_gistemp(gistemp_txt), None),
        ("hadcrut5", "HadCRUT5",          "1961-1990", parse_hadcrut(hadcrut_txt), None),
        ("noaa",     "NOAAGlobalTemp v6", "1971-2000", noaa_raw,                   None),
        ("berkeley", "Berkeley Earth",    "1951-1980", parse_berkeley(berkeley_txt), None),
        ("era5",     "ERA5 (reanalysis)", "1991-2020", era5_ann,                   era5_days),
        ("jma",      "JMA",               "1991-2020", jma_txt and parse_jma(jma_txt), None),
    ]

    datasets, notes = [], []
    for sid, label, native, series, days in sources:
        adj, off = rebaseline(series)
        years = sorted(adj)
        # completed years only, except keep a flagged year-to-date tip for ERA5
        rows = []
        for y in years:
            partial = bool(days and days.get(y, 366) < 360)
            if partial and sid != "era5":
                continue
            rows.append((y, round(adj[y], 3), partial))
        if days:  # drop non-final partial years except the most recent
            rows = [r for r in rows if not r[2] or r[0] == max(y for y, _, _ in rows)]
        datasets.append({
            "id": sid, "label": label,
            "years": [r[0] for r in rows],
            "anoms": [r[1] for r in rows],
            "partial_last": rows[-1][2],
        })
        notes.append({"id": sid, "label": label, "native_baseline": native,
                      "offset_removed": round(off, 3),
                      "span": f"{rows[0][0]}-{rows[-1][0]}"})

    payload = {
        "meta": {
            "generated": dt.date.today().isoformat(),
            "common_baseline": f"{BASE_LO}-{BASE_HI}",
            "era5_last_day": era5_last.isoformat(),
            "noaa_file": noaa_url,
            "notes": notes,
        },
        "datasets": datasets,
    }
    (DATA / "compare.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    (DATA / "compare.js").write_text(
        "window.VS_COMPARE = " + json.dumps(payload) + ";\n", encoding="utf-8")

    for n in notes:
        print("%-10s %-18s %s  (native %s, offset removed %+.3f)"
              % (n["id"], n["label"], n["span"], n["native_baseline"], n["offset_removed"]))


if __name__ == "__main__":
    main()
