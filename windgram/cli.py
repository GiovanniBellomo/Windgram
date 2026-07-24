#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windgram.cli -- orchestrazione della pipeline (Strato di coordinamento).

Collega gli strati (REFACTOR.md): sorgenti dati (windgram.sources) -> fisica
(windgram.core) -> contratto (windgram.contract) -> renderer (windgram.render).
Interroga Open-Meteo/ICON-D2, assembla il contratto `Forecast`, ne scrive il log
storico (F2) e lo passa al renderer SVG che produce il file .html.

Invocazione abituale via il lanciatore sottile alla radice:
  py windgram_v2.py --lat 46.087557 --lon 12.530206 \
      --name "Piancavallo - Antenne Castaldia" --start 9 --end 19 --out windgram.html
(equivalente: py -m windgram.cli ...)

Argomenti: --lat --lon --elev(auto DEM) --name --start --end --top-agl(5000)
--model(icon_d2) --out --history-dir --no-history.
"""
import argparse
import os
import sys
import datetime as dt

from windgram.sources.openmeteo import (fetch, to_grid, fetch_elevation,
                                        fetch_shf15, fetch_model_run)
from windgram.core.thermals import thermals
from windgram.core.aggregate import aggregate
from windgram.core.forecast import build_forecast
from windgram.render.json_api import render_json
from windgram.render.svg import build_svg, esc

# cartella di default del log storico, alla RADICE del progetto (parent del
# package windgram/), cosi' e' stabile a prescindere dalla cwd di lancio.
# Ignorata da git: e' dato rigenerabile.
_DEFAULT_HISTORY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "history")


# =========================================================================== #
def write_history(forecast, history_dir):
    """Log storico a costo ~zero (REFACTOR.md, F2): scrive il contratto JSON su
    file, uno per (giorno previsto, modello, corsa). Ri-eseguire la STESSA corsa
    sovrascrive lo stesso file (idempotente, niente duplicati); una corsa nuova
    o un altro giorno crea un file nuovo. Abilita la futura correzione statistica
    (confronto previsione vs osservazioni reali). Passa per `render_json`, la
    superficie payload (F1). Ritorna il percorso scritto."""
    meta = forecast.meta
    day = forecast.hours[0].time[:10] if forecast.hours else "na"   # AAAA-MM-GG previsto
    if meta.run_utc:
        run_tag = f"run{dt.datetime.fromisoformat(meta.run_utc):%Y%m%dT%H%MZ}"
    else:
        run_tag = "runNA"
    os.makedirs(history_dir, exist_ok=True)
    path = os.path.join(history_dir, f"{day}_{meta.model}_{run_tag}.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_json(forecast, indent=1))
    return path


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
    ap.add_argument("--history-dir", default=_DEFAULT_HISTORY,
                    help="cartella del log storico dei contratti (default: ./history)")
    ap.add_argument("--no-history", action="store_true",
                    help="non scrivere il log storico del contratto")
    args = ap.parse_args()

    try:
        data = fetch(args.lat, args.lon, args.model)
    except Exception as e:
        print(f"Errore fetch API: {e}", file=sys.stderr); sys.exit(1)
    times, levels, hwind, surf, grid_elev = to_grid(data, args.start, args.end)
    elev = args.elev if args.elev is not None else fetch_elevation(args.lat, args.lon)
    if elev is None:
        elev = grid_elev if grid_elev is not None else 1098.0
    print(f"Quota decollo: {elev:.0f} m slm")
    if len(levels) < 3:
        print("Pochi livelli validi.", file=sys.stderr); sys.exit(2)

    zi, wstar, lcl, work_top, overdev = thermals(times, levels, surf, elev)
    agg = aggregate(times, surf, zi, wstar, lcl, work_top, overdev, elev)

    # flusso di calore sensibile a 15' (per rifinire la stabilita' della
    # "quota raggiungibile"); se non disponibile si ripiega silenziosamente
    # sulla sola interpolazione del W* orario (vedi build_chart)
    shf15 = fetch_shf15(args.lat, args.lon, args.model)
    if shf15[0] is None:
        print("Flusso 15' non disponibile, uso interpolazione oraria.", file=sys.stderr)

    init = fetch_model_run(args.model)

    # E3d (REFACTOR.md): assembla il contratto e passalo come UNICO argomento del
    # rendering (fisica -> build_forecast -> render(forecast)). Il renderer non fa
    # piu' nessuna fisica: legge scalari, profili e metadati (comprese le stringhe
    # di intestazione) dal contratto.
    forecast = build_forecast(
        times, levels, hwind, surf, elev, zi, wstar, lcl, work_top, overdev, agg,
        site=args.name, lat=args.lat, lon=args.lon, model=args.model,
        run_utc=(init.isoformat() if init is not None else None),
        generated_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        timezone="Europe/Rome", top_agl=args.top_agl,
        period_start_h=args.start, period_end_h=args.end, shf15=shf15)

    # F2 (REFACTOR.md): log storico del contratto a costo ~zero. Non deve mai far
    # fallire la generazione del windgram: se scrivere fallisce (permessi, disco)
    # si avvisa e si prosegue.
    if not args.no_history:
        try:
            print(f"Log storico: {write_history(forecast, args.history_dir)}")
        except OSError as e:
            print(f"Log storico non scritto: {e}", file=sys.stderr)

    svg = build_svg(forecast)
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
