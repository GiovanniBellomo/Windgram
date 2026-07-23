#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windgram.contract — Strato 1.5: il CONTRATTO.

Struttura dati versionata e serializzabile che descrive COMPLETAMENTE un
windgram. E' il confine unico fra fisica e rappresentazione (REFACTOR.md, Fase
E): tutto cio' che sta sopra (sources + core) lo PRODUCE, tutto cio' che sta
sotto (render, API, mobile, widget) lo CONSUMA. E' anche il payload che l'API
restituira' e il file che si logga come storico.

Contratto RICCO (opzione A): porta anche la fisica derivata che oggi il renderer
ricalcola (profilo di vento risolto, profilo di lapse per lo sfondo), cosi' un
consumatore puo' disegnare SENZA rifare fisica. Restano nel renderer solo layout
e stile (mappatura quota->pixel, palette, sagome SVG).

REGOLE:
- Solo dati SEMANTICI: nessun colore, nessuna coordinata-pixel, nessuna stringa
  di layout. Le etichette qualitative gia' calcolate (stelle, qualita' vento...)
  vivono in `aggregates` perche' sono interpretazione del dato, non stile.
- Tipi Python semplici e JSON-safe: float/int/str/bool/None/list/dict. NIENTE
  numpy, NIENTE NaN (i mancanti sono `None`). La conversione da numpy avviene a
  monte, in chi costruisce il contratto (Fase E2).
- `contract_version` versiona il formato: quando cambia in modo incompatibile va
  incrementato (i consumatori terzi ci contano).

E1: qui si DEFINISCE solo il dataclass + (de)serializzazione + round-trip. Non e'
ancora agganciato a nessun renderer (quello e' E2/E3).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

CONTRACT_VERSION = "1.0"


@dataclass
class Meta:
    """Metadati della previsione (tutto semantico/grezzo; la formattazione per
    l'header — data estesa, ore locali — la fa il renderer)."""
    site: str
    lat: float
    lon: float
    elev_m: float
    model: str                  # id modello, es. "icon_d2"
    run_utc: str | None         # ISO 8601 UTC della corsa, o None se ignoto
    generated_utc: str          # ISO 8601 UTC di generazione del contratto
    timezone: str               # es. "Europe/Rome"
    top_agl_m: float            # tetto della scala verticale (m sopra il decollo)
    period_start_h: int         # ora locale di inizio finestra
    period_end_h: int           # ora locale di fine finestra


@dataclass
class Surface:
    """Valori al suolo per una singola ora."""
    t2m_c: float | None
    td2m_c: float | None
    wind_ms: float | None
    gust_ms: float | None
    dir_deg: float | None


@dataclass
class WindProfile:
    """Profilo di vento risolto alle quote NATIVE del dato (superficie 10 m +
    height-level + livelli di pressione), gia' in componenti u/v. Il renderer
    interpola da qui alle quote-barbe che sceglie (operazione di layout)."""
    agl_m: list[float]
    u_ms: list[float]
    v_ms: list[float]


@dataclass
class LapseProfile:
    """Gradiente termico a strati per lo sfondo: `edges_m` = quote dei confini di
    strato (m slm, suolo incluso), `rate_c100m` = ΔT/100 m di ogni strato
    (len = len(edges_m) - 1; `None` dove non calcolabile)."""
    edges_m: list[float]
    rate_c100m: list[float | None]


@dataclass
class Hour:
    """Tutti i dati (grezzi + derivati) di una singola ora."""
    time: str                   # ISO 8601 locale
    wstar: float | None         # W* Deardorff (m/s)
    zi_m: float | None          # cima boundary layer (m slm)
    lcl_m: float | None         # base cumuli (m slm)
    work_top_m: float | None    # soffitto meteorologico min(zi, lcl) (m slm)
    climb_top_m: float | None   # quota realisticamente raggiungibile (m slm)
    overdev: bool               # sovrasviluppo
    cloud_low_pct: float | None
    cape: float | None
    lifted_index: float | None
    precip_mm: float | None
    freezing_level_m: float | None
    surface: Surface
    wind: WindProfile
    lapse: LapseProfile


@dataclass
class Forecast:
    """Il contratto completo: metadati + serie oraria + aggregati di sintesi."""
    contract_version: str
    meta: Meta
    hours: list[Hour]
    aggregates: dict            # l'attuale `agg` (stelle, finestra, range...): gia' semantico

    # -- serializzazione -----------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int | None = None) -> str:
        # allow_nan=False: fa fallire se per errore e' rimasto un NaN (deve essere None)
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent,
                          allow_nan=False)

    @classmethod
    def from_dict(cls, d: dict) -> "Forecast":
        meta = Meta(**d["meta"])
        hours = []
        for h in d["hours"]:
            rest = {k: v for k, v in h.items()
                    if k not in ("surface", "wind", "lapse")}
            hours.append(Hour(surface=Surface(**h["surface"]),
                              wind=WindProfile(**h["wind"]),
                              lapse=LapseProfile(**h["lapse"]),
                              **rest))
        return cls(contract_version=d["contract_version"], meta=meta,
                   hours=hours, aggregates=d["aggregates"])

    @classmethod
    def from_json(cls, s: str) -> "Forecast":
        return cls.from_dict(json.loads(s))
