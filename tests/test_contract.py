#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test del contratto (REFACTOR.md, E1): round-trip serializza -> deserializza ->
identico, e alcune invarianti di base. Eseguibile senza pytest:

  py tests/test_contract.py

Esce con codice != 0 se qualcosa non torna.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from windgram.contract import (  # noqa: E402
    CONTRACT_VERSION, Forecast, Meta, Surface, WindProfile, LapseProfile, Hour)


def sample_forecast():
    meta = Meta(site="Piancavallo - Antenne Castaldia", lat=46.087557,
                lon=12.530206, elev_m=1098.0, model="icon_d2",
                run_utc="2026-07-23T12:00:00+00:00",
                generated_utc="2026-07-23T17:09:00+00:00",
                timezone="Europe/Rome", top_agl_m=5000.0,
                period_start_h=8, period_end_h=20)
    h1 = Hour(
        time="2026-07-23T14:00:00+02:00", wstar=2.44, zi_m=3111.0, lcl_m=2148.0,
        work_top_m=2148.0, climb_top_m=2148.0, overdev=False, cloud_low_pct=62.0,
        cape=120.0, lifted_index=-1.0, precip_mm=0.0, freezing_level_m=3150.0,
        surface=Surface(t2m_c=19.0, td2m_c=8.0, wind_ms=3.6, gust_ms=8.3, dir_deg=180.0),
        wind=WindProfile(agl_m=[10.0, 1000.0, 2000.0], u_ms=[-0.5, -1.2, -2.0],
                         v_ms=[-3.5, -5.0, -6.1]),
        lapse=LapseProfile(edges_m=[1098.0, 1500.0, 3000.0],
                           rate_c100m=[0.8, None]))
    h2 = Hour(
        time="2026-07-23T15:00:00+02:00", wstar=None, zi_m=None, lcl_m=None,
        work_top_m=None, climb_top_m=None, overdev=True, cloud_low_pct=None,
        cape=None, lifted_index=None, precip_mm=None, freezing_level_m=None,
        surface=Surface(t2m_c=None, td2m_c=None, wind_ms=None, gust_ms=None, dir_deg=None),
        wind=WindProfile(agl_m=[], u_ms=[], v_ms=[]),
        lapse=LapseProfile(edges_m=[], rate_c100m=[]))
    return Forecast(contract_version=CONTRACT_VERSION, meta=meta,
                    hours=[h1, h2],
                    aggregates=dict(stars=4.0, top_val=2223, top_hour="15:00",
                                    lcl_lo=1840, lcl_hi=2440, lcl_q="variabile",
                                    cc_lo=18, cc_hi=89, cc_top=3110,
                                    dev_q="eccessivo", wind_q="moderato",
                                    wind_dir="S", window="08:30 - 17:30",
                                    judge="Molto buone"))


def main():
    fc = sample_forecast()

    # 1) round-trip via JSON: deve tornare un oggetto identico
    s = fc.to_json()
    fc2 = Forecast.from_json(s)
    assert fc == fc2, "round-trip JSON: oggetto diverso dopo from_json(to_json())"
    assert fc.to_dict() == fc2.to_dict(), "round-trip: dict diversi"

    # 2) il JSON e' valido e ri-parsabile, e i None restano null (non NaN)
    d = json.loads(s)
    assert d["contract_version"] == CONTRACT_VERSION
    assert d["hours"][1]["wstar"] is None
    assert d["hours"][0]["lapse"]["rate_c100m"][1] is None
    assert "NaN" not in s, "il JSON non deve contenere NaN"

    # 3) indent opzionale non altera i dati
    fc3 = Forecast.from_json(fc.to_json(indent=2))
    assert fc == fc3

    # 4) from_dict pura (senza passare da stringa)
    fc4 = Forecast.from_dict(fc.to_dict())
    assert fc == fc4

    print(f"OK: contratto v{CONTRACT_VERSION} — round-trip e invarianti superate "
          f"({len(s)} char JSON, {len(fc.hours)} ore).")


if __name__ == "__main__":
    main()
