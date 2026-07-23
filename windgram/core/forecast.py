#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windgram.core.forecast — assemblaggio del contratto (Strato 1 -> 1.5).

`build_forecast(...)` prende gli output della fisica (times, livelli, surf, zi,
wstar, lcl, ...) e li impacchetta nel `Forecast` (windgram.contract), un oggetto
serializzabile che il renderer/API consumeranno SENZA rifare fisica (contratto
ricco, REFACTOR.md Fase E).

Qui vengono PRECALCOLATE le grandezze derivate che oggi il renderer ricalcola:
- `climb_top` per ora (via climb_ceiling),
- il profilo di vento risolto alle quote native (wind_samples),
- il profilo di lapse a strati per lo sfondo (lapse_grid),
- lo `wstar_slope_15min` (variazione di W* su +-15', col flusso reale a 15' se
  disponibile) -- unico pezzo che dipende dal dato a 15' e quindi NON ricavabile
  a valle dai soli scalari orari.

La logica dello slope replica ESATTAMENTE quella oggi in build_chart, cosi' che
quando il renderer passera' a consumare il contratto (E3) l'output resti identico.
"""
import datetime as dt

import numpy as np

from windgram.contract import (CONTRACT_VERSION, Forecast, Hour, LapseProfile,
                               Meta, Surface, WindProfile)
from windgram.core.climb import climb_ceiling
from windgram.core.thermals import lapse_grid, wind_samples


def _fnone(x):
    """float(x) oppure None se x manca / e' NaN (JSON-safe)."""
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(xf) else xf


def _at(arr, j):
    """Valore j-esimo di un array di surf (o None se l'array manca / e' NaN)."""
    if arr is None:
        return None
    return _fnone(arr[j])


def build_forecast(times, levels, hwind, surf, elev, zi, wstar, lcl, work_top,
                   overdev, agg, *, site, lat, lon, model, run_utc, generated_utc,
                   timezone, top_agl, period_start_h, period_end_h, shf15=None):
    """Assembla il Forecast dai dati fisici. `run_utc`/`generated_utc` come
    stringhe ISO (o None per run_utc). Ritorna un windgram.contract.Forecast."""
    nt = len(times)
    edges, lr = lapse_grid(times, levels, surf, elev)
    shf15_t, shf15_v = shf15 if shf15 else (None, None)

    # --- slope di W* su +-15' (replica ESATTA di build_chart) ----------------
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
        return _interp(wstar, t_frac)

    def _slope(j):
        return _w_at(j, 0.25) - _w_at(j, -0.25)

    cc_low = surf.get("cc_low")
    cape = surf.get("cape")
    li = surf.get("li")
    precip = surf.get("precip")
    fzl = surf.get("fzl")

    hours = []
    for j in range(nt):
        climb_top = climb_ceiling(elev, zi[j], lcl[j], wstar[j])
        ag, us, vs = wind_samples(levels, hwind, surf, elev, j)
        hours.append(Hour(
            time=times[j].isoformat(),
            wstar=_at(wstar, j), zi_m=_at(zi, j), lcl_m=_at(lcl, j),
            work_top_m=_at(work_top, j), climb_top_m=_fnone(climb_top),
            wstar_slope_15min=_fnone(_slope(j)),
            overdev=bool(overdev[j]),
            cloud_low_pct=_at(cc_low, j), cape=_at(cape, j),
            lifted_index=_at(li, j), precip_mm=_at(precip, j),
            freezing_level_m=_at(fzl, j),
            surface=Surface(
                t2m_c=_at(surf.get("T2m"), j), td2m_c=_at(surf.get("Td2m"), j),
                wind_ms=_at(surf.get("ws10"), j), gust_ms=_at(surf.get("gust10"), j),
                dir_deg=_at(surf.get("wd10"), j)),
            wind=WindProfile(agl_m=ag, u_ms=us, v_ms=vs),
            lapse=LapseProfile(
                edges_m=[_fnone(x) for x in edges[:, j]],
                rate_c100m=[_fnone(x) for x in lr[:, j]]),
        ))

    meta = Meta(site=site, lat=lat, lon=lon, elev_m=float(elev), model=model,
                run_utc=run_utc, generated_utc=generated_utc, timezone=timezone,
                top_agl_m=float(top_agl), period_start_h=int(period_start_h),
                period_end_h=int(period_end_h))
    return Forecast(contract_version=CONTRACT_VERSION, meta=meta, hours=hours,
                    aggregates=dict(agg))
