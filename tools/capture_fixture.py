#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cattura UNA volta una risposta reale di Open-Meteo come fixture deterministica,
usata dalla rete di sicurezza del refactoring (vedi REFACTOR.md, Step A1).
Richiede rete. Non fa parte del runtime: e' uno strumento di sviluppo.

Uso:
  py tools/capture_fixture.py

Salva tests/fixtures/piancavallo_icon_d2.json con:
- data:  il dict JSON grezzo del forecast (gia' serializzabile)
- elev:  quota DEM del punto
- shf15: flusso di calore a 15' (times ISO + valori, NaN -> null)

La fixture va ricatturata solo se cambiano i campi richiesti a Open-Meteo o il
punto di riferimento; NON per aggiornare la previsione (deve restare fissa).
"""
import json
import os
import sys

# rende importabile il package windgram/ dalla radice del progetto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from windgram.sources.openmeteo import (fetch, fetch_elevation,  # noqa: E402
                                        fetch_shf15)

LAT, LON, MODEL = 46.087557, 12.530206, "icon_d2"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "tests", "fixtures", "piancavallo_icon_d2.json")


def main():
    print("Fetch forecast...")
    data = fetch(LAT, LON, MODEL)
    print("Fetch elevation...")
    elev = fetch_elevation(LAT, LON)
    print("Fetch flusso 15'...")
    sh_t, sh_v = fetch_shf15(LAT, LON, MODEL)

    fixture = {
        "lat": LAT, "lon": LON, "model": MODEL,
        "data": data,
        "elev": elev,
        "shf15_times": [t.isoformat() for t in sh_t] if sh_t else None,
        # v != v e' True solo per NaN: lo mappiamo a null (JSON valido/portabile)
        "shf15_vals": ([None if (v != v) else float(v) for v in sh_v]
                       if sh_v is not None else None),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False)
    print(f"Salvato: {OUT}")


if __name__ == "__main__":
    main()
