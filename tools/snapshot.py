#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rete di sicurezza del refactoring (vedi REFACTOR.md, Step A1).

Ricostruisce l'SVG della dashboard da una fixture salvata, con run-time e
generated-time CONGELATI (output deterministico, nessuna rete), e lo confronta
col golden di riferimento. Da eseguire dopo OGNI passo di refactoring: se il
diff non e' vuoto, il passo ha cambiato l'output senza volerlo.

  py tools/snapshot.py            -> genera e confronta col golden (exit != 0 se diverso)
  py tools/snapshot.py --update   -> (ri)scrive il golden

Il golden e' tests/golden/dashboard.svg. Va rigenerato con --update SOLO quando
un cambio di comportamento e' voluto ed esplicito, documentandone il perche'
(commit dedicato).

Nota: l'harness replica volutamente la parte di orchestrazione di
windgram_v2.main() (costruzione di date_str/period_str/label). E' duplicazione
temporanea: quando l'orchestrazione finira' in cli.py (Fase G) questo harness
chiamera' direttamente quella.
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
import windgram_arome as W  # noqa: E402
import windgram_v2 as V  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "piancavallo_icon_d2.json")
GOLDEN = os.path.join(ROOT, "tests", "golden", "dashboard.svg")

# parametri del golden (coerenti con l'uso reale: finestra 8-20)
START, END = 8, 20
NAME = "Piancavallo - Antenne Castaldia"
TOP_AGL = 5000.0
# stringhe CONGELATE: in produzione dipendono dall'ora corrente e dalla corsa,
# qui sono fisse per rendere l'output deterministico e diffabile
RUN_LABEL = "corsa 23 Jul 12:00 UTC (5 h fa)"
RUN_TIME_STR = "14:00"
GEN_TIME_STR = "19:00"

MONTHS = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
          "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
WD = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
LABELS = {"icon_d2": "ICON-D2 · 2.2 km",
          "italia_meteo_arpae_icon_2i": "ICON-2I · 2 km", "icon_eu": "ICON-EU · 7 km"}


def build_svg_from_fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        fx = json.load(f)
    data, elev, model = fx["data"], fx["elev"], fx["model"]
    if fx["shf15_times"]:
        sh_t = [dt.datetime.fromisoformat(t) for t in fx["shf15_times"]]
        sh_v = np.array([np.nan if v is None else v for v in fx["shf15_vals"]], float)
        shf15 = (sh_t, sh_v)
    else:
        shf15 = None

    times, levels, hwind, surf, grid_elev = W.to_grid(data, START, END)
    if elev is None:
        elev = grid_elev
    zi, wstar, lcl, work_top, overdev = W.thermals(times, levels, surf, elev)
    agg = V.aggregate(times, surf, zi, wstar, lcl, work_top, overdev, elev)

    d0 = times[0]
    date_str = f"{WD[d0.weekday()].capitalize()} {d0.day} {MONTHS[d0.month]} {d0.year}"
    period_str = f"{START:02d}:00 - {END:02d}:00 (ora locale)"
    model_label = LABELS.get(model, model)

    return V.build_svg(times, levels, hwind, surf, elev, zi, wstar, lcl,
                       overdev, agg, NAME, model_label, RUN_LABEL, TOP_AGL,
                       date_str, period_str, RUN_TIME_STR, GEN_TIME_STR,
                       fx["lat"], fx["lon"], shf15)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="(ri)scrive il golden")
    args = ap.parse_args()

    svg = build_svg_from_fixture()

    if args.update:
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        with open(GOLDEN, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"Golden aggiornato: {GOLDEN} ({len(svg)} char)")
        return

    if not os.path.exists(GOLDEN):
        print("Golden assente. Esegui prima: py tools/snapshot.py --update",
              file=sys.stderr)
        sys.exit(2)
    with open(GOLDEN, encoding="utf-8") as f:
        golden = f.read()

    if svg == golden:
        print(f"OK: output identico al golden ({len(svg)} char).")
        sys.exit(0)

    print(f"DIFF: output DIVERSO dal golden! "
          f"(nuovo {len(svg)} char, golden {len(golden)} char)", file=sys.stderr)
    n = min(len(svg), len(golden))
    for i in range(n):
        if svg[i] != golden[i]:
            a = max(0, i - 40)
            print(f"Prima divergenza a offset {i}:", file=sys.stderr)
            print(f"  golden: ...{golden[a:i+40]!r}", file=sys.stderr)
            print(f"  nuovo : ...{svg[a:i+40]!r}", file=sys.stderr)
            break
    sys.exit(1)


if __name__ == "__main__":
    main()
