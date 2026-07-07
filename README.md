# The Flattening Well

Climate change viewed as a dynamical system — a prototype for state-space
climate visualization.

Instead of plotting temperature against time, the centerpiece is a **phase
portrait**: global temperature anomaly (x) against warming rate (y). A stable
climate orbits a fixed point; the instrumental record shows the orbit breaking
out around 1970 and never looping back. Two companion panels make the
tipping-point argument tangible: an interactive fold bifurcation with
hysteresis (the reduced model of AMOC bistability), and critical-slowing-down
early-warning statistics (rolling variance and lag-1 autocorrelation) computed
in the browser from the real record.

## Data

| Source | Role | Coverage |
|---|---|---|
| [NASA GISTEMP v4](https://data.giss.nasa.gov/gistemp/) global annual means | primary record (anomaly vs 1951–80) | 1880 through last complete year |
| [ERA5 via C3S Climate Pulse](https://pulse.climate.copernicus.eu/) daily global 2 m temperature | running-year extension (anomaly vs 1991–2020, rebaselined) | 1940–present, ~2-day lag |

ERA5 anomalies are shifted onto GISTEMP's 1951–80 baseline by adding GISTEMP's
mean anomaly over 1991–2020 (ERA5's reference period). The build prints an
overlap consistency check (mean difference ≈ 0.01 °C over 86 complete years).

## Use

```
python scripts/build_data.py   # refresh data/series.json + data/series.js
start index.html               # open the page (any static server also works)
```

No dependencies beyond the Python standard library; the page is a single
static HTML file with no build step.

## Roadmap

1. Phase portrait of the AMOC fingerprint itself (EN4 / HadISST subpolar-gyre
   SST index) rather than global mean temperature.
2. Data-reconstructed potential landscape (Langevin / Fokker–Planck) — watch
   the well flatten in measurements.
3. Coupled tipping-element cascade graph with early-warning state as input.
