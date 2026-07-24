#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rete di sicurezza del refactoring (vedi REFACTOR.md).

Ricostruisce in modo DETERMINISTICO (fixture salvata, run-time/gen-time
congelati, nessuna rete) due artefatti e li confronta col rispettivo golden:
  1. l'SVG della dashboard          -> tests/golden/dashboard.svg
  2. il contratto Forecast (JSON)   -> tests/golden/forecast.json  (da E2)

Da eseguire dopo OGNI passo: se un diff non e' vuoto, il passo ha cambiato
l'output senza volerlo.

  py tools/snapshot.py            -> genera e confronta entrambi i golden
  py tools/snapshot.py --update   -> (ri)scrive entrambi i golden

I golden vanno rigenerati con --update SOLO quando un cambio e' voluto ed
esplicito, documentandone il perche' (commit dedicato).
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
from windgram.core.forecast import build_forecast  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "piancavallo_icon_d2.json")
GOLDEN_SVG = os.path.join(ROOT, "tests", "golden", "dashboard.svg")
GOLDEN_FC = os.path.join(ROOT, "tests", "golden", "forecast.json")

# parametri del golden (coerenti con l'uso reale: finestra 8-20)
START, END = 8, 20
NAME = "Piancavallo - Antenne Castaldia"
TOP_AGL = 5000.0
TIMEZONE = "Europe/Rome"
# valori CONGELATI: in produzione dipendono dall'ora corrente e dalla corsa
RUN_LABEL = "corsa 23 Jul 12:00 UTC (5 h fa)"
RUN_TIME_STR = "14:00"
GEN_TIME_STR = "19:00"
RUN_UTC = "2026-07-23T12:00:00+00:00"
GEN_UTC = "2026-07-23T17:09:00+00:00"

MONTHS = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
          "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
WD = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
LABELS = {"icon_d2": "ICON-D2 · 2.2 km",
          "italia_meteo_arpae_icon_2i": "ICON-2I · 2 km", "icon_eu": "ICON-EU · 7 km"}


def _load_inputs():
    """Carica la fixture e produce, in modo deterministico, tutti gli output di
    fisica + i metadati congelati. Condiviso da SVG e contratto."""
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
    return dict(fx=fx, data=data, elev=elev, model=model, shf15=shf15,
                times=times, levels=levels, hwind=hwind, surf=surf,
                zi=zi, wstar=wstar, lcl=lcl, work_top=work_top, overdev=overdev,
                agg=agg, lat=fx["lat"], lon=fx["lon"])


def _forecast_from_inputs(x):
    """Assembla il Forecast (contratto) dagli input deterministici. Condiviso da
    SVG (ingresso del rendering, E3a) e dal golden JSON."""
    return build_forecast(
        x["times"], x["levels"], x["hwind"], x["surf"], x["elev"],
        x["zi"], x["wstar"], x["lcl"], x["work_top"], x["overdev"], x["agg"],
        site=NAME, lat=x["lat"], lon=x["lon"], model=x["model"],
        run_utc=RUN_UTC, generated_utc=GEN_UTC, timezone=TIMEZONE,
        top_agl=TOP_AGL, period_start_h=START, period_end_h=END, shf15=x["shf15"])


def build_svg_from_fixture():
    x = _load_inputs()
    d0 = x["times"][0]
    date_str = f"{WD[d0.weekday()].capitalize()} {d0.day} {MONTHS[d0.month]} {d0.year}"
    period_str = f"{START:02d}:00 - {END:02d}:00 (ora locale)"
    model_label = LABELS.get(x["model"], x["model"])
    forecast = _forecast_from_inputs(x)  # E3a: contratto = ingresso del rendering
    return V.build_svg(forecast,
                       x["times"], x["levels"], x["hwind"], x["surf"], x["elev"],
                       x["zi"], x["wstar"], x["lcl"], x["overdev"], x["agg"],
                       NAME, model_label, RUN_LABEL, TOP_AGL,
                       date_str, period_str, RUN_TIME_STR, GEN_TIME_STR,
                       x["lat"], x["lon"], x["shf15"])


def build_forecast_json_from_fixture():
    x = _load_inputs()
    return _forecast_from_inputs(x).to_json(indent=1)


def _check(name, produced, golden_path):
    """Ritorna True se identico al golden; stampa esito e prima divergenza."""
    if not os.path.exists(golden_path):
        print(f"[{name}] golden assente: {golden_path} "
              f"(esegui: py tools/snapshot.py --update)", file=sys.stderr)
        return False
    with open(golden_path, encoding="utf-8") as f:
        golden = f.read()
    if produced == golden:
        print(f"[{name}] OK: identico al golden ({len(produced)} char).")
        return True
    print(f"[{name}] DIFF: DIVERSO dal golden! "
          f"(nuovo {len(produced)} char, golden {len(golden)} char)", file=sys.stderr)
    n = min(len(produced), len(golden))
    for i in range(n):
        if produced[i] != golden[i]:
            a = max(0, i - 40)
            print(f"[{name}] prima divergenza a offset {i}:", file=sys.stderr)
            print(f"  golden: ...{golden[a:i+40]!r}", file=sys.stderr)
            print(f"  nuovo : ...{produced[a:i+40]!r}", file=sys.stderr)
            break
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="(ri)scrive i golden")
    args = ap.parse_args()

    svg = build_svg_from_fixture()
    fc_json = build_forecast_json_from_fixture()

    if args.update:
        os.makedirs(os.path.dirname(GOLDEN_SVG), exist_ok=True)
        with open(GOLDEN_SVG, "w", encoding="utf-8") as f:
            f.write(svg)
        with open(GOLDEN_FC, "w", encoding="utf-8") as f:
            f.write(fc_json)
        print(f"Golden aggiornati: dashboard.svg ({len(svg)} char), "
              f"forecast.json ({len(fc_json)} char)")
        return

    ok_svg = _check("SVG", svg, GOLDEN_SVG)
    ok_fc = _check("contratto", fc_json, GOLDEN_FC)
    sys.exit(0 if (ok_svg and ok_fc) else 1)


if __name__ == "__main__":
    main()
