#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windgram.core.thermals — Strato 1 (fisica).

Calcoli termici in stile RASP dai campi fisici gia' prodotti da ICON-D2:
gradiente di strato (lapse), base cumuli (lcl), cima BL + W* Deardorff
(thermals), profilo di vento in quota (wind_profile), scala verticale a bande
(make_vscale). Funzioni PURE: nessun I/O di rete, nessuna rappresentazione.

Estratto verbatim da windgram_arome.py nel refactoring a strati (REFACTOR.md,
Step C1). Restano invocabili anche via `windgram_arome` (shim di
ri-esportazione) per non rompere il codice esistente.
"""
import numpy as np


def lapse_grid(times, levels, surf, elev):
    """Ritorna edges (nz,nt) = quote dei confini di strato (suolo incluso) e
    lr (nz-1,nt) = gradiente ΔT/100 m di ogni strato. Serve a colorare a bande
    piene fino a terra."""
    nt = len(times)
    ground_z = np.full(nt, float(elev))
    ground_T = surf["T2m"] if surf["T2m"] is not None else np.full(nt, np.nan)
    seq = [{"z": ground_z, "T": ground_T}] + levels
    nz = len(seq)
    edges = np.array([s["z"] for s in seq])          # (nz, nt)
    lr = np.full((nz - 1, nt), np.nan)
    for i in range(nz - 1):
        dz = seq[i + 1]["z"] - seq[i]["z"]
        dT = seq[i]["T"] - seq[i + 1]["T"]
        with np.errstate(divide="ignore", invalid="ignore"):
            lr[i] = np.where(dz > 1, dT / dz * 100.0, np.nan)
    return edges, lr


def lcl_height(T2m, Td2m, elev):
    if T2m is None or Td2m is None:
        return None
    return elev + 125.0 * (T2m - Td2m)


def thermals(times, levels, surf, elev):
    """Parametri termici in stile RASP, dai campi FISICI di ICON-D2.
    W* alla Deardorff:  W* = [ (g/T0) * (Qs/(rho*cp)) * D ]^(1/3)
    con Qs = flusso di calore sensibile del modello, D = boundary layer height.
    Cade sul metodo della particella secca solo se il flusso non e' disponibile.
    """
    nt = len(times)
    g, cp, dry = 9.81, 1005.0, 0.0098
    zi = np.full(nt, np.nan)
    wstar = np.full(nt, np.nan)
    zcol = np.array([l["z"] for l in levels])
    Tcol = np.array([l["T"] for l in levels])
    T2, swr = surf["T2m"], surf["swr"]
    blh, shf, psurf = surf.get("blh"), surf.get("shf"), surf.get("psurf")
    for j in range(nt):
        if T2 is None or np.isnan(T2[j]):
            continue
        Tk = T2[j] + 273.15
        # --- spessore del boundary layer D ---
        if blh is not None and not np.isnan(blh[j]) and blh[j] > 30:
            D = float(blh[j])                     # PBL height del modello (m AGL)
            zi[j] = elev + D
        else:                                     # fallback: particella secca
            z, Te = zcol[:, j], Tcol[:, j]
            o = np.argsort(z); z, Te = z[o], Te[o]
            Tp = T2[j] - dry * (z - elev)
            above = np.where((Tp - Te) <= 0)[0]
            zi[j] = z[above[0]] if len(above) else np.nanmax(z)
            D = max(zi[j] - elev, 100.0)
        # --- W*: Deardorff dal flusso di calore sensibile del modello ---
        day = swr is not None and not np.isnan(swr[j]) and swr[j] > 20
        if shf is not None and not np.isnan(shf[j]) and day and D > 50:
            if psurf is not None and not np.isnan(psurf[j]):
                rho = (psurf[j] * 100.0) / (287.0 * Tk)
            else:
                rho = 1.12
            wtheta = abs(shf[j]) / (rho * cp)     # flusso cinematico (K m/s)
            wstar[j] = (g / Tk * wtheta * D) ** (1.0 / 3.0)
        elif day:                                 # ripiego dalla radiazione
            wtheta = 0.15 * swr[j] / (1.12 * cp)
            wstar[j] = (g / Tk * wtheta * D) ** (1.0 / 3.0)
        else:
            wstar[j] = 0.0
    lcl = lcl_height(surf["T2m"], surf["Td2m"], elev)
    lcl = np.full(nt, np.nan) if lcl is None else np.asarray(lcl, float)
    work_top = np.where(zi > lcl, lcl, zi)
    cape = surf["cape"] if surf["cape"] is not None else np.zeros(nt)
    li = surf.get("li")
    li_arr = np.nan_to_num(np.asarray(li, float), nan=99.0) if li is not None \
        else np.full(nt, 99.0)
    depth = np.where(zi > lcl, zi - lcl, 0.0)
    overdev = (depth > 1200) & ((np.nan_to_num(cape) > 250) | (li_arr < -2.0))
    return zi, wstar, lcl, work_top, overdev


def wind_profile(levels, hwind, surf, elev, j, agl_targets):
    """Interpola (u,v) del vento sulle quote AGL richieste, all'ora j."""
    ag, us, vs = [], [], []
    def add(agl, ws, wd):
        if not (np.isnan(ws) or np.isnan(wd)):
            ag.append(agl)
            us.append(-ws * np.sin(np.deg2rad(wd)))
            vs.append(-ws * np.cos(np.deg2rad(wd)))
    if surf["ws10"] is not None:
        add(10.0, surf["ws10"][j], surf["wd10"][j])
    for w in hwind:
        add(float(w["agl"]), w["ws"][j], w["wd"][j])
    for l in levels:
        z = l["z"][j]
        if not np.isnan(z):
            add(z - elev, l["ws"][j], l["wd"][j])
    if len(ag) < 2:
        return None, None
    o = np.argsort(ag)
    ag = np.array(ag)[o]; us = np.array(us)[o]; vs = np.array(vs)[o]
    u_i = np.interp(agl_targets, ag, us)
    v_i = np.interp(agl_targets, ag, vs)
    return u_i, v_i


# --------------------------------------------------------------------------- #
# Scala verticale AGL a 3 bande (0-1000 / 1000-2000 / 2000-top)
# --------------------------------------------------------------------------- #
def make_vscale(elev, top_agl=5000.0, f1=0.45, f2=0.25):
    h1, h2 = 1000.0, 2000.0
    f3 = max(1.0 - f1 - f2, 0.05)
    Y1, Y2 = f1, f1 + f2

    def agl_to_y(agl):
        agl = np.asarray(agl, float)
        return np.where(
            agl <= h1, np.clip(agl, 0, None) / h1 * f1,
            np.where(agl <= h2, Y1 + (agl - h1) / (h2 - h1) * f2,
                     Y2 + (agl - h2) / (top_agl - h2) * f3))

    def z_to_y(z):
        return agl_to_y(np.asarray(z, float) - elev)

    return z_to_y, agl_to_y, top_agl, (f1, f2, f3)
