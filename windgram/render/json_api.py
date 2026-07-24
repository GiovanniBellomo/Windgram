#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windgram.render.json_api — Strato 2: rappresentazione JSON del contratto.

E' il renderer piu' semplice del progetto (REFACTOR.md, F1): il contratto
`Forecast` E' gia', per costruzione, un dato JSON-safe e completo. Qui non si
trasforma nulla, si fissa soltanto il **punto d'ingresso stabile** che tutti i
consumatori "dato" useranno:
- l'**API** (il payload che l'endpoint restituira'),
- il **log storico** a costo zero (il file che si scrive ad ogni run, F2),
- eventuali client (mobile, widget WordPress) che leggono il JSON.

Tenere questa superficie separata da `Forecast.to_json` significa che API/CLI
dipendono da `windgram.render.json_api`, non da un metodo interno del contratto:
domani si potra' cambiare la forma del payload (compatto vs indentato, header
HTTP, envelope di versione...) senza toccare il dataclass del contratto.

Come ogni renderer (vedi il renderer SVG in `windgram_v2.py`), consuma SOLO il
contratto: nessuna fisica, nessun I/O di rete.
"""
from __future__ import annotations

from windgram.contract import Forecast

# Content-Type da usare quando il payload viene servito via HTTP.
CONTENT_TYPE = "application/json; charset=utf-8"


def render_json(forecast: Forecast, *, indent: int | None = None) -> str:
    """Renderizza il contratto come stringa JSON (il payload 'API').

    `indent=None` -> JSON compatto (una riga, tipico della risposta HTTP);
    `indent=N`    -> JSON indentato leggibile (tipico del log storico su file).
    `allow_nan=False` e' garantito a monte da `Forecast.to_json`: se per errore
    fosse rimasto un NaN (invece di None) la serializzazione fallisce, cosi' un
    payload malformato non arriva mai a un consumatore.
    """
    return forecast.to_json(indent=indent)
