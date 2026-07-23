#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windgram.core.aggregate — Strato 1 (fisica / indici derivati).

Aggregazioni di sintesi della giornata a partire dagli output della fisica:
stelle, finestra migliore (flyscore), range e qualita' di base cumuli / sviluppo
/ vento, stima quota massima cumuli. Piu' l'helper `_card16` (gradi -> cardinale
a 16 punti), condiviso: e' un'etichetta semantica (non presentazione), quindi
sta qui e il rendering la importa da questo modulo (dipendenza render->core).

Funzioni PURE: nessun I/O, nessuna rappresentazione.

Estratto verbatim da windgram_v2.py nel refactoring a strati (REFACTOR.md, Step
C3) — era logica incastonata nel file di rendering. Restano invocabili anche via
`windgram_v2` (import) per non rompere il codice esistente.
"""
import datetime as dt

import numpy as np


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
