#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windgram.sources.openmeteo — Strato 0 (sorgenti dati).

Acquisizione dei dati grezzi da Open-Meteo (modello ICON-D2 di default) e loro
parsing in strutture pronte per la fisica (`to_grid`). NESSUN calcolo fisico,
NESSUNA rappresentazione: solo I/O + parsing.

Estratto verbatim da windgram_arome.py nel refactoring a strati (REFACTOR.md,
Step B1). Le funzioni restano invocabili anche via `windgram_arome` (shim di
ri-esportazione) per non rompere il codice esistente.
"""
import datetime as dt

import numpy as np
import requests

PLEVELS = [1000, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200]
HLEVELS = [10, 80, 120, 180]
API = "https://api.open-meteo.com/v1/forecast"
ELEV_API = "https://api.open-meteo.com/v1/elevation"

META_PATH = {
    "icon_d2": "dwd_icon_d2", "icon_eu": "dwd_icon_eu",
    "italia_meteo_arpae_icon_2i": "italia_meteo_arpae_icon_2i",
    "arome_france": "meteofrance_arome_france",
    "arome_france_hd": "meteofrance_arome_france_hd"}


# --------------------------------------------------------------------------- #
# FETCH
# --------------------------------------------------------------------------- #
def build_params(lat, lon, model="icon_d2"):
    per_level = []
    for p in PLEVELS:
        per_level += [f"temperature_{p}hPa", f"relative_humidity_{p}hPa",
                      f"wind_speed_{p}hPa", f"wind_direction_{p}hPa",
                      f"geopotential_height_{p}hPa", f"cloud_cover_{p}hPa"]
    for hgt in HLEVELS:
        per_level += [f"wind_speed_{hgt}m", f"wind_direction_{hgt}m"]
    surface = ["temperature_2m", "dew_point_2m", "precipitation",
               "cloud_cover", "cloud_cover_low", "cloud_cover_mid",
               "freezing_level_height", "cape", "lifted_index",
               "shortwave_radiation", "boundary_layer_height",
               "sensible_heat_flux", "surface_pressure",
               "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m"]
    return {"latitude": lat, "longitude": lon,
            "hourly": ",".join(surface + per_level),
            "models": model, "forecast_days": 2,
            "timezone": "Europe/Rome", "wind_speed_unit": "ms"}


def fetch(lat, lon, model="icon_d2", timeout=30):
    r = requests.get(API, params=build_params(lat, lon, model), timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_elevation(lat, lon, timeout=15):
    try:
        r = requests.get(ELEV_API, params={"latitude": lat, "longitude": lon},
                         timeout=timeout)
        r.raise_for_status()
        return float(r.json()["elevation"][0])
    except Exception:
        return None


def fetch_shf15(lat, lon, model="icon_d2", timeout=30):
    """Flusso di calore sensibile (sensible_heat_flux) a risoluzione 15 minuti,
    se il modello la espone (verificato: lo fa per icon_d2, con valori che
    variano davvero ogni 15' e non sono la ripetizione del dato orario).
    ATTENZIONE: boundary_layer_height NON e' disponibile a questa risoluzione
    (sempre null) -- solo il flusso lo e'. Ritorna (times, valori) o
    (None, None) se la richiesta fallisce o il campo non e' presente."""
    try:
        r = requests.get(API, params={
            "latitude": lat, "longitude": lon,
            "minutely_15": "sensible_heat_flux",
            "models": model, "forecast_days": 2,
            "timezone": "Europe/Rome"}, timeout=timeout)
        r.raise_for_status()
        j = r.json().get("minutely_15")
        if not j or "sensible_heat_flux" not in j:
            return None, None
        times = [dt.datetime.fromisoformat(t) for t in j["time"]]
        vals = np.array([v if v is not None else np.nan
                         for v in j["sensible_heat_flux"]], dtype=float)
        return times, vals
    except Exception:
        return None, None


def fetch_model_run(model, timeout=15):
    """Orario della corsa del modello (last_run_initialisation_time) come
    datetime UTC. Ritorna None se l'endpoint non risponde."""
    for pth in (META_PATH.get(model, model), model):
        try:
            r = requests.get(
                f"https://api.open-meteo.com/data/{pth}/static/meta.json",
                timeout=timeout)
            r.raise_for_status()
            ts = r.json().get("last_run_initialisation_time")
            if ts:
                return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc)
        except Exception:
            continue
    return None


# --------------------------------------------------------------------------- #
# PARSING -> griglia oraria pronta per la fisica
# --------------------------------------------------------------------------- #
def to_grid(data, start_h=9, end_h=19):
    h = data["hourly"]
    all_times = [dt.datetime.fromisoformat(t) for t in h["time"]]
    day0 = all_times[0].date()
    idx = [i for i, t in enumerate(all_times)
           if t.date() == day0 and start_h <= t.hour <= end_h]
    if not idx:
        idx = list(range(start_h, end_h + 1))
    times = [all_times[i] for i in idx]

    def col(name):
        v = h.get(name)
        if v is None:
            return None
        return np.array([v[i] if v[i] is not None else np.nan for i in idx],
                        dtype=float)

    levels = []
    for p in PLEVELS:
        gz, t = col(f"geopotential_height_{p}hPa"), col(f"temperature_{p}hPa")
        if gz is None or t is None or np.all(np.isnan(gz)) or np.all(np.isnan(t)):
            continue
        levels.append({"p": p, "z": gz, "T": t,
                       "ws": col(f"wind_speed_{p}hPa"),
                       "wd": col(f"wind_direction_{p}hPa"),
                       "cc": col(f"cloud_cover_{p}hPa")})
    levels.sort(key=lambda d: np.nanmean(d["z"]))

    hwind = []
    for hgt in HLEVELS:
        ws, wd = col(f"wind_speed_{hgt}m"), col(f"wind_direction_{hgt}m")
        if ws is not None and wd is not None and not np.all(np.isnan(ws)):
            hwind.append({"agl": hgt, "ws": ws, "wd": wd})

    surf = {k: col(v) for k, v in {
        "T2m": "temperature_2m", "Td2m": "dew_point_2m",
        "precip": "precipitation", "cc": "cloud_cover",
        "cc_low": "cloud_cover_low", "cc_mid": "cloud_cover_mid",
        "fzl": "freezing_level_height", "cape": "cape",
        "li": "lifted_index", "shf": "sensible_heat_flux",
        "swr": "shortwave_radiation", "blh": "boundary_layer_height",
        "psurf": "surface_pressure", "ws10": "wind_speed_10m",
        "wd10": "wind_direction_10m", "gust10": "wind_gusts_10m"}.items()}
    return times, levels, hwind, surf, data.get("elevation")
