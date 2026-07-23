#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windgram.core.climb — Strato 1 (fisica).

Quota realisticamente raggiungibile in salita da un parapendio, tenendo conto
dell'affondo dell'ala e del fatto che la termica si indebolisce salendo verso
`zi`. Funzione PURA (solo numpy): nessun I/O, nessuna rappresentazione.

Estratto verbatim da windgram_v2.py nel refactoring a strati (REFACTOR.md, Step
C2) — era fisica incastonata nel file di rendering. Restano invocabili anche via
`windgram_v2` (import) per non rompere il codice esistente.
"""
import numpy as np

SINK_RATE = 1.0  # m/s: affondo minimo tipico di un'ala da parapendio in aria calma


def climb_ceiling(elev, zi, lcl, wstar, sink_rate=SINK_RATE):
    """Quota REALISTICAMENTE raggiungibile in salita -- non il soffitto meteorologico
    `zi` (dove la termica smette di esistere nel modello, per costruzione), ma dove
    la sua intensita' LOCALE scende sotto l'affondo dell'ala. La termica non e'
    costante con la quota: parte debole a terra, ha un massimo verso 1/4 dello
    strato rimescolato, torna verso zero proprio a `zi` (e' la definizione stessa
    di `zi`). Qui approssimata con un profilo w(z*) = wstar * 3.4 * z*^(1/3) *
    (1-z*), con z* = (z-elev)/(zi-elev) in [0,1] -- picco ~1.6x wstar verso
    z*=0.25 (coerente con i "nuclei reali ~2x W*" gia' citati altrove), zero ai
    due estremi. Se il picco del profilo non supera l'affondo, quel giorno non
    c'e' termica sfruttabile (torna `elev`, nessuna quota di lavoro). Come per
    le altre soglie del progetto: approssimazione ragionevole, NON tarata su
    voli reali -- calibrare `sink_rate`/coefficiente su giornate note.
    """
    if zi is None or elev is None or np.isnan(zi) or np.isnan(elev):
        return elev
    span = zi - elev
    if span <= 1.0 or wstar is None or np.isnan(wstar) or wstar <= 0:
        return elev

    def w(zstar):
        zstar = min(max(zstar, 1e-4), 1.0)
        return wstar * 3.4 * zstar ** (1.0 / 3.0) * (1.0 - zstar)

    if w(0.25) < sink_rate:          # anche al suo meglio la termica non regge l'ala
        return elev
    lo, hi = 0.25, 1.0                # bisezione sul ramo discendente oltre il picco
    for _ in range(30):
        mid = (lo + hi) / 2.0
        lo, hi = (mid, hi) if w(mid) > sink_rate else (lo, mid)
    top = elev + lo * span
    if lcl is not None and not np.isnan(lcl):
        top = min(top, lcl)
    return top
