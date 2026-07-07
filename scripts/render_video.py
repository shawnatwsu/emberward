"""Render Orbitfall to an MP4 — same data, same staging, same score idea as
orbit.html, reproduced offline with PIL + numpy + ffmpeg so no browser or
manual recording is needed.

Usage:  python scripts/render_video.py
Output: orbitfall.mp4 in the repo root (1280x720, 30 fps, with score).
"""
import json
import math
import pathlib
import struct
import subprocess
import sys
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[1]
W, H, FPS = 1280, 720, 30
MX, MY = 110, 80

# ---------------- data (mirrors orbit.html exactly) ----------------
data = json.loads((ROOT / "data" / "compare.json").read_text(encoding="utf-8"))
DS = data["datasets"]

def gaussian_smooth(arr, sigma=4):
    half = int(math.ceil(sigma * 3))
    out = []
    for i in range(len(arr)):
        s = w = 0.0
        for k in range(-half, half + 1):
            j = i + k
            if 0 <= j < len(arr):
                g = math.exp(-(k * k) / (2 * sigma * sigma))
                s += arr[j] * g
                w += g
        out.append(s / w)
    return out

tracks = []
for d in DS:
    S = gaussian_smooth(d["anoms"])
    n = len(S)
    R = [(S[min(n - 1, i + 1)] - S[max(0, i - 1)]) /
         (min(n - 1, i + 1) - max(0, i - 1)) * 10 for i in range(n)]
    tracks.append({"y0": d["years"][0], "S": S, "R": R, "A": d["anoms"],
                   "py": d["years"][-1] if d.get("partial_last") else -1})

y0 = min(t["y0"] for t in tracks)
y1 = max(t["y0"] + len(t["S"]) - 1 for t in tracks)
ENS = []
for y in range(y0, y1 + 1):
    pts = []
    for t in tracks:
        i = y - t["y0"]
        if 0 <= i < len(t["S"]):
            pts.append((t["S"][i], t["R"][i], t["A"][i], t["py"] == y))
    xs = [p[0] for p in pts]; vs = [p[1] for p in pts]; raws = [p[2] for p in pts]
    ENS.append({"y": y, "x": sum(xs) / len(xs), "v": sum(vs) / len(vs),
                "raw": sum(raws) / len(raws),
                "spread": (max(xs) - min(xs)) if len(xs) > 1 else 0.0,
                "n": len(pts), "partial": all(p[3] for p in pts)})
NY = len(ENS)

orbit_era = [e for e in ENS if 1880 <= e["y"] < 1970]
SUNX = sum(e["x"] for e in orbit_era) / len(orbit_era)
SUNV = sum(e["v"] for e in orbit_era) / len(orbit_era)
RING1 = max(math.hypot(e["x"] - SUNX, (e["v"] - SUNV) * 2.2) for e in orbit_era)

xmin = min(min(t["S"]) for t in tracks); xmax = max(max(t["S"]) for t in tracks)
vmin = min(min(t["R"]) for t in tracks); vmax = max(max(t["R"]) for t in tracks)
XD = (xmin - 0.12, xmax + 0.22); YD = (vmin - 0.05, vmax + 0.08)
def px(x): return MX + (x - XD[0]) / (XD[1] - XD[0]) * (W - 2 * MX)
def py(v): return H - MY - (v - YD[0]) / (YD[1] - YD[0]) * (H - 2 * MY)

def state_at(fy):
    i = max(0, min(NY - 1, int(fy)))
    j = min(NY - 1, i + 1); f = fy - i
    a, b = ENS[i], ENS[j]
    return {"y": a["y"] + f,
            "x": a["x"] + (b["x"] - a["x"]) * f,
            "v": a["v"] + (b["v"] - a["v"]) * f,
            "spread": a["spread"] + (b["spread"] - a["spread"]) * f, "n": a["n"]}

def planet_color(x):
    t = max(0.0, min(1.0, (x + 0.3) / 1.4))
    c1, c2 = (80, 160, 255), (255, 90, 45)
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))

CAPTIONS = [(1850, "three instruments are watching"),
            (1883, "Krakatoa dims the sky"),
            (1912, "the orbit holds"),
            (1944, "wartime warmth — still bound"),
            (1963, "Agung erupts; one last cool swing"),
            (1975, "the orbit breaks"),
            (1998, "a super El Niño, absorbed and exceeded"),
            (2016, "records now fall routinely"),
            (2024, "the hottest year ever measured")]

# ---------------- timeline ----------------
def speed(year): return 6.0 if year < 1968 else 2.1
frames = []
fy = 0.0
while fy < NY - 1:
    frames.append(fy)
    fy += speed(ENS[min(NY - 1, int(fy))]["y"]) / FPS
frames += [NY - 1] * int(2.5 * FPS)          # hold while the score fades
T = len(frames) / FPS
print(f"{len(frames)} frames, {T:.1f}s")

# ---------------- fonts & static base ----------------
FD = pathlib.Path("C:/Windows/Fonts")
def font(name, size):
    try: return ImageFont.truetype(str(FD / name), size)
    except OSError: return ImageFont.load_default()
F_YEAR = font("consolab.ttf", 62); F_STAT = font("consola.ttf", 15)
F_TICK = font("consola.ttf", 14); F_BOARD = font("consola.ttf", 15)
F_BT = font("consola.ttf", 12); F_CAP = font("georgiai.ttf", 24)

base = Image.new("RGB", (W, H), (5, 7, 12))
bd = ImageDraw.Draw(base, "RGBA")
gx = XD[0]
x = math.ceil(XD[0] / 0.25) * 0.25
while x <= XD[1]:
    bd.line([(px(x), MY * 0.6), (px(x), H - MY * 0.6)], fill=(150, 175, 205, 66), width=1)
    bd.text((px(x), H - MY * 0.6 + 10), f"{x:.2f}".replace("-0.00", "0.00"),
            font=F_TICK, fill=(195, 210, 225, 242), anchor="mt")
    x += 0.25
v = math.ceil(YD[0] / 0.1) * 0.1
while v <= YD[1]:
    bd.line([(MX * 0.55, py(v)), (W - MX * 0.55, py(v))], fill=(150, 175, 205, 66), width=1)
    bd.text((MX * 0.55 - 8, py(v)), f"{v:.1f}", font=F_TICK,
            fill=(195, 210, 225, 242), anchor="rm")
    v += 0.1
bd.text((W / 2, H - 22), "temperature anomaly (°C vs 1951–80)",
        font=F_TICK, fill=(195, 210, 225, 242), anchor="mm")
sx, sy = px(SUNX), py(SUNV)
for k in (0.55, 0.8, 1.05):   # orbit rings
    rx = (px(SUNX + RING1) - sx) * k
    ry = (sy - py(SUNV + RING1 / 2.2)) * k
    bd.ellipse([sx - rx, sy - ry, sx + rx, sy + ry], outline=(180, 200, 230, 26), width=1)
bd.line([(sx + 24, sy + 24), (sx + 52, sy + 52)], fill=(255, 215, 160, 90), width=1)
bd.text((sx + 58, sy + 46), 'the "sun" = the stable climate state',
        font=F_TICK, fill=(255, 220, 170, 217))
bd.text((sx + 58, sy + 64), "mean of 1880–1969, all six datasets",
        font=F_TICK, fill=(255, 220, 170, 140))
BASE = np.asarray(base).astype(np.uint16)

# ---------------- sprites (additive glows) ----------------
def radial_sprite(rad, color, peak):
    d = rad * 2
    yy, xx = np.mgrid[0:d, 0:d]
    r = np.hypot(xx - rad + 0.5, yy - rad + 0.5) / rad
    fall = np.clip(1 - r, 0, 1) ** 2.2 * peak
    return (fall[..., None] * np.array(color, dtype=float)).astype(np.uint16)

SUN_SPR = radial_sprite(95, (255, 205, 130), 1.0)
def add_sprite(arr, spr, cx, cy, scale=1.0):
    s = spr if scale == 1.0 else (spr.astype(float) * scale).astype(np.uint16)
    h, w = s.shape[:2]
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    ax0, ay0 = max(0, x0), max(0, y0)
    ax1, ay1 = min(W, x0 + w), min(H, y0 + h)
    if ax0 >= ax1 or ay0 >= ay1: return
    arr[ay0:ay1, ax0:ax1] += s[ay0 - y0:ay1 - y0, ax0 - x0:ax1 - x0]

rng = np.random.default_rng(42)
stars = [(rng.random() * W, rng.random() * H, rng.random() * 1.3 + 0.3,
          rng.random() * 6.28, 0.5 + rng.random() * 2) for _ in range(340)]

# ---------------- frame loop ----------------
tmp = pathlib.Path(tempfile.mkdtemp(prefix="orbitfall_"))
print("frames ->", tmp)
remnant = Image.new("RGB", (W, H), (0, 0, 0))
rd = ImageDraw.Draw(remnant)
drawn_year = 0
last_board_year, board = -1, []

for fi, f in enumerate(frames):
    s = state_at(f)
    yr = int(s["y"])
    # accumulate remnant segments once per data year
    while drawn_year < int(f):
        a, b = ENS[drawn_year + 1], ENS[drawn_year]
        c = planet_color(a["x"])
        rd.line([(px(b["x"]), py(b["v"])), (px(a["x"]), py(a["v"]))],
                fill=tuple(int(ch * 0.18) for ch in c), width=2)
        drawn_year += 1

    glow = remnant.copy()
    gd = ImageDraw.Draw(glow)
    tnow = fi / FPS
    for stx, sty, srad, stw, ssp in stars:   # twinkle
        aamp = 0.25 + 0.55 * abs(math.sin(stw + tnow * ssp))
        v255 = int(210 * aamp)
        gd.ellipse([stx - srad, sty - srad, stx + srad, sty + srad],
                   fill=(int(v255 * 0.9), int(v255 * 0.95), v255))
    k0 = max(1, int(f) - 50)                  # comet tail
    for k in range(k0, int(f) + 1):
        a, b = ENS[k], ENS[k - 1]
        age = (int(f) - k) / 50
        c = planet_color(a["x"])
        wdt = max(1, int((1 - age) * 6))
        gd.line([(px(b["x"]), py(b["v"])), (px(a["x"]), py(a["v"]))],
                fill=tuple(int(ch * (1 - age) * 0.55) for ch in c), width=wdt)

    arr = BASE + np.asarray(glow, dtype=np.uint16)
    pulse = 1 + 0.04 * math.sin(tnow * 1.4)
    add_sprite(arr, SUN_SPR, sx, sy, pulse)
    hx, hy = px(s["x"]), py(s["v"])
    if s["n"] > 1:                            # uncertainty halo
        halo_r = max(14, int((px(s["spread"]) - px(0)) / 2 + 14))
        add_sprite(arr, radial_sprite(halo_r, (43, 143, 242), 0.5), hx, hy)
    pc = planet_color(s["x"])
    add_sprite(arr, radial_sprite(26, pc, 0.9), hx, hy)

    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    dr = ImageDraw.Draw(im, "RGBA")
    dr.ellipse([hx - 9, hy - 9, hx + 9, hy + 9], fill=pc)   # planet body
    dr.ellipse([hx - 5, hy - 6, hx + 2, hy + 1],
               fill=tuple(min(255, ch + 70) for ch in pc))

    # HUD (kept clear of the x-axis tick row)
    dr.text((28, H - 140), str(yr), font=F_YEAR, fill=(242, 245, 248, 245))
    stat = (f"{s['x']:+.2f} °C · {s['v']:+.2f} °C/dec" +
            (f" · ±{s['spread']/2:.2f} °C across {s['n']} datasets" if s["n"] > 1 else ""))
    dr.text((30, H - 70), stat, font=F_STAT, fill=(182, 193, 204, 230))
    # leaderboard
    if yr != last_board_year:
        last_board_year = yr
        board = sorted((e for e in ENS if e["y"] <= yr),
                       key=lambda e: -e["raw"])[:5]
    dr.text((92, 22), "H O T T E S T   Y E A R S   S O   F A R",
            font=F_BT, fill=(124, 136, 148, 230))
    for i, e in enumerate(board):
        col = (244, 80, 42, 255) if e["y"] == yr else (242, 245, 248, 235)
        star = "*" if e["partial"] else ""
        dr.text((92, 46 + i * 20), f"{i+1}. {e['y']}{star}  {e['raw']:+.2f} °C",
                font=F_BOARD, fill=col)
    # caption
    best = None
    for cy, ct in CAPTIONS:
        d0 = abs(s["y"] - cy)
        if d0 < 5 and (best is None or d0 < best[0]): best = (d0, ct)
    if best:
        dr.text((W - 28, 28), best[1], font=F_CAP, anchor="ra",
                fill=(242, 245, 248, int(242 * max(0, 1 - best[0] / 5))))

    im.save(tmp / f"f{fi:05d}.png")
    if fi % 300 == 0: print(f"  frame {fi}/{len(frames)}")

# ---------------- score (same piece as the page, offline) ----------------
SR = 44100
N = int(T * SR)
t = np.arange(N) / SR
frame_times = np.arange(len(frames)) / FPS
anom = np.array([state_at(f)["x"] for f in frames])
I_t = np.interp(t, frame_times, np.clip((anom + 0.35) / 1.5, 0, 1))

def tri(freq, tt, bright):
    w = np.sin(2 * np.pi * freq * tt)
    w += bright / 9 * np.sin(2 * np.pi * 3 * freq * tt)
    w += bright / 25 * np.sin(2 * np.pi * 5 * freq * tt)
    return w

def note(buf, freq, t0, dur, vol, bright):
    i0, i1 = int(t0 * SR), min(N, int((t0 + dur) * SR))
    if i0 >= N: return
    tt = np.arange(i1 - i0) / SR
    env = np.minimum(1, tt / 0.06) * np.minimum(1, np.maximum(0, (dur - tt) / (dur * 0.3)))
    buf[i0:i1] += (tri(freq, tt, bright) + 0.35 * np.sin(2 * np.pi * 2 * freq * tt)) * env * vol

ARP = [220, 329.63, 440, 523.25, 659.25, 523.25, 440, 329.63]
CHORDS = [[220, 261.63, 329.63, 440], [174.61, 220, 261.63, 349.23]]
audio = np.zeros(N)
audio += 0.11 * (0.5 * np.sin(2 * np.pi * 55 * t) + 0.5 * np.sin(2 * np.pi * 55.2 * t)
                 + 0.22 * np.sin(2 * np.pi * 110 * t))
n = 0
while 0.1 + 0.4 * n < T - 0.5:
    t0 = 0.1 + 0.4 * n
    Ii = float(np.interp(t0, t, I_t))
    note(audio, ARP[n % 8], t0, 0.42, (0.05 + 0.28 * Ii) * 0.5, 0.2 + 0.8 * Ii)
    if n % 16 == 0:
        for fq in CHORDS[(n // 16) % 2]:
            note(audio, fq, t0, 6.8, (0.10 + 0.14 * Ii) * 0.16, 0.3)
    if n % 2 == 0:  # clock tick
        i0 = int(t0 * SR); i1 = min(N, i0 + int(0.03 * SR))
        tick = rng.standard_normal(i1 - i0)
        tick = np.diff(tick, prepend=0)                     # crude highpass
        audio[i0:i1] += tick * np.exp(-np.arange(i1 - i0) / (0.006 * SR)) \
                        * (0.05 + 0.07 * Ii) * 0.25
    n += 1
audio *= 0.9
audio *= np.minimum(1, t / 1.0)                             # fade in
audio *= np.minimum(1, np.maximum(0, (T - t) / 2.5))        # fade out
audio = np.clip(audio / max(1e-9, np.max(np.abs(audio))) * 0.85, -1, 1)
wav_path = tmp / "score.wav"
with wave.open(str(wav_path), "wb") as wf:
    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR)
    wf.writeframes((audio * 32767).astype(np.int16).tobytes())
print("score written")

# ---------------- mux ----------------
out = ROOT / "orbitfall.mp4"
def mux(vcodec_args):
    return subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(tmp / "f%05d.png"),
         "-i", str(wav_path)] + vcodec_args +
        ["-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)],
        capture_output=True, text=True)
r = mux(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19"])
if r.returncode != 0:
    print("libx264 unavailable, falling back to mpeg4")
    r = mux(["-c:v", "mpeg4", "-q:v", "3", "-pix_fmt", "yuv420p"])
if r.returncode != 0:
    sys.exit(r.stderr[-2000:])
print("wrote", out, f"({out.stat().st_size/1e6:.1f} MB)")
