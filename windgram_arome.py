#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windgram_arome.py  (v4)
-----------------------
Windgram tempo-quota stile FIVL/RASP dai dati AROME France HD (~1.3 km) via
Open-Meteo, con asse verticale RIFERITO AL DECOLLO (AGL) a 3 bande e barbe del
vento (in nodi) su griglia regolare: una barba a ogni incrocio ora x quota.

Asse verticale (default):
  * 0-1000 m sopra il decollo  -> 45% dello spazio (max dettaglio)
  * 1000-2000 m                -> 25%
  * 2000-5000 m                -> 30% (compresso)

Sotto le ore: vento al suolo medio/raffica (km/h) e temperatura al suolo (C).
Il grafico parte dalla quota TERRENO reale (DEM 90 m Open-Meteo).
W*, top BL e TCU sono STIME, NON output RASP.
"""

import argparse
import sys
import datetime as dt

import numpy as np
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
import matplotlib.patheffects as pe
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm, Normalize
from matplotlib.path import Path
from scipy.interpolate import PchipInterpolator

# Strato 0 (sorgenti dati) spostato in windgram/sources/openmeteo.py nel
# refactoring a strati (REFACTOR.md, B1). Costanti e funzioni fetch/to_grid sono
# ri-esportate qui per non rompere il codice esistente: windgram_v2 e i tool
# usano W.fetch, W.to_grid, W.fetch_elevation, ... via questo modulo.
from windgram.sources.openmeteo import (  # noqa: F401,E402
    PLEVELS, HLEVELS, API, ELEV_API, META_PATH,
    build_params, fetch, fetch_elevation, fetch_shf15, fetch_model_run, to_grid)
# Strato 1 (fisica) spostato in windgram/core/thermals.py (REFACTOR.md, C1),
# ri-esportato qui per compatibilita' (windgram_v2 usa W.thermals, W.lapse_grid,
# W.wind_profile, W.make_vscale, W.lcl_height).
from windgram.core.thermals import (  # noqa: F401,E402
    lapse_grid, lcl_height, thermals, wind_profile, make_vscale)

# tacche verticali (m AGL): tutte -> barbe + tick; solo MAJOR -> etichetta
ALL_TICKS = [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000,
             1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000,
             2500, 3000, 3500, 4000, 4500, 5000]
MAJOR_TICKS = [0, 200, 400, 600, 800, 1000, 1200, 1400, 1600, 1800, 2000,
               3000, 4000, 5000]
BARB_AGL = [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000,
            1200, 1400, 1600, 1800, 2000, 2500, 3000, 3500, 4000, 4500, 5000]


# --------------------------------------------------------------------------- #
# Strato 0 (FETCH) e parsing (to_grid) spostati in windgram/sources/openmeteo.py
# nel refactoring (REFACTOR.md, B1). Restano invocabili via lo shim in cima.
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# DERIVATI (fisica) spostati in windgram/core/thermals.py (REFACTOR.md, C1).
# Restano invocabili via lo shim in cima (W.thermals, W.lapse_grid, ...).
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# 5. PLOT
# --------------------------------------------------------------------------- #
def make_colormap():
    colors = [(0.35, 0, 0.5), (0, 0, 0.8), (0, 0.7, 0.9), (0.1, 0.7, 0.2),
              (0.7, 0.9, 0.1), (1, 0.8, 0), (0.95, 0.45, 0), (0.8, 0.1, 0.1)]
    return LinearSegmentedColormap.from_list("fivl", colors, N=256)


def _cloud_path():
    """Sagoma di nuvola stilizzata: UN solo path chiuso (base piatta, cima a
    festoni). Nessuna sovrapposizione -> riempimento pulito."""
    MO, C4, LT, CP = Path.MOVETO, Path.CURVE4, Path.LINETO, Path.CLOSEPOLY
    v = [(-0.95, 0.0)]; c = [MO]
    v += [(0.95, 0.0)]; c += [LT]
    v += [(1.20, 0.02), (1.20, 0.52), (0.72, 0.54)]; c += [C4, C4, C4]
    v += [(0.92, 0.86), (0.40, 0.92), (0.34, 0.58)]; c += [C4, C4, C4]
    v += [(0.34, 1.02), (-0.20, 1.02), (-0.16, 0.60)]; c += [C4, C4, C4]
    v += [(-0.10, 0.90), (-0.62, 0.90), (-0.60, 0.54)]; c += [C4, C4, C4]
    v += [(-0.86, 0.66), (-1.22, 0.36), (-0.95, 0.0)]; c += [C4, C4, C4]
    v += [(-0.95, 0.0)]; c += [CP]
    v = np.array(v, float)
    p = Path(v, np.array(c))
    poly = p.to_polygons()[0]
    x, y = poly[:, 0], poly[:, 1]
    a = x[:-1] * y[1:] - x[1:] * y[:-1]
    A = a.sum() / 2.0
    cx = ((x[:-1] + x[1:]) * a).sum() / (6 * A)
    cy = ((y[:-1] + y[1:]) * a).sum() / (6 * A)
    v[:, 0] -= cx; v[:, 1] -= cy
    return Path(v, np.array(c))

CLOUD = _cloud_path()


def _smooth(x, y, n=240):
    """Curva morbida (PCHIP) sui punti validi; ritorna (xf, yf)."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 3:
        return x[m], y[m]
    xs, ys = x[m], y[m]
    o = np.argsort(xs); xs, ys = xs[o], ys[o]
    xs, idx = np.unique(xs, return_index=True); ys = ys[idx]
    if len(xs) < 3:
        return xs, ys
    xf = np.linspace(xs.min(), xs.max(), n)
    try:
        return xf, PchipInterpolator(xs, ys)(xf)
    except Exception:
        return xs, ys



def _draw_cb(ax, x, ybase, ytop, warn=True):
    """Disegna un cumulo torreggiante con incudine tra ybase e ytop (coord y
    display). Rappresenta il sovrasviluppo (TCU/Cb)."""
    ytop = max(ytop, ybase + 0.05)
    ymid = 0.5 * (ybase + ytop)
    ec = "darkred" if warn else "0.3"
    # colonna (torre)
    col = [(x - 0.16, ybase), (x + 0.16, ybase), (x + 0.13, ymid),
           (x + 0.13, ytop - 0.03), (x - 0.13, ytop - 0.03), (x - 0.13, ymid)]
    ax.add_patch(plt.Polygon(col, closed=True, facecolor="0.72",
                             edgecolor=ec, lw=0.8, alpha=0.85, zorder=5))
    # incudine (trapezio che si allarga in cima)
    anv = [(x - 0.14, ytop - 0.05), (x + 0.14, ytop - 0.05),
           (x + 0.40, ytop), (x + 0.30, ytop + 0.022),
           (x - 0.30, ytop + 0.022), (x - 0.40, ytop)]
    ax.add_patch(plt.Polygon(anv, closed=True, facecolor="0.6",
                             edgecolor=ec, lw=0.9, alpha=0.9, zorder=5))
    ax.text(x, ybase - 0.018, "Cb", fontsize=6, ha="center", va="top",
            color=ec, fontweight="bold", zorder=6)

def plot(times, levels, hwind, surf, elev, name, out, top_agl=5000.0,
         model_label="ICON-D2 ~2.2 km", wind_unit="kmh", run_label=None):
    uf = 3.6 if wind_unit == "kmh" else 1.94384
    ulab = "km/h" if wind_unit == "kmh" else "nodi"
    edges, lr = lapse_grid(times, levels, surf, elev)
    zi, wstar, lcl, work_top, overdev = thermals(times, levels, surf, elev)
    z_to_y, agl_to_y, top_agl, fr = make_vscale(elev, top_agl=top_agl)

    nt = len(times)
    hours = np.arange(nt)
    xlabels = [t.strftime("%H") for t in times]
    ztop = elev + top_agl
    Ymax = 1.0

    def Y(z):
        return z_to_y(np.clip(np.asarray(z, float), elev, ztop))

    fig = plt.figure(figsize=(12.5, 10.2))
    ax = fig.add_axes([0.11, 0.26, 0.78, 0.60])
    cmap = make_colormap()
    cnorm = Normalize(vmin=-0.2, vmax=1.05)

    # -- sfondo gradiente termico FLUIDO (gouraud), ancorato al suolo --
    def col_profile(j):
        ez = edges[:, j]
        ll = lr[:, j]
        fe = np.isfinite(ez)
        mids = 0.5 * (ez[:-1] + ez[1:])
        ok = np.isfinite(mids) & np.isfinite(ll)
        mids, llv = mids[ok], ll[ok]
        if len(mids) < 2:
            return None, None
        o = np.argsort(mids); mids, llv = mids[o], llv[o]
        ztopcol = np.nanmax(ez[fe])
        zpts = np.concatenate([[elev], mids, [ztopcol]])
        lpts = np.concatenate([[llv[0]], llv, [llv[-1]]])
        zpts, idx = np.unique(zpts, return_index=True)
        return zpts, lpts[idx]

    znodes = np.linspace(elev, ztop, 260)
    ynodes = Y(znodes)
    F = np.full((len(znodes), nt), np.nan)
    for j in range(nt):
        zp, lp = col_profile(j)
        if zp is None:
            continue
        F[:, j] = np.interp(znodes, zp, lp, left=lp[0], right=lp[-1])
    # densificazione orizzontale per transizioni morbide
    hf = np.linspace(0, nt - 1, (nt - 1) * 8 + 1)
    Ff = np.empty((len(znodes), len(hf)))
    for i in range(len(znodes)):
        Ff[i] = np.interp(hf, hours, F[i])
    Hm, Ym = np.meshgrid(hf, ynodes)
    pcm = ax.pcolormesh(Hm, Ym, Ff, shading="gouraud", cmap=cmap, norm=cnorm,
                        zorder=1)

    # -- barbe vento su griglia regolare (una a ogni incrocio) --
    agl_targets = np.array(BARB_AGL, float)
    ytar = np.array([float(agl_to_y(a)) for a in agl_targets])
    for j in range(nt):
        u_i, v_i = wind_profile(levels, hwind, surf, elev, j, agl_targets)
        if u_i is None:
            continue
        ax.barbs(np.full_like(ytar, hours[j]), ytar,
                 u_i * uf, v_i * uf, length=4.6, linewidth=0.5,
                 color="black", zorder=3, rounding=False)

    # -- quota di congelamento: linea morbida + fiocco a OGNI ora --
    fzl = surf["fzl"]
    if fzl is not None:
        yf = np.where((fzl >= elev) & (fzl <= ztop), Y(fzl), np.nan)
        xs, ys = _smooth(hours, yf)
        ax.plot(xs, ys, color="white", lw=2.2, zorder=4)
        ax.plot(xs, ys, color="navy", lw=1.0, ls="--", zorder=4)
        for j in range(nt):
            if elev <= fzl[j] <= ztop:
                ax.text(hours[j], Y(fzl[j]), "\u2744", fontsize=23,
                        ha="center", va="center", color="white", zorder=5,
                        path_effects=[pe.withStroke(linewidth=1.6,
                                                    foreground="#20406a")])

    # -- linee morbide: LCL, top BL, top operativo --
    def smline(vals, **kw):
        xs, ys = _smooth(hours, Y(vals))
        ax.plot(xs, ys, **kw)
    smline(lcl, color="#00a5d6", lw=1.8, ls=":", zorder=4)
    smline(work_top, color="magenta", lw=2.6, zorder=5)
    # handle di legenda
    ax.plot([], [], color="#00a5d6", lw=1.8, ls=":", label="Base cumuli (LCL)")
    ax.plot([], [], color="magenta", lw=2.6, label="Top termica operativo (no nube)")

    # -- nuvole: base (LCL) + cima (BL top o convettiva), con quota base --
    cc_low = surf["cc_low"] if surf["cc_low"] is not None else surf["cc"]
    cape = surf["cape"] if surf["cape"] is not None else np.zeros(nt)
    halo = [pe.withStroke(linewidth=1.4, foreground="white")]
    for j in range(nt):
        if cc_low is None or np.isnan(cc_low[j]) or np.isnan(lcl[j]):
            continue
        if not (elev < lcl[j] < ztop) or cc_low[j] < 10:
            continue
        cc = float(cc_low[j])
        base = float(lcl[j])
        yb = float(Y(base))
        yc = min(yb + 0.03, Ymax - 0.05)          # puff alla base
        s = 3200 + 22 * cc
        g = max(0.60, 0.95 - 0.35 * cc / 100.0)

        # cima della nube: convettiva se sovrasviluppo, altrimenti top BL
        if overdev[j]:
            ctop = min(ztop, max(zi[j] + 800,
                                 base + 1500 + np.nan_to_num(cape[j]) * 1.5))
        else:
            ctop = min(ztop, max(zi[j], base + 250))
        yt = min(float(Y(ctop)), Ymax - 0.02)

        # corpo nube (colonna translucida base->cima)
        if yt > yc + 0.02:
            ax.add_patch(plt.Rectangle((hours[j] - 0.10, yc), 0.20, yt - yc,
                                       facecolor=str(round(g, 2)), edgecolor="none",
                                       alpha=0.28, zorder=4))
            ax.plot([hours[j], hours[j]], [yc + 0.015, yt - 0.01],
                    color="0.3", lw=0.7,
                    ls=(0, (2, 2)) if overdev[j] else "-", alpha=0.6, zorder=4)

        # puff alla base con % copertura
        ax.scatter([hours[j]], [yc], marker=CLOUD, s=s, facecolor=str(round(g, 2)),
                   edgecolor="0.5", linewidth=0.8, alpha=0.62, zorder=5)
        tc = "0.15" if cc < 70 else "black"
        ax.text(hours[j], yc, f"{int(cc)}%", fontsize=8.5, ha="center",
                va="center", color=tc, fontweight="bold", zorder=6)

        # quota base cumulo (m slm) SOTTO la nuvola
        ax.text(hours[j], yb - 0.014, f"{int(round(base / 10) * 10)} m",
                fontsize=6.5, ha="center", va="top", color="#14315c",
                fontweight="bold", zorder=6, path_effects=halo)

        # marcatore della CIMA (limite superiore della nube)
        if yt > yc + 0.03:
            if overdev[j]:
                ax.scatter([hours[j]], [yt], marker=CLOUD, s=s * 1.05,
                           facecolor="none", edgecolor="0.12", linewidths=1.3,
                           linestyle="--", zorder=5)
                ax.text(hours[j], yt, "Cb", fontsize=6, ha="center", va="center",
                        color="0.1", fontweight="bold", zorder=6)
            else:
                ax.scatter([hours[j]], [yt], marker=CLOUD, s=s * 0.6,
                           facecolor=str(round(g, 2)), edgecolor="0.45",
                           linewidth=0.7, alpha=0.5, zorder=5)
            # quota cima (m slm) sopra la cima
            ax.text(hours[j], yt + 0.016, f"{int(round(ctop / 10) * 10)} m",
                    fontsize=6, ha="center", va="bottom", color="0.25",
                    zorder=6, path_effects=halo)

    # -- precipitazione (bordo alto) --
    precip = surf["precip"]
    if precip is not None and np.nanmax(precip) > 0.05:
        pmax = max(np.nanmax(precip), 1.0)
        for j in range(nt):
            if not np.isnan(precip[j]) and precip[j] > 0.05:
                bh = 0.13 * (precip[j] / pmax)
                ax.plot([hours[j], hours[j]], [Ymax, Ymax - bh],
                        color="royalblue", lw=7, alpha=0.85,
                        solid_capstyle="butt", zorder=3)
                ax.text(hours[j], Ymax - bh, f"{precip[j]:.2f}", fontsize=6,
                        ha="center", va="top", color="navy")

    # -- barra terreno --
    ax.axhspan(-0.05, 0.0, color="#d9b38c", zorder=2)
    ax.axhline(0.0, color="#5b3a1a", lw=2.2, zorder=2)

    # -- W* sul bordo superiore --
    axt = ax.twiny()
    axt.set_xlim(ax.get_xlim()); axt.set_xticks(hours)
    axt.set_xticklabels([f"{w:.1f}" if not np.isnan(w) else "" for w in wstar],
                        fontsize=7.5)
    axt.tick_params(length=0, pad=2)
    axt.set_xlabel("W* Deardorff (m/s) da flusso ICON  \u2014  nuclei reali ~2x",
                   fontsize=8.5)

    # -- asse Y AGL --
    ax.set_xlim(-0.5, nt - 0.5)
    ax.set_ylim(-0.05, Ymax)
    ax.set_xticks(hours); ax.set_xticklabels(xlabels)
    # scala verticale UNICA a destra, in m slm (parte dalla quota decollo)
    def _slm_ticks():
        first50 = int(np.ceil((elev + 40) / 50.0) * 50)      # 1098 -> 1150
        majors = [(0.0, int(round(elev))), (float(first50 - elev), first50)]
        minors = []
        bands = [(0, 1000, 50, 200), (1000, 2000, 100, 500),
                 (2000, int(top_agl), 200, 1000)]
        for lo, hi, fine, lab in bands:
            s = int(np.ceil((elev + lo) / fine) * fine)
            while s <= elev + hi + 1:
                agl = s - elev
                if 0 < agl <= top_agl and s != first50:
                    is_major = (s % lab == 0)
                    if lo == 0 and is_major and abs(s - first50) < 150:
                        is_major = False
                    if is_major:
                        majors.append((float(agl), s))
                    else:
                        minors.append(float(agl))
                s += fine
        return majors, minors
    majors, minors = _slm_ticks()
    ax.set_yticks([float(agl_to_y(a)) for a, _ in majors])
    ax.set_yticklabels([f"{v}" for _, v in majors], fontsize=8)
    ax.set_yticks([float(agl_to_y(a)) for a in minors], minor=True)
    ax.yaxis.set_label_position("right")
    ax.set_ylabel("Quota (m slm)", fontsize=9.5)
    ax.tick_params(axis="y", which="minor", length=4, color="0.4",
                   right=True, left=False, labelright=False, labelleft=False)
    ax.tick_params(axis="y", which="major", length=7,
                   right=True, left=False, labelright=True, labelleft=False)
    ax.grid(True, axis="y", which="major", alpha=0.12, ls=":")
    for hb in (1000, 2000):
        ax.axhline(float(agl_to_y(hb)), color="0.5", lw=0.8, ls="-.",
                   alpha=0.5, zorder=2)

    # -- righe sotto le ore: vento suolo med/raffica (km/h), T suolo (C) --
    trans = ax.get_xaxis_transform()
    y_wind, y_temp = -0.075, -0.125
    ws10, gust, T2 = surf["ws10"], surf["gust10"], surf["T2m"]
    for j in range(nt):
        if ws10 is not None and not np.isnan(ws10[j]):
            g = gust[j] if (gust is not None and not np.isnan(gust[j])) else ws10[j]
            gk = g * 3.6  # soglia colore sempre in km/h (fisica)
            c = "red" if gk >= 30 else ("darkorange" if gk >= 20 else "black")
            ax.text(hours[j], y_wind, f"{ws10[j]*uf:.0f}/{g*uf:.0f}",
                    transform=trans, ha="center", va="center", fontsize=7, color=c)
        if T2 is not None and not np.isnan(T2[j]):
            ax.text(hours[j], y_temp, f"{T2[j]:.0f}\u00b0", transform=trans,
                    ha="center", va="center", fontsize=7.5, color="#8a3b00")
    fig.text(0.105, 0.26 - 0.075 * 0.60, f"Vento suolo med/raff ({ulab})",
             ha="right", va="center", fontsize=7, color="0.2")
    fig.text(0.105, 0.26 - 0.125 * 0.60, "T suolo (\u00b0C)",
             ha="right", va="center", fontsize=7, color="#8a3b00")
    ax.set_xlabel("Ora locale", labelpad=2)

    d0 = times[0].strftime("%a %d %b %Y")
    ax.set_title(f"{name}\n{model_label}  \u2014  {d0}  "
                 f"({times[0].strftime('%H')}\u2013{times[-1].strftime('%H')})  "
                 f"\u2014  decollo {int(elev)} m slm", fontsize=12.5, pad=26)

    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=8,
               framealpha=0.9, bbox_to_anchor=(0.5, 0.115))
    cax = fig.add_axes([0.17, 0.05, 0.56, 0.018])
    sm = plt.cm.ScalarMappable(norm=cnorm, cmap=cmap)
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal",
                      ticks=[-0.2, 0.0, 0.32, 0.48, 0.65, 0.82, 0.98])
    cb.ax.tick_params(labelsize=7)
    cb.set_label("Instabile <\u2014  Gradiente termico (\u0394T/100 m)  "
                 "\u2014> Stabile", fontsize=8)

    if run_label:
        ax.text(0.995, 1.008, run_label, transform=ax.transAxes, ha="right",
                va="bottom", fontsize=7.5, color="#b03030", fontweight="bold")
    fig.text(0.01, 0.008,
             f"Fonte: Open-Meteo ({model_label}).  "
             + (f"Corsa: {run_label}.  " if run_label else "")
             + f"Barbe in {ulab} su griglia AGL.  Bande "
             + f"{int(fr[0]*100)}/{int(fr[1]*100)}/{int(fr[2]*100)}%.  "
             + f"Decollo {int(elev)} m slm.  W* Deardorff da flusso + PBL ICON-D2.",
             fontsize=6, color="gray")

    fig.savefig(out, dpi=140)
    print(f"Salvato: {out}")


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, default=46.11)
    ap.add_argument("--lon", type=float, default=12.52)
    ap.add_argument("--elev", type=float, default=None)
    ap.add_argument("--name", default="Piancavallo - Antenne Castaldia")
    ap.add_argument("--start", type=int, default=9)
    ap.add_argument("--end", type=int, default=19)
    ap.add_argument("--top-agl", type=float, default=5000)
    ap.add_argument("--model", default="icon_d2",
                    help="modello Open-Meteo con livelli di pressione "
                         "(icon_d2, italia_meteo_arpae_icon_2i, icon_eu, arome_france)")
    ap.add_argument("--wind-unit", choices=["kmh", "kt"], default="kmh",
                    help="unita' del vento per barbe e riga suolo")
    ap.add_argument("--out", default="windgram.png")
    args = ap.parse_args()

    try:
        data = fetch(args.lat, args.lon, args.model)
    except Exception as e:
        print(f"Errore fetch API: {e}", file=sys.stderr)
        sys.exit(1)

    times, levels, hwind, surf, grid_elev = to_grid(data, args.start, args.end)
    init_dt = fetch_model_run(args.model)
    if init_dt is not None:
        age = (dt.datetime.now(dt.timezone.utc) - init_dt).total_seconds() / 3600
        run_label = f"corsa {init_dt:%d %b %H:%M} UTC ({age:.0f} h fa)"
        print(f"Corsa modello: {init_dt:%Y-%m-%d %H:%M} UTC ({age:.0f} h fa)")
    else:
        run_label = None
        print('[avviso] orario corsa modello non disponibile')
    elev = args.elev
    if elev is None:
        elev = fetch_elevation(args.lat, args.lon)
    if elev is None:
        elev = grid_elev if grid_elev is not None else 1080.0
        print(f"[avviso] quota decollo non rilevata, uso {elev} m", file=sys.stderr)
    else:
        print(f"Quota decollo (DEM): {elev:.0f} m slm")

    labels_map = {"icon_d2": "ICON-D2 ~2.2 km",
                  "italia_meteo_arpae_icon_2i": "ICON-2I ~2 km",
                  "icon_eu": "ICON-EU ~7 km", "arome_france": "AROME France ~2.5 km",
                  "arome_france_hd": "AROME HD ~1.3 km"}
    model_label = labels_map.get(args.model, args.model)
    if len(levels) < 3:
        print("Pochi livelli di pressione validi per il modello "
              f"'{args.model}'. Questo modello potrebbe non esporre i "
              "livelli di pressione o non coprire il punto. Prova un "
              "altro modello, es.:  --model italia_meteo_arpae_icon_2i",
              file=sys.stderr)
        sys.exit(2)
    plot(times, levels, hwind, surf, elev, args.name, args.out,
         top_agl=args.top_agl, model_label=model_label,
         wind_unit=args.wind_unit, run_label=run_label)


if __name__ == "__main__":
    main()
