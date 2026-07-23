#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windgram_v2.py  --  cruscotto (dashboard) HTML+SVG del windgram.

Riusa TUTTA la fisica gia' validata importando windgram_arome.py (fetch, thermals
con W* Deardorff, orario corsa, scala verticale a bande). Aggiunge le aggregazioni
(stelle, finestra migliore, range) e genera un unico file .html con dentro un
grande <svg> con l'intera dashboard: header, colonna sintesi, grafico, legende,
tabella oraria, footer.

Uso:
  python3 windgram_v2.py --lat 46.087557 --lon 12.530206 \
      --name "Piancavallo - Antenne Castaldia" --start 9 --end 19 --out windgram.html

Richiede windgram_arome.py nella stessa cartella.
"""

import argparse
import sys
import html
import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import windgram_arome as W
# Strato 1 (fisica): la quota realisticamente raggiungibile e' stata estratta in
# windgram/core/climb.py (REFACTOR.md, C2) -- era fisica incastonata qui.
from windgram.core.climb import climb_ceiling, SINK_RATE  # noqa: F401

ROME_TZ = ZoneInfo("Europe/Rome")


# =========================================================================== #
# COLORI / SCALE
# =========================================================================== #
GRAD_STOPS = [(1.05, "#dc2b28"), (0.90, "#f0632a"), (0.65, "#f5b02a"),
              (0.48, "#f5e043"), (0.32, "#a3d945"), (0.16, "#26b357"),
              (0.00, "#3f9bdb"), (-0.20, "#525fcf")]

GRAD_CLASSES = [("Instabile", "> 0.9", "#dc2b28"),
                ("Buona", "0.65 - 0.9", "#f0632a"),
                ("Moderata", "0.32 - 0.65", "#a3d945"),
                ("Debole", "0 - 0.32", "#26b357"),
                ("Stabile", "< 0", "#3f9bdb")]

PINK = "#e5197f"
BLUEC = "#2f7fd0"
ICE = "#6fd0ea"
RAIN = "#3f9bdb"
INK = "#1b2a4a"
MUTE = "#5a6b86"

# classi di intensita' termica (W*, m/s) per la linea "quota raggiungibile":
# stessi 5 colori della legenda GRADIENTE TERMICO (presi da GRAD_CLASSES, qui in
# ordine crescente zero->molto forte) cosi' le due scale restano coerenti.
# Usate come CONTROL POINT per un gradiente continuo (`therm_color`), non a
# blocchi netti: il colore sfuma con fluidita' da una soglia all'altra.
THERM_CLASSES = [
    (0.0, 0.5, "Zero", GRAD_CLASSES[4][2]),          # blu (= Stabile)
    (0.5, 1.0, "Debole", GRAD_CLASSES[3][2]),        # verde (= Debole)
    (1.0, 2.0, "Sfruttabile", GRAD_CLASSES[2][2]),   # verde-giallo (= Moderata)
    (2.0, 3.0, "Forte", GRAD_CLASSES[1][2]),         # arancio (= Buona)
    (3.0, None, "Molto forte", GRAD_CLASSES[0][2]),  # rosso (= Instabile)
]
THERM_STOPS = [(lo, col) for lo, hi, _, col in THERM_CLASSES]


def therm_color(w):
    """Colore continuo (interpolato) per un valore di W*, sugli stessi 5
    control point/colori di THERM_CLASSES."""
    if w is None or (isinstance(w, float) and np.isnan(w)):
        return MUTE
    st = THERM_STOPS
    if w <= st[0][0]:
        return st[0][1]
    if w >= st[-1][0]:
        return st[-1][1]
    for i in range(len(st) - 1):
        lo, hi = st[i], st[i + 1]
        if lo[0] <= w <= hi[0]:
            t = (w - lo[0]) / (hi[0] - lo[0])
            return _lerp(lo[1], hi[1], t)
    return st[-1][1]


def therm_opacity(w, slope):
    """Trasparenza della linea: bassa intensita' (W*<1) = poco visibile;
    variabilita' locale alta (salita/discesa marcata) = riduce ulteriormente
    la visibilita' (termica meno "solida"); termica stabile = poco trasparente.
    mag: sotto W*=1 (soglia di "galleggiamento") resta smorzata 0.15-0.5; da
    W*=1 a 2.5 (gia' una bella termica) sale a piena visibilita' 0.5-1.0.
    W*<=0 (nessuna termica, tipico di notte) = invisibile del tutto: se non
    c'e' condizione non ha senso mostrare comunque un filo di linea."""
    if w is None or (isinstance(w, float) and np.isnan(w)):
        return 0.0
    if w <= 0:
        return 0.0
    mag = (0.15 + 0.35 * min(w, 1.0)) if w < 1.0 else (
        0.5 + 0.5 * float(np.clip((w - 1.0) / 1.5, 0.0, 1.0)))
    if slope is None or (isinstance(slope, float) and np.isnan(slope)):
        stab = 1.0
    else:
        stab = float(np.clip(1.0 - abs(slope) / 1.0, 0.45, 1.0))
    return float(np.clip(mag * stab, 0.0, 1.0))

# margine orizzontale ai due estremi della scala oraria del grafico (cosi' le
# barbe di vento a inizio/fine non escano dal plot). Unica fonte di verita':
# usata da build_chart (barbe/sfondo), e da build_svg per la fascia W* e la
# tabella in fondo, cosi' le colonne restano allineate alle ore qualunque sia
# nt (numero di ore) o la larghezza del plot.
HOUR_XPAD = 28.0


def hour_x(px, pw, nt, j, xpad=HOUR_XPAD):
    return px + xpad + (j / (nt - 1)) * (pw - 2 * xpad) if nt > 1 else px + pw / 2


def _lerp(c1, c2, t):
    a = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    b = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = [int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3)]
    return f"#{r[0]:02x}{r[1]:02x}{r[2]:02x}"


def grad_color(lr):
    if lr is None or (isinstance(lr, float) and np.isnan(lr)):
        return "#eceadf"
    stops = GRAD_STOPS
    if lr >= stops[0][0]:
        return stops[0][1]
    if lr <= stops[-1][0]:
        return stops[-1][1]
    for i in range(len(stops) - 1):
        hi, lo = stops[i], stops[i + 1]
        if lo[0] <= lr <= hi[0]:
            t = (hi[0] - lr) / (hi[0] - lo[0])
            return _lerp(hi[1], lo[1], t)
    return "#eceadf"


WSTAR_STOPS = [(0.0, "#3fb56a"), (0.6, "#b7d63f"), (1.0, "#f2c336"),
               (1.4, "#f2882b"), (1.8, "#e8542a"), (2.4, "#d62828")]


def wstar_color(w):
    if w is None or (isinstance(w, float) and np.isnan(w)):
        return "#cfd6df"
    st = WSTAR_STOPS
    if w <= st[0][0]:
        return st[0][1]
    if w >= st[-1][0]:
        return st[-1][1]
    for i in range(len(st) - 1):
        lo, hi = st[i], st[i + 1]
        if lo[0] <= w <= hi[0]:
            t = (w - lo[0]) / (hi[0] - lo[0])
            return _lerp(lo[1], hi[1], t)
    return "#cfd6df"


# =========================================================================== #
# AGGREGAZIONI (valori del cruscotto)
# =========================================================================== #
def _card16(deg):
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW",
            "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((deg % 360) / 22.5 + 0.5) % 16]


def aggregate(times, surf, zi, wstar, lcl, work_top, overdev, elev):
    nt = len(times)
    swr = surf["swr"]
    day = [j for j in range(nt)
           if swr is not None and not np.isnan(swr[j]) and swr[j] > 20]
    if not day:
        day = list(range(nt))

    def A(x):
        return np.array([x[j] for j in day], dtype=float)

    gust_kmh = A(surf["gust10"]) * 3.6 if surf["gust10"] is not None else np.zeros(len(day))
    cc = A(surf["cc_low"]) if surf["cc_low"] is not None else np.zeros(len(day))
    wt = A(work_top); ws_ = A(wstar); lc = A(lcl)
    precip = A(surf["precip"]) if surf["precip"] is not None else np.zeros(len(day))

    wmax = float(np.nanmax(ws_)) if len(ws_) else 0.0
    wmax = max(wmax, 1e-6)

    # top termica
    top_val = float(np.nanmax(wt))
    top_hour = times[day[int(np.nanargmax(wt))]].strftime("%H:%M")

    # base cumuli (ore con nuvole)
    cloudy = cc >= 10
    if cloudy.any():
        lcl_lo, lcl_hi = float(np.nanmin(lc[cloudy])), float(np.nanmax(lc[cloudy]))
    else:
        lcl_lo = lcl_hi = float(np.nanmedian(lc))
    spread = lcl_hi - lcl_lo
    lcl_q = "stabile" if spread < 300 else ("variabile" if spread < 600 else "molto variabile")

    # sviluppo cumuli
    if cloudy.any():
        cc_lo, cc_hi = int(np.nanmin(cc[cloudy])), int(np.nanmax(cc[cloudy]))
    else:
        cc_lo = cc_hi = 0
    ccmax = cc_hi
    dev_q = ("scarso" if ccmax < 20 else "buono" if ccmax < 70
             else "abbondante" if ccmax < 85 else "eccessivo")

    # stima della quota massima raggiunta dai cumuli (stessa formula della cima
    # convettiva disegnata nel grafico: work_top/zi + extra se sovrasviluppo)
    zi_ = A(zi)
    cape_ = A(surf["cape"]) if surf["cape"] is not None else np.zeros(len(day))
    ov_ = np.array([bool(overdev[j]) for j in day])
    if cloudy.any():
        idx = np.where(cloudy)[0]
        ctop_vals = np.where(
            ov_[idx],
            np.maximum(zi_[idx] + 800, lc[idx] + 1500 + np.nan_to_num(cape_[idx]) * 1.5),
            np.maximum(zi_[idx], lc[idx] + 250))
        cc_top = float(np.nanmax(ctop_vals))
    else:
        cc_top = float(np.nanmax(zi_)) if len(zi_) else elev

    # vento
    gmax = float(np.nanmax(gust_kmh)) if len(gust_kmh) else 0.0
    wind_q = ("debole" if gmax < 15 else "debole/moderato" if gmax < 28
              else "moderato" if gmax < 45 else "forte")
    if surf["ws10"] is not None:
        ws10 = A(surf["ws10"]); wd10 = A(surf["wd10"])
        u = np.nansum(ws10 * np.sin(np.deg2rad(wd10)))
        v = np.nansum(ws10 * np.cos(np.deg2rad(wd10)))
        wind_dir = _card16((np.degrees(np.arctan2(u, v))) % 360)
    else:
        wind_dir = "-"

    # punteggio stelle
    s_forza = np.clip(wmax / 2.2, 0, 1)
    s_quota = np.clip((top_val - elev) / 2000.0, 0, 1)
    s_vento = np.clip(1 - max(0, gmax - 20) / 30.0, 0.05, 1)
    good = np.sum((ws_ >= 0.6 * wmax) & (gust_kmh < 35))
    s_fin = np.clip(good / 6.0, 0, 1)
    base = 0.34 * s_forza + 0.26 * s_quota + 0.26 * s_vento + 0.14 * s_fin
    # penalita'
    central = [k for k, j in enumerate(day) if 11 <= times[j].hour <= 17]
    if central and any(overdev[day[k]] for k in central):
        base *= 0.75
    if len(precip) and np.nanmax(precip) > 0.3:
        base *= 0.60
    if len(cc) and np.nanmean(cc) > 85:
        base *= 0.85
    stars = float(np.clip(round(base * 5 * 2) / 2.0, 0.5, 5))
    judge = ("Ottime condizioni" if stars >= 4.5 else "Molto buone" if stars >= 4
             else "Buone" if stars >= 3 else "Discrete" if stars >= 2
             else "Deboli" if stars >= 1 else "Scarse")

    # finestra migliore (flyscore)
    fscore = []
    for k in range(len(day)):
        f_forza = ws_[k] / wmax
        gk = gust_kmh[k]
        f_vento = 1.0 if gk < 25 else (0.5 if gk < 35 else 0.15)
        f_ov = 0.3 if overdev[day[k]] else 1.0
        fscore.append(0.55 * f_forza + 0.25 * f_vento + 0.20 * f_ov)
    fscore = np.array(fscore)
    best = _best_block(fscore, thr=0.65)
    if best is None:
        kk = int(np.nanargmax(fscore))
        win = times[day[kk]].strftime("%H:%M")
    else:
        a, b = best
        t0 = times[day[a]] - dt.timedelta(minutes=30)
        t1 = times[day[b]] + dt.timedelta(minutes=30)
        win = f"{t0.strftime('%H:%M')} - {t1.strftime('%H:%M')}"

    return dict(stars=stars, judge=judge, top_val=int(round(top_val)),
                top_hour=top_hour, lcl_lo=int(round(lcl_lo / 10) * 10),
                lcl_hi=int(round(lcl_hi / 10) * 10), lcl_q=lcl_q,
                cc_lo=cc_lo, cc_hi=cc_hi, cc_top=int(round(cc_top / 10) * 10),
                dev_q=dev_q, wind_q=wind_q, wind_dir=wind_dir, window=win)


def _best_block(score, thr):
    best = None; cur = None
    for i, s in enumerate(score):
        if s >= thr:
            cur = (cur[0], i) if cur else (i, i)
        else:
            if cur and (best is None or cur[1] - cur[0] > best[1] - best[0]):
                best = cur
            cur = None
    if cur and (best is None or cur[1] - cur[0] > best[1] - best[0]):
        best = cur
    return best


# =========================================================================== #
# SVG helpers
# =========================================================================== #
def esc(s):
    return html.escape(str(s))


def rrect(x, y, w, h, r, fill, stroke="none", sw=1, extra=""):
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{r}" ry="{r}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw}" {extra}/>')


def txt(x, y, s, size=13, fill=INK, weight="normal", anchor="start",
        family="Inter, Segoe UI, sans-serif", extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}" text-anchor="{anchor}" '
            f'font-family="{family}" {extra}>{esc(s)}</text>')


def smooth_path(pts):
    """Catmull-Rom -> cubic bezier, path 'd' liscio."""
    if len(pts) < 2:
        return ""
    p = [pts[0]] + list(pts) + [pts[-1]]
    d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f} "
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1x = p1[0] + (p2[0] - p0[0]) / 6.0
        c1y = p1[1] + (p2[1] - p0[1]) / 6.0
        c2x = p2[0] - (p3[0] - p1[0]) / 6.0
        c2y = p2[1] - (p3[1] - p1[1]) / 6.0
        d += f"C {c1x:.1f} {c1y:.1f} {c2x:.1f} {c2y:.1f} {p2[0]:.1f} {p2[1]:.1f} "
    return d


def wind_barb(x, y, spd_kmh, deg, unit=10.0, L=26.0, col="#20344f"):
    """Barba centrata su (x,y) [la quota/ora esatta]: l'asta si estende meta'
    verso la provenienza e meta' in direzione opposta, cosi' il simbolo non
    "pende" tutto da un lato della quota di riferimento. Tutte le proporzioni
    (spessore, lunghezza barbe/pennant) scalano con L, cosi' si puo' rimpicciolire
    il simbolo (griglia fitta) senza snaturarne la forma."""
    if spd_kmh is None or np.isnan(spd_kmh):
        return ""
    sw = max(0.9, L * 0.06)
    if spd_kmh < 5:                                 # calma: solo pallino "o"
        r = max(1.8, L * 0.13)
        return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="none" '
                f'stroke="{col}" stroke-width="{sw:.2f}"/>')
    ang = np.deg2rad(deg)
    dx, dy = np.sin(ang), -np.cos(ang)             # verso provenienza (SVG y giu')
    ox, oy = x - dx * L / 2, y - dy * L / 2         # base asta: il centro cade su (x,y)
    ex, ey = x + dx * L / 2, y + dy * L / 2
    out = [f'<line x1="{ox:.1f}" y1="{oy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
           f'stroke="{col}" stroke-width="{sw:.2f}"/>']
    # perpendicolare (verso sinistra dell'asta)
    px, py = -dy, dx
    n50 = int(spd_kmh // 50); rem = spd_kmh - 50 * n50
    n10 = int(rem // 10); rem -= 10 * n10
    n5 = 1 if rem >= 4 else 0
    fl = L * 0.32
    pos = L * 0.91
    step50, step10, pbase = L * 0.36, L * 0.23, L * 0.27
    for _ in range(n50):                            # pennant (triangolo)
        bx, by = ox + dx * pos, oy + dy * pos
        tx, ty = bx + px * fl, by + py * fl
        bx2, by2 = ox + dx * (pos - pbase), oy + dy * (pos - pbase)
        out.append(f'<path d="M {bx:.1f} {by:.1f} L {tx:.1f} {ty:.1f} '
                   f'L {bx2:.1f} {by2:.1f} Z" fill="{col}"/>')
        pos -= step50
    for _ in range(n10):
        bx, by = ox + dx * pos, oy + dy * pos
        tx, ty = bx + px * fl, by + py * fl
        out.append(f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" '
                   f'stroke="{col}" stroke-width="{sw:.2f}"/>')
        pos -= step10
    for _ in range(n5):
        bx, by = ox + dx * pos, oy + dy * pos
        tx, ty = bx + px * fl * 0.5, by + py * fl * 0.5
        out.append(f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" '
                   f'stroke="{col}" stroke-width="{sw:.2f}"/>')
    return "".join(out)


def cloud_path(cx, cy, s, fill, stroke="#8592a6", sw=1.2, opacity=1.0, dash=None):
    """Nuvola stilizzata (sagoma chiusa) centrata in cx,cy, scala s."""
    # sagoma unitaria (base piatta, cima a festoni), centrata ~0
    pts = "M -1 0.32 C -1.25 0.32 -1.3 -0.1 -1.02 -0.16 C -1.05 -0.5 -0.55 -0.55 "\
          "-0.42 -0.28 C -0.32 -0.62 0.2 -0.62 0.28 -0.24 C 0.5 -0.5 0.98 -0.32 "\
          "0.82 -0.02 C 1.2 -0.02 1.2 0.32 0.85 0.32 Z"
    dash_a = f'stroke-dasharray="4 3"' if dash else ""
    return (f'<g transform="translate({cx:.1f} {cy:.1f}) scale({s:.1f})" '
            f'opacity="{opacity}"><path d="{pts}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw/s:.2f}" {dash_a}/></g>')


def star(cx, cy, r, kind):
    """kind: 'full' | 'half' | 'empty'."""
    pts = []
    for i in range(10):
        ang = -np.pi / 2 + i * np.pi / 5
        rr = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rr * np.cos(ang), cy + rr * np.sin(ang)))
    d = "M " + " L ".join(f"{p[0]:.1f} {p[1]:.1f}" for p in pts) + " Z"
    gold = "#f4b400"
    if kind == "full":
        return f'<path d="{d}" fill="{gold}"/>'
    if kind == "empty":
        return f'<path d="{d}" fill="#e3e6ec"/>'
    # half: clip
    return (f'<path d="{d}" fill="#e3e6ec"/>'
            f'<clipPath id="cl{int(cx)}{int(cy)}"><rect x="{cx-r:.1f}" '
            f'y="{cy-r:.1f}" width="{r:.1f}" height="{2*r:.1f}"/></clipPath>'
            f'<path d="{d}" fill="{gold}" clip-path="url(#cl{int(cx)}{int(cy)})"/>')


def stars_row(x, y, value, r=13, gap=30):
    out = []
    for i in range(5):
        frac = value - i
        kind = "full" if frac >= 0.75 else ("half" if frac >= 0.25 else "empty")
        out.append(star(x + i * gap, y, r, kind))
    return "".join(out)


# =========================================================================== #
# CHART (pannello centrale) in SVG
# =========================================================================== #
def _lapse_at(ez, lv, z):
    ez = ez[np.isfinite(ez)]
    if len(ez) < 2:
        return np.nan
    o = np.argsort(ez); ez = ez[o]
    if z < ez[0] or z > ez[-1]:
        return np.nan
    i = np.searchsorted(ez, z, side="right") - 1
    i = min(max(i, 0), len(lv) - 1)
    return lv[i]


# SINK_RATE e climb_ceiling (fisica: quota realisticamente raggiungibile) sono
# stati spostati in windgram/core/climb.py (REFACTOR.md, C2) e importati in cima.


def build_chart(times, levels, hwind, surf, elev, zi, wstar, lcl,
                overdev, top_agl, geom, shf15=None):
    px, py, pw, ph = geom
    nt = len(times)
    z2y, agl2y, top_agl, fr = W.make_vscale(elev, top_agl=top_agl)
    ztop = elev + top_agl
    edges, lr = W.lapse_grid(times, levels, surf, elev)

    def X(j):
        return hour_x(px, pw, nt, j)

    # margine verticale sopra/sotto: le bandierine delle barbe (asta + pennant)
    # sporgono qualche decina di px dal loro punto di ancoraggio: la riga barbe
    # piu' alta (top_agl) e quella piu' bassa (suolo) restano comunque ancorate
    # alla loro quota/ora esatta, solo compresse un po' dentro un'area colorata
    # (in alto) / la banda del suolo (in basso) piu' ampia, cosi' le bandierine
    # non escono mai dalla zona colorata.
    YPAD_TOP, YPAD_BOT = 26.0, 30.0
    ph_eff = ph - YPAD_TOP - YPAD_BOT

    def Yfrac(frac):
        return py + YPAD_TOP + (1 - frac) * ph_eff

    def Yz(z):
        z = min(max(float(z), elev), ztop)
        return Yfrac(float(z2y(z)))

    def Yagl(a):
        return Yfrac(float(agl2y(a)))

    defs, body = [], []

    # --- sfondo: una colonna per ora con gradiente verticale dal lapse ---
    # le colonne sono sfumate tra loro con una sfocatura orizzontale (clippata
    # al riquadro del plot), cosi' la mappa colore si legge come continua da
    # un'ora all'altra invece che a bande nette.
    blur_std = max(10.0, (pw / max(nt - 1, 1)) * 0.45)
    defs.append(f'<clipPath id="plotclip"><rect x="{px:.1f}" y="{py:.1f}" '
                f'width="{pw:.1f}" height="{ph:.1f}"/></clipPath>')
    defs.append(f'<filter id="hblur" x="-15%" y="0" width="130%" height="100%">'
                f'<feGaussianBlur stdDeviation="{blur_std:.1f} 0"/></filter>')
    bg = []
    zsamp = np.linspace(elev, ztop, 16)
    for j in range(nt):
        stops = []
        for z in zsamp:
            lrv = _lapse_at(edges[:, j], lr[:, j], z)
            off = (Yz(z) - py) / ph
            stops.append((off, grad_color(lrv)))
        stops.sort()
        gid = f"col{j}"
        sd = "".join(f'<stop offset="{o:.3f}" stop-color="{c}"/>' for o, c in stops)
        defs.append(f'<linearGradient id="{gid}" x1="0" y1="{py:.0f}" x2="0" '
                    f'y2="{py+ph:.0f}" gradientUnits="userSpaceOnUse">{sd}</linearGradient>')
        x0 = (X(j - 1) + X(j)) / 2 if j > 0 else px
        x1 = (X(j) + X(j + 1)) / 2 if j < nt - 1 else px + pw
        bg.append(f'<rect x="{x0:.1f}" y="{py:.1f}" width="{x1-x0:.1f}" '
                  f'height="{ph:.1f}" fill="url(#{gid})" fill-opacity="0.5"/>')
    body.append(f'<g filter="url(#hblur)" clip-path="url(#plotclip)">'
                f'{"".join(bg)}</g>')

    # --- zero termico stimato (quota isoterma 0 gradi) ---
    # disegnata subito dopo lo sfondo, PRIMA di griglia/barbe/nuvole/etichette:
    # resta in secondo piano, un riferimento di massima che non deve competere
    # con i dati operativi. Tratteggiata, sottile e semi-trasparente per lo
    # stesso motivo; i fiocchi di neve a ogni ora restano leggibili anche così.
    fzl = surf.get("fzl")
    if fzl is not None:
        pts_fzl = [(X(j), Yz(fzl[j])) for j in range(nt) if not np.isnan(fzl[j])]
        if len(pts_fzl) >= 2:
            body.append(f'<path d="{smooth_path(pts_fzl)}" fill="none" stroke="{ICE}" '
                        f'stroke-width="1.6" stroke-linecap="round" stroke-opacity="0.7" '
                        f'stroke-dasharray="5 4"/>')
            for j in range(nt):
                if not np.isnan(fzl[j]):
                    body.append(ic_snowflake(X(j), Yz(fzl[j])))

    # --- griglia + etichette Y (m slm) ---
    first50 = int(np.ceil((elev + 40) / 50.0) * 50)
    ymaj = [(0.0, int(round(elev))), (float(first50 - elev), first50)]
    ymin = []
    for lo, hi, fine, lab in [(0, 1000, 50, 200), (1000, 2000, 100, 500),
                              (2000, int(top_agl), 200, 1000)]:
        s = int(np.ceil((elev + lo) / fine) * fine)
        while s <= elev + hi + 1:
            agl = s - elev
            if 0 < agl <= top_agl and s != first50:
                mj = (s % lab == 0) and not (lo == 0 and abs(s - first50) < 150)
                (ymaj if mj else ymin).append((float(agl), s) if mj else float(agl))
            s += fine
    for a in ymin:
        y = Yagl(a)
        body.append(f'<line x1="{px-4:.1f}" y1="{y:.1f}" x2="{px:.1f}" y2="{y:.1f}" '
                    f'stroke="#9aa6b8" stroke-width="1"/>')
        body.append(f'<line x1="{px+pw:.1f}" y1="{y:.1f}" x2="{px+pw+4:.1f}" y2="{y:.1f}" '
                    f'stroke="#9aa6b8" stroke-width="1"/>')
    for a, v in ymaj:
        y = Yagl(a)
        # tiene le etichette estreme (in alto e in basso) dentro il riquadro del plot
        ty = min(max(y + 4, py + 11), py + ph - 3)
        body.append(f'<line x1="{px-7:.1f}" y1="{y:.1f}" x2="{px:.1f}" y2="{y:.1f}" '
                    f'stroke="#6b7789" stroke-width="1.4"/>')
        body.append(f'<line x1="{px+pw:.1f}" y1="{y:.1f}" x2="{px+pw+7:.1f}" y2="{y:.1f}" '
                    f'stroke="#6b7789" stroke-width="1.4"/>')
        body.append(txt(px + pw + 10, ty, v, 12, MUTE, anchor="start"))
        body.append(txt(px - 11, ty, v, 12, MUTE, anchor="end"))
    # banda suolo: dalla quota di decollo fino al bordo inferiore del plot, in
    # marrone chiaro -- e' la zona in cui possono sporgere le bandierine delle
    # barbe della riga piu' bassa, restando comunque dentro l'area colorata.
    gy = Yagl(0.0)
    body.append(f'<rect x="{px-4:.1f}" y="{gy:.1f}" width="{pw+4:.1f}" '
                f'height="{py+ph-gy:.1f}" fill="#ad8258" opacity="0.9"/>')
    # separatori bande
    for hb in (1000, 2000):
        y = Yagl(hb)
        body.append(f'<line x1="{px:.1f}" y1="{y:.1f}" x2="{px+pw:.1f}" y2="{y:.1f}" '
                    f'stroke="#6b7789" stroke-width="0.8" stroke-dasharray="6 4" '
                    f'opacity="0.5"/>')

    # --- etichette X (ore) ---
    for j in range(nt):
        body.append(txt(X(j), py + ph + 22, times[j].strftime("%H"), 13, INK,
                        "bold", "middle"))
    body.append(txt(px + pw / 2, py + ph + 44, "ORA LOCALE", 12, MUTE, "bold", "middle",
                    extra='letter-spacing="1.5"'))

    # --- barbe vento: righe scelte in base allo spazio in pixel disponibile ---
    # la scala verticale e' compressa a bande (vedi Yagl/make_vscale): un passo
    # fisso in metri stipa troppe righe nella banda alta. Si sceglie invece un
    # passo minimo in pixel (poco piu' della dimensione del simbolo) e si cammina
    # sulla quota finche' non si accumula quel gap, cosi' le righe restano sempre
    # non sovrapposte qualunque sia la compressione della banda (non serve essere
    # precisi sulla quota esatta di ciascuna riga).
    MIN_BARB_GAP_PX = 18.0
    fine = np.arange(0.0, top_agl, 10.0)
    fine = np.append(fine, top_agl)
    tgt = [0.0]
    last_y = Yagl(0.0)
    for a in fine[1:]:
        y = Yagl(a)
        if last_y - y >= MIN_BARB_GAP_PX:
            tgt.append(a)
            last_y = y
    if tgt[-1] != top_agl:
        tgt.append(top_agl)
    tgt = np.array(tgt)
    for j in range(nt):
        u, v = W.wind_profile(levels, hwind, surf, elev, j, tgt)
        if u is None:
            continue
        for k, a in enumerate(tgt):
            spd = np.hypot(u[k], v[k]) * 3.6
            deg = (np.degrees(np.arctan2(-u[k], -v[k]))) % 360
            yb = Yagl(a)
            body.append(wind_barb(X(j), yb, spd, deg, L=14, col="#243b57"))

    # --- nuvole: testa base, gambo, cima ---
    cc_low = surf["cc_low"] if surf["cc_low"] is not None else surf["cc"]
    cape = surf["cape"] if surf["cape"] is not None else np.zeros(nt)
    CLOUD_GAP = 25.0  # m: la base disegnata resta questo tanto sopra la lcl, cosi'
                       # non viene mai tagliata dalla linea della termica (<= lcl)
    for j in range(nt):
        if cc_low is None or np.isnan(cc_low[j]) or np.isnan(lcl[j]):
            continue
        if not (elev < lcl[j] < ztop) or cc_low[j] < 40:
            continue
        cc = float(cc_low[j])
        base = float(lcl[j])
        head = 15 + cc * 0.10
        # centro della sagoma: il suo bordo inferiore (a +head*0.32) cade esattamente
        # sulla quota base+CLOUD_GAP, non sulla lcl stessa
        yb = Yz(base + CLOUD_GAP) - head * 0.32
        if overdev[j]:
            ctop = min(ztop, max(zi[j] + 800, base + 1500 + np.nan_to_num(cape[j]) * 1.5))
        else:
            ctop = min(ztop, max(zi[j], base + 250))
        yt = Yz(ctop)
        g = _lerp("#f2f4f8", "#9aa6b6", min(cc / 100.0, 1))
        # gambo: largo e tenue (trasparenza); lo spessore cresce con quanto e'
        # "cattivo" lo sviluppo (copertura/sovrasviluppo), senza superare la base
        if yt < yb - 6:
            severity = min(1.0, cc / 100.0 + (0.25 if overdev[j] else 0.0))
            stem_w = min(head * 0.9, 3.0 + severity * (head * 0.9 - 3.0))
            body.append(f'<line x1="{X(j):.1f}" y1="{yb-8:.1f}" x2="{X(j):.1f}" '
                        f'y2="{yt+6:.1f}" stroke="#8592a6" stroke-width="{stem_w:.1f}" '
                        f'stroke-opacity="0.32" stroke-linecap="round" '
                        f'{"stroke-dasharray=\'4 3\'" if overdev[j] else ""}/>')
            # cima
            if overdev[j]:
                body.append(cloud_path(X(j), yt, 13, "none", "#33475f", 1.6, 1, dash=True))
                body.append(txt(X(j), yt + 4, "Cb", 9, "#33475f", "bold", "middle"))
            else:
                body.append(cloud_path(X(j), yt, 10, g, "#8592a6", 1.1, 0.9))
            body.append(txt(X(j), yt - 12, f"{int(round(ctop/10)*10)} m", 10, MUTE,
                            "normal", "middle"))
        # testa alla base: piu' trasparente quanto meno e' coperto il cielo,
        # opaca del tutto solo a copertura 100%
        head_op = min(1.0, 0.3 + 0.7 * (cc / 100.0))
        body.append(cloud_path(X(j), yb, head, g, "#6f7d90", 1.2, head_op))
        body.append(txt(X(j), yb + 4, f"{int(cc)}%", 12, "#20344f", "bold", "middle"))
        body.append(txt(X(j), yb + head * 0.32 + 15, f"{int(round(base/10)*10)} m", 10,
                        MUTE, "normal", "middle"))

    # --- quota realisticamente raggiungibile: gradiente SVG continuo ---
    # tiene conto dell'affondo dell'ala (SINK_RATE) e di come la termica si
    # indebolisce salendo verso zi (climb_ceiling). Usa lo stesso linguaggio
    # visivo (colore=intensita', trasparenza=stabilita') gia' validato: un vero
    # <linearGradient>, un colore/opacita' "puro" esattamente
    # ad ogni ora, sfumato con continuita' verso le ore vicine, senza gradini.
    climb_top = np.array([climb_ceiling(elev, zi[j], lcl[j], wstar[j])
                          for j in range(nt)])
    idxs = [j for j in range(nt) if not np.isnan(climb_top[j])]
    pts2 = [(X(j), Yz(climb_top[j])) for j in idxs]
    if len(pts2) >= 2:
        # variabilita' locale su una finestra di 15' prima/dopo (non piu' 1h
        # prima/dopo). boundary_layer_height/T2m/psurf non sono disponibili a
        # 15' su Open-Meteo (verificato: sempre null), quindi restano
        # interpolati linearmente dall'ora -- MA sensible_heat_flux SI' (varia
        # davvero ogni 15', non e' il dato orario ripetuto): se e' stato
        # scaricato (`shf15`), viene usato quello vero per ricalcolare un W*
        # locale piu' fedele; altrimenti si ripiega sulla semplice
        # interpolazione lineare del W* orario gia' calcolato.
        shf15_t, shf15_v = shf15 if shf15 else (None, None)

        def _interp(arr, t_frac):
            if arr is None:
                return np.nan
            t = min(max(t_frac, 0.0), nt - 1)
            i0 = int(np.floor(t)); i1 = min(i0 + 1, nt - 1)
            f = t - i0
            a, b = arr[i0], arr[i1]
            if np.isnan(a):
                return b
            if np.isnan(b):
                return a
            return a + (b - a) * f

        def _w_at(j, frac_h):
            t_frac = j + frac_h
            if shf15_t:
                # D dallo stesso `zi' gia' risolto da thermals() (blh reale se
                # disponibile, altrimenti il suo fallback a particella secca) --
                # NON dal blh grezzo, che qui puo' essere NaN per l'intera
                # finestra pur avendo zi/wstar orari validi (visto succedere).
                D = _interp(zi, t_frac) - elev
                T2 = _interp(surf.get("T2m"), t_frac)
                psurf = _interp(surf.get("psurf"), t_frac)
                swr = _interp(surf.get("swr"), t_frac)
                if not np.isnan(swr) and swr <= 20:
                    return 0.0
                if (not np.isnan(swr) and not np.isnan(D) and D > 50
                        and not np.isnan(T2)):
                    Tk = T2 + 273.15
                    rho = ((psurf * 100.0) / (287.0 * Tk)
                          if not np.isnan(psurf) else 1.12)
                    t_abs = times[0] + dt.timedelta(hours=t_frac)
                    k = min(range(len(shf15_t)),
                           key=lambda i: abs((shf15_t[i] - t_abs).total_seconds()))
                    qs = shf15_v[k]
                    if not np.isnan(qs):
                        wtheta = abs(qs) / (rho * 1005.0)
                        return (9.81 / Tk * wtheta * D) ** (1.0 / 3.0)
            return _interp(wstar, t_frac)          # ripiego: W* orario interpolato

        def _slope(j):
            return _w_at(j, 0.25) - _w_at(j, -0.25)

        gstops = []
        for j in idxs:
            w = wstar[j]
            off = (X(j) - px) / pw
            gstops.append(f'<stop offset="{off:.3f}" stop-color="{therm_color(w)}" '
                          f'stop-opacity="{therm_opacity(w, _slope(j)):.2f}"/>')
        defs.append(f'<linearGradient id="thermgrad" x1="{px:.1f}" y1="0" '
                    f'x2="{px+pw:.1f}" y2="0" gradientUnits="userSpaceOnUse">'
                    f'{"".join(gstops)}</linearGradient>')
        body.append(f'<path d="{smooth_path(pts2)}" fill="none" stroke="url(#thermgrad)" '
                    f'stroke-width="3.4" stroke-linecap="round"/>')

    # --- pioggia: barra verticale dalla sommita' del plot, una per ora ---
    # il dato e' un accumulo orario (niente sotto-orario): la larghezza resta
    # quindi fissa al 50% della colonna oraria (= "e' piovuto per un'ora intera"),
    # solo la profondita' scala con l'intensita'.
    precip = surf.get("precip")
    if precip is not None and np.nanmax(np.nan_to_num(precip)) > 0.05:
        pmax = max(float(np.nanmax(np.nan_to_num(precip))), 1.0)
        colw = (pw - 2 * HOUR_XPAD) / (nt - 1) if nt > 1 else pw
        bar_w = colw * 0.5
        for j in range(nt):
            if np.isnan(precip[j]) or precip[j] <= 0.05:
                continue
            depth = ph_eff * 0.32 * min(1.0, precip[j] / pmax)
            y1 = py + depth
            body.append(f'<line x1="{X(j):.1f}" y1="{py:.1f}" x2="{X(j):.1f}" '
                        f'y2="{y1:.1f}" stroke="{RAIN}" stroke-width="{bar_w:.1f}" '
                        f'stroke-opacity="0.55" stroke-linecap="butt"/>')
            body.append(txt(X(j), y1 + 14, f"{precip[j]:.1f} mm/h", 10, RAIN,
                            "bold", "middle"))

    # riquadro nota vento
    body.append(rrect(px + 8, py + 8, 168, 40, 6, "#ffffff", "#d7dce4", 1,
                      'opacity="0.92"'))
    body.append(txt(px + 18, py + 25, "VENTO IN QUOTA", 11, INK, "bold"))
    body.append(txt(px + 18, py + 40, "una barba = 10 km/h", 10, MUTE))

    return "".join(defs), "".join(body)


# =========================================================================== #
# LAYOUT COMPLETO
# =========================================================================== #
# ICONE (per la colonna sinistra)
# =========================================================================== #
def ic_thermal(cx, cy, col=PINK):
    return (f'<g transform="translate({cx} {cy})" fill="none" stroke="{col}" '
            f'stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="M -11 13 C -14 -1 -6 -11 6 -14"/>'
            f'<path d="M -1 -14 L 7 -14.5 L 6.5 -6"/>'
            f'<path d="M -1 15 C -4 3 4 -6 15 -9"/>'
            f'<path d="M 8 -9 L 16 -9.5 L 15.5 -1"/></g>')


def ic_wind(cx, cy, col=BLUEC):
    return (f'<g transform="translate({cx} {cy})" fill="none" stroke="{col}" '
            f'stroke-width="3" stroke-linecap="round">'
            f'<path d="M -15 -7 H 5 C 12 -7 12 -15 5.5 -14"/>'
            f'<path d="M -15 1 H 11 C 18 1 18 10 11 9"/>'
            f'<path d="M -15 9 H 1 C 7 9 7 16 1 15"/></g>')


def ic_cloud1(cx, cy):
    return cloud_path(cx, cy, 15, "#c3d8ee", "#7ba3ce", 1.4, 1.0)


def ic_cloud2(cx, cy):
    return (cloud_path(cx - 6, cy + 4, 12, "#e7ebf2", "#b4bece", 1.3, 1.0)
            + cloud_path(cx + 6, cy - 3, 14, "#d4dbe6", "#9aa6b8", 1.3, 1.0))


def ic_wind_s(cx, cy, col=BLUEC):
    return (f'<g transform="translate({cx} {cy})" fill="none" stroke="{col}" '
            f'stroke-width="2.1" stroke-linecap="round">'
            f'<path d="M -10 -5 H 4 C 9 -5 9 -11 3.5 -10"/>'
            f'<path d="M -10 1 H 8 C 13 1 13 7 8 6"/>'
            f'<path d="M -10 7 H 1 C 5 7 5 12 1 11"/></g>')


def ic_thermo(cx, cy, col="#d8433a"):
    return (f'<g transform="translate({cx} {cy})">'
            f'<rect x="-3" y="-11" width="6" height="15" rx="3" fill="none" '
            f'stroke="{col}" stroke-width="1.8"/>'
            f'<circle cx="0" cy="7" r="4.6" fill="{col}"/>'
            f'<rect x="-1.4" y="-4" width="2.8" height="10" rx="1.4" fill="{col}"/></g>')


def ic_snowflake(cx, cy, r=5.0, col=ICE):
    """Fiocco di neve stilizzato (3 assi incrociati, 6 punte): segna ogni ora
    sulla linea "zero termico stimato" per restare leggibile anche se sottile,
    tratteggiata e in secondo piano rispetto agli altri simboli del grafico."""
    out = []
    for i in range(3):
        ang = np.deg2rad(i * 60)
        dx, dy = r * np.cos(ang), r * np.sin(ang)
        out.append(f'<line x1="{cx-dx:.1f}" y1="{cy-dy:.1f}" x2="{cx+dx:.1f}" y2="{cy+dy:.1f}" '
                   f'stroke="{col}" stroke-width="1.1" stroke-linecap="round"/>')
    return "".join(out)


# =========================================================================== #
def build_svg(times, levels, hwind, surf, elev, zi, wstar, lcl,
              overdev, agg, name, model_label, run_label, top_agl,
              date_str, period_str, run_time_str, gen_time_str,
              lat, lon, shf15=None):
    Wpx, Hpx = 1500, 1000
    defs = ['<filter id="sh" x="-20%" y="-20%" width="140%" height="140%">'
            '<feDropShadow dx="0" dy="1.5" stdDeviation="3" flood-color="#1b2a4a" '
            'flood-opacity="0.10"/></filter>']
    S = []
    S.append(f'<rect width="{Wpx}" height="{Hpx}" fill="#f4f6fa"/>')

    # ---- HEADER ----
    S.append(txt(28, 46, name.split(" - ")[-1].upper(), 32, INK, "800"))
    S.append(txt(28, 72, f"Altitudine {int(elev)} m slm", 15, BLUEC, "bold"))
    S.append(txt(620, 40, date_str, 20, INK, "bold", "start"))
    S.append(txt(620, 66, period_str, 14, MUTE))
    # orari corsa modello, pulito (senza box scuro), allineato a destra.
    # "Prossimo aggiornamento" rimossa: la stima (corsa + 3h nominali) non e'
    # affidabile, ignora il ritardo reale di pubblicazione dei dati (vedi
    # DECISIONS.md) -- meglio non promettere un orario che spesso e' sbagliato.
    S.append(txt(1476, 40, f"Modello dati aggiornato alle {run_time_str}", 14, INK, "bold", "end"))
    S.append(txt(1476, 62, f"Grafico generato alle {gen_time_str}", 12, MUTE, "normal", "end"))

    # ---- COLONNA SINISTRA ----
    lx, lw = 24, 250
    S.append(rrect(lx, 100, lw, 724, 16, "#ffffff", "#e6eaf1", 1, 'filter="url(#sh)"'))
    # badge header
    S.append(rrect(lx + 12, 112, lw - 24, 34, 9, INK))
    S.append(txt(lx + lw / 2, 134, "STIMA GIORNATA", 13, "#ffffff", "bold",
                 "middle", extra='letter-spacing="0.5"'))
    # stelle grandi centrate
    S.append(stars_row(lx + lw / 2 - 4 * 17, 178, agg["stars"], r=16, gap=34))

    def divider(y):
        S.append(f'<line x1="{lx+18}" y1="{y:.0f}" x2="{lx+lw-18}" y2="{y:.0f}" '
                 f'stroke="#eaedf2" stroke-width="1.4"/>')

    def _tw(s, size):                        # stima larghezza testo (bold 800)
        return len(s) * size * 0.60

    def _wrap(s, maxw, size):
        toks = s.replace("/", "/ ").replace("\u2013", "\u2013 ").split(" ")
        toks = [t for t in toks if t]
        lines = [""]
        for t in toks:
            trial = (lines[-1] + " " + t).strip()
            if _tw(trial, size) <= maxw or lines[-1] == "":
                lines[-1] = trial
            else:
                lines.append(t)
        return [ln.replace("/ ", "/").replace("\u2013 ", "\u2013 ").strip()
                for ln in lines[:2]]

    def stat_row(cy, icon_svg, title, big, sub, color):
        S.append(icon_svg)
        tx = lx + 78
        maxw = (lx + lw - 14) - tx - 4       # larghezza utile a destra dell'icona
        S.append(txt(tx, cy - 20, title, 11.5, "#3a4a63", "bold",
                     extra='letter-spacing="0.3"'))
        # scegli il corpo piu' grande che stia in 1 riga; se nessuno, vai a capo
        size, lines = 21, _wrap(big, maxw, 21)
        if len(lines) > 1:
            size, lines = 18, _wrap(big, maxw, 18)
        if len(lines) == 1:
            S.append(txt(tx, cy + 4, lines[0], size, color, "800"))
            S.append(txt(tx, cy + 24, sub, 12, MUTE))
        else:
            S.append(txt(tx, cy - 2, lines[0], 18, color, "800"))
            S.append(txt(tx, cy + 17, lines[1], 18, color, "800"))
            S.append(txt(tx, cy + 35, sub, 12, MUTE))

    divider(204)
    y1, y2, y3, y4 = 278, 426, 574, 722
    stat_row(y1, ic_thermal(lx + 42, y1), "TOP TERMICA",
             f"{agg['top_val']} m", f"max ore {agg['top_hour']}", PINK)
    divider(352)
    stat_row(y2, ic_cloud1(lx + 42, y2), "BASE CUMULI (LCL)",
             f"{agg['lcl_lo']} \u2013 {agg['lcl_hi']} m", agg["lcl_q"], BLUEC)
    divider(500)
    stat_row(y3, ic_cloud2(lx + 42, y3), "SVILUPPO CUMULI",
             f"{agg['cc_lo']} \u2013 {agg['cc_hi']} %",
             f"{agg['dev_q']} \u00b7 fino a {agg['cc_top']} m", BLUEC)
    divider(648)
    stat_row(y4, ic_wind(lx + 42, y4), "VENTO",
             agg["wind_q"], f"da {agg['wind_dir']}", BLUEC)

    # ---- PANNELLO GRAFICO ----
    S.append(rrect(290, 100, 898, 724, 14, "#ffffff", "#e4e8ef", 1, 'filter="url(#sh)"'))
    geom = (372, 200, 720, 558)
    px, py, pw, ph = geom

    def Xh(j):
        return hour_x(px, pw, len(times), j)

    # --- FASCIA INTENSITA' TERMICA (sopra il plot, separata dalle barbe) ---
    S.append(txt(px, 138, "INTENSIT\u00c0 TERMICA ATTESA (core \u00d72)", 12, "#33465f",
                 "bold", extra='letter-spacing="0.4"'))
    # numeri W* per ora
    for j in range(len(times)):
        if not np.isnan(wstar[j]):
            S.append(txt(Xh(j), 166, f"{wstar[j]:.1f}", 12.5, "#2b3a52", "bold", "middle"))
    # barra colore intensita' (gradiente per ora)
    bar_y, bar_h = 174, 13
    gstops = "".join(
        f'<stop offset="{(j/(len(times)-1)):.3f}" stop-color="{wstar_color(wstar[j])}"/>'
        for j in range(len(times)))
    defs.append(f'<linearGradient id="wbar" x1="{px}" y1="0" x2="{px+pw}" y2="0" '
                f'gradientUnits="userSpaceOnUse">{gstops}</linearGradient>')
    S.append(rrect(px, bar_y, pw, bar_h, 4, "url(#wbar)", "#c9d0da", 0.8))

    cdefs, cbody = build_chart(times, levels, hwind, surf, elev, zi, wstar, lcl,
                               overdev, top_agl, geom, shf15)
    defs.append(cdefs)
    S.append(cbody)

    # ---- COLONNA DESTRA (legende) ----
    rx, rw = 1204, 272
    RB_TOP, RB_BOT, GAP = 100, 969, 16
    bh = (RB_BOT - RB_TOP - 2 * GAP) / 3.0
    b1, b2, b3 = RB_TOP, RB_TOP + bh + GAP, RB_TOP + 2 * (bh + GAP)

    # --- box 1: LEGENDA ---
    S.append(rrect(rx, b1, rw, bh, 16, "#ffffff", "#e6eaf1", 1, 'filter="url(#sh)"'))
    S.append(txt(rx + 22, b1 + 34, "LEGENDA", 14, INK, "bold",
                 extra='letter-spacing="0.5"'))
    ly = b1 + 78
    tstops = "".join(f'<stop offset="{(lo/THERM_STOPS[-1][0]):.3f}" stop-color="{col}"/>'
                     for lo, col in THERM_STOPS)
    defs.append(f'<linearGradient id="thermleg" x1="{rx+22}" y1="0" x2="{rx+58}" y2="0" '
                f'gradientUnits="userSpaceOnUse">{tstops}</linearGradient>')
    S.append(f'<line x1="{rx+22}" y1="{ly}" x2="{rx+58}" y2="{ly}" stroke="url(#thermleg)" '
             f'stroke-width="3.6" stroke-linecap="round"/>')
    S.append(txt(rx + 70, ly - 3, "Quota raggiungibile (stimata)", 12, INK))
    S.append(txt(rx + 70, ly + 11, "colore = intensità (W*)", 10, MUTE))
    S.append(txt(rx + 70, ly + 24, "trasparenza = stabilità", 10, MUTE))
    ly += 46
    S.append(cloud_path(rx + 40, ly, 13, "#c7cfda", "#6f7d90", 1.2))
    S.append(txt(rx + 70, ly + 4, "Copertura cumuli (%)", 12, INK))
    ly += 34
    S.append(cloud_path(rx + 40, ly, 12, "none", "#33475f", 1.4, 1, dash=True))
    S.append(txt(rx + 70, ly + 4, "Sviluppo verticale", 12, INK))
    ly += 34
    S.append(f'<line x1="{rx+22}" y1="{ly}" x2="{rx+58}" y2="{ly}" stroke="{ICE}" '
             f'stroke-width="3.6" stroke-linecap="round"/>')
    S.append(txt(rx + 70, ly + 4, "Zero termico stimato", 12, INK))

    # --- box 2: GRADIENTE TERMICO ---
    S.append(rrect(rx, b2, rw, bh, 16, "#ffffff", "#e6eaf1", 1, 'filter="url(#sh)"'))
    S.append(txt(rx + 22, b2 + 34, "GRADIENTE TERMICO", 14, INK, "bold"))
    S.append(txt(rx + 22, b2 + 52, "(\u0394T/100 m)", 11, MUTE))
    gy = b2 + 72
    gstep = (bh - 90) / len(GRAD_CLASSES)
    for nm, rng, col in GRAD_CLASSES:
        S.append(rrect(rx + 22, gy, 30, gstep - 8, 5, col))
        S.append(txt(rx + 64, gy + gstep / 2 - 3, nm, 13, INK, "bold"))
        S.append(txt(rx + 64, gy + gstep / 2 + 12, rng, 11, MUTE))
        gy += gstep

    # --- box 3: VENTO ---
    S.append(rrect(rx, b3, rw, bh, 16, "#ffffff", "#e6eaf1", 1, 'filter="url(#sh)"'))
    S.append(txt(rx + 22, b3 + 34, "VENTO", 14, INK, "bold"))
    S.append(txt(rx + 22, b3 + 52, "una barba = 10 km/h", 11, MUTE))
    wy = b3 + 78
    wstep = (bh - 96) / 5.0
    for spd, lab in [(50, "50 km/h"), (20, "20 km/h"), (10, "10 km/h"),
                     (5, "5 km/h"), (2, "< 5 km/h (calma)")]:
        S.append(wind_barb(rx + 42, wy, spd, 270, L=24, col="#243b57"))
        S.append(txt(rx + 96, wy + 4, lab, 12, INK))
        wy += wstep

    # ---- TABELLA (colonne allineate alle ore del grafico) ----
    tgx, tgy, tgw, tgh = geom                       # geometria del grafico
    tx, ty, tw, th = 24, 838, 1164, 131
    S.append(rrect(tx, ty, tw, th, 16, "#ffffff", "#e6eaf1", 1, 'filter="url(#sh)"'))
    nt = len(times)

    def TX(j):                                      # STESSE ascisse delle ore
        return hour_x(tgx, tgw, nt, j)

    ws10 = surf["ws10"]; g10 = surf["gust10"]; T2 = surf["T2m"]; wd = surf["wd10"]
    rows = [("wind", ic_wind_s, "VENTO SUOLO", "med/raff (km/h)"),
            ("dir", ic_wind_s, "DIR. VENTO SUOLO", None),
            ("temp", ic_thermo, "T SUOLO (\u00b0C)", None)]
    rh = (th - 20) / 3.0
    for ri, (key, icon, lab1, lab2) in enumerate(rows):
        ry = ty + 12 + rh * (ri + 0.5)
        if ri > 0:
            S.append(f'<line x1="{tx+16}" y1="{ty+12+rh*ri:.0f}" x2="{tx+tw-16}" '
                     f'y2="{ty+12+rh*ri:.0f}" stroke="#eef1f5" stroke-width="1.4"/>')
        icol = "#d8433a" if key == "temp" else BLUEC
        S.append(icon(tx + 40, ry, icol))
        if lab2:
            S.append(txt(tx + 66, ry - 4, lab1, 11.5, "#2b3a52", "bold"))
            S.append(txt(tx + 66, ry + 11, lab2, 10, MUTE))
        else:
            S.append(txt(tx + 66, ry + 4, lab1, 11.5, "#2b3a52", "bold"))
        for j in range(nt):
            cx = TX(j)
            if key == "wind" and ws10 is not None and not np.isnan(ws10[j]):
                gk = (g10[j] * 3.6) if (g10 is not None and not np.isnan(g10[j])) else ws10[j] * 3.6
                S.append(txt(cx, ry + 4, f"{ws10[j]*3.6:.0f}/{gk:.0f}", 12,
                             _gust_col(gk), "bold", "middle"))
            elif key == "dir" and wd is not None and not np.isnan(wd[j]):
                S.append(txt(cx, ry + 4, _card16(wd[j]), 12, "#33465f", "bold", "middle"))
            elif key == "temp" and T2 is not None and not np.isnan(T2[j]):
                S.append(txt(cx, ry + 4, f"{T2[j]:.0f}\u00b0", 12, INK, "normal", "middle"))

    # ---- FOOTER ----
    foot = (f"Fonte: Open-Meteo ({model_label}).  "
            + (f"Corsa: {run_label}.  " if run_label else "")
            + f"Barbe in km/h.  W* Deardorff da flusso + PBL ICON-D2.  "
            f"Decollo {int(elev)} m slm.  Coordinate: {lat:.6f}, {lon:.6f}.")
    S.append(txt(28, 990, foot, 10, "#8792a6"))

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {Wpx} {Hpx}" '
           f'font-family="Inter, Segoe UI, Arial, sans-serif">'
           f'<defs>{"".join(defs)}</defs>{"".join(S)}</svg>')
    return svg


def _gust_col(gk):
    return ("#c0392b" if gk >= 45 else "#d35400" if gk >= 30
            else "#e08a1e" if gk >= 20 else "#2c3e50")


# =========================================================================== #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, default=46.087557)
    ap.add_argument("--lon", type=float, default=12.530206)
    ap.add_argument("--elev", type=float, default=None)
    ap.add_argument("--name", default="Piancavallo - Antenne Castaldia")
    ap.add_argument("--start", type=int, default=9)
    ap.add_argument("--end", type=int, default=19)
    ap.add_argument("--top-agl", type=float, default=5000)
    ap.add_argument("--model", default="icon_d2")
    ap.add_argument("--out", default="windgram.html")
    args = ap.parse_args()

    try:
        data = W.fetch(args.lat, args.lon, args.model)
    except Exception as e:
        print(f"Errore fetch API: {e}", file=sys.stderr); sys.exit(1)
    times, levels, hwind, surf, grid_elev = W.to_grid(data, args.start, args.end)
    elev = args.elev if args.elev is not None else W.fetch_elevation(args.lat, args.lon)
    if elev is None:
        elev = grid_elev if grid_elev is not None else 1098.0
    print(f"Quota decollo: {elev:.0f} m slm")
    if len(levels) < 3:
        print("Pochi livelli validi.", file=sys.stderr); sys.exit(2)

    zi, wstar, lcl, work_top, overdev = W.thermals(times, levels, surf, elev)
    agg = aggregate(times, surf, zi, wstar, lcl, work_top, overdev, elev)

    # flusso di calore sensibile a 15' (per rifinire la stabilita' della
    # "quota raggiungibile"); se non disponibile si ripiega silenziosamente
    # sulla sola interpolazione del W* orario (vedi build_chart)
    shf15 = W.fetch_shf15(args.lat, args.lon, args.model)
    if shf15[0] is None:
        print("Flusso 15' non disponibile, uso interpolazione oraria.", file=sys.stderr)

    init = W.fetch_model_run(args.model)
    if init is not None:
        age = (dt.datetime.now(dt.timezone.utc) - init).total_seconds() / 3600
        run_label = f"corsa {init:%d %b %H:%M} UTC ({age:.0f} h fa)"
        run_time_str = f"{init.astimezone(ROME_TZ):%H:%M}"
    else:
        run_label = None
        run_time_str = "n/d"
    gen_time_str = f"{dt.datetime.now(ROME_TZ):%H:%M}"

    labels_map = {"icon_d2": "ICON-D2 · 2.2 km",
                  "italia_meteo_arpae_icon_2i": "ICON-2I · 2 km",
                  "icon_eu": "ICON-EU · 7 km"}
    model_label = labels_map.get(args.model, args.model)
    months = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
              "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    wd = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
    d0 = times[0]
    date_str = f"{wd[d0.weekday()].capitalize()} {d0.day} {months[d0.month]} {d0.year}"
    period_str = f"{args.start:02d}:00 - {args.end:02d}:00 (ora locale)"

    svg = build_svg(times, levels, hwind, surf, elev, zi, wstar, lcl,
                    overdev, agg, args.name, model_label, run_label, args.top_agl,
                    date_str, period_str, run_time_str, gen_time_str,
                    args.lat, args.lon, shf15)
    page = (f'<!doctype html><html lang="it"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{esc(args.name)} - windgram</title>'
            f'<style>body{{margin:0;background:#e9edf3;}}'
            f'.wrap{{max-width:1500px;margin:0 auto;}}svg{{width:100%;height:auto;}}'
            f'</style></head><body><div class="wrap">{svg}</div></body></html>')
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Salvato: {args.out}")


if __name__ == "__main__":
    main()
