#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windgram_arome.py — facciata di compatibilita' (shim).

Storicamente questo file conteneva motore dati + fisica + rendering PNG
(matplotlib). Nel refactoring a strati (REFACTOR.md) il contenuto e' stato
spostato nel package `windgram/`:
- Strato 0 (dati)   -> windgram/sources/openmeteo.py
- Strato 1 (fisica) -> windgram/core/thermals.py

Il rendering PNG v1 (matplotlib/scipy: plot, make_colormap, _cloud_path,
_smooth, _draw_cb, main) e' stato RITIRATO (REFACTOR.md, Step D1): non serve
piu' e trascinava dipendenze pesanti sull'intero progetto.

Questo file resta solo come facciata: `import windgram_arome as W` continua a
esporre W.fetch, W.to_grid, W.thermals, W.make_vscale, ... per windgram_v2 e i
tool, senza piu' matplotlib/scipy. In Fase G verra' probabilmente assorbito nel
package `windgram/`.
"""
# Strato 0 — sorgenti dati (Open-Meteo)
from windgram.sources.openmeteo import (  # noqa: F401
    PLEVELS, HLEVELS, API, ELEV_API, META_PATH,
    build_params, fetch, fetch_elevation, fetch_shf15, fetch_model_run, to_grid)
# Strato 1 — fisica
from windgram.core.thermals import (  # noqa: F401
    lapse_grid, lcl_height, thermals, wind_profile, make_vscale)
