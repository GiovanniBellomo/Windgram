# Piano di refactoring — separazione degli strati

Documento di lavoro. Definisce la migrazione da 2 file monolitici a un'architettura a strati
netti, **per piccoli passi**, ognuno committabile e **verificabile a output invariato**.
Deciso con Giovanni il 2026-07-23. Vedi anche `DECISIONS.md` per le scelte di fondo.

> ## ▶ STATO / RIPRENDERE DA QUI (2026-07-24)
> Fatto: **A1, B1, C1, C2, C3, D1, E1, E2, E3a, E3b, E3c**. A1-E2 pushati su `origin/main` (commit
> `98ead9c`); E3a/E3b/E3c committati in locale, **non ancora pushati**. Dati, fisica e contratto
> sono separati e testati; `windgram_arome.py` e' una facciata di soli shim; niente piu'
> matplotlib/scipy. Il contratto e' l'INGRESSO del rendering (`build_svg(forecast, ...)`); il
> renderer legge dal contratto `climb_top_m`, `wstar_slope_15min` (E3b), il profilo vento e il
> profilo lapse (E3c). Restano ricalcolati/sciolti solo gli scalari per-ora (zi, wstar, lcl,
> superficie...) -> E3d.
>
> **Prossimo passo: E3d** (vedi checklist Fase E, l'ultimo di E3). E3 e' spezzato in 4 sotto-passi
> (E3a-E3d) perche' e' il piu' delicato: far consumare il contratto al renderer, a golden invariato.
>
> **Come riprendere in sicurezza**: prima di ogni modifica e dopo, lanciare
> `py tools/snapshot.py` — deve stampare `[SVG] OK` e `[contratto] OK` (entrambi identici ai
> golden). Se un passo cambia un golden senza volerlo, fermarsi. La fixture e i golden sono in
> `tests/`. Ambiente: Windows, `py`, dipendenze runtime `requests numpy`.

## Obiettivo

Separare nettamente:
- **Sorgenti dati** (acquisizione) → **Fisica** (calcoli puri) → **Contratto** (dato serializzabile)
  → **Rappresentazioni** (renderer che consumano solo il contratto).

Perché: multipiattaforma (mobile, widget WordPress), monetizzazione (l'API = il contratto JSON),
e futura correzione statistica su osservazioni reali. Scelte confermate:
- Fisica **server-side** (Python), il contratto **JSON** è il confine universale.
- v1 (PNG matplotlib) **ritirata** → la fisica si libera di `matplotlib`/`scipy`.
- Log storico delle previsioni **a costo ~zero** (scrivere il contratto su file per ogni run).

## Principi non negoziabili

1. **Output invariato a ogni passo.** Nessuno step cambia il pixel finale finché non è un cambio
   di comportamento *voluto ed esplicito*. La rete di sicurezza (sotto) lo garantisce.
2. **Passi piccoli, un commit ciascuno** (regola permanente del progetto).
3. **Spostare, non riscrivere.** Nella prima parte si spostano funzioni fra moduli lasciando shim
   di ri-esportazione, così nulla si rompe. La riscrittura vera (firme sul contratto) arriva dopo,
   isolata.
4. **Documentazione in pari** (CLAUDE.md, wiki, DECISIONS.md) a fine di ogni fase.

## Architettura target

```
windgram/
  __init__.py
  sources/        # Strato 0 — SOLO acquisizione, nessun calcolo
    openmeteo.py      (build_params, fetch, fetch_elevation, fetch_model_run,
                       fetch_shf15, to_grid)
    station.py        (FUTURO: osservazioni per la correzione statistica)
  core/           # Strato 1 — fisica pura: ZERO I/O, ZERO grafica
    thermals.py       (lapse_grid, lcl_height, thermals, wind_profile, make_vscale)
    climb.py          (climb_ceiling, SINK_RATE)         # oggi in windgram_v2.py!
    aggregate.py      (aggregate, _best_block)           # oggi in windgram_v2.py!
  contract.py     # Strato 1.5 — dataclass Forecast (v1.0) + to_dict/from_dict/to_json + versione
  render/         # Strato 2 — consuma SOLO il contratto
    svg.py            (dashboard HTML+SVG, ex windgram_v2)
    json_api.py       (serializza il contratto — banale)
  cli.py          # orchestrazione: sources -> core -> contract -> render
windgram_v2.py    # entry-point sottile mantenuto alla radice per non cambiare l'invocazione
                  # abituale (`py windgram_v2.py --lat ...`) finche' non decidiamo di rinominare
```

La v1 `windgram_arome.py` sparisce: le funzioni utili migrano in `sources/` e `core/`, il codice
matplotlib viene eliminato.

## La rete di sicurezza (golden snapshot)

Il cuore della sicurezza. Serve a diffare l'output prima/dopo ogni passo. L'output però dipende da
dati live e dall'ora corrente → va **congelato**:

- **Fixture**: si cattura UNA volta una risposta reale di Open-Meteo (forecast + elevation +
  shf15) e la si salva in `tests/fixtures/*.json` (tracciati da git — il `.gitignore` ignora solo
  `*.html`/`*.png`).
- **Harness**: `tools/snapshot.py` carica la fixture, **inietta run-time e generated-time fissi**,
  esegue la pipeline e scrive l'SVG in `tests/golden/dashboard.svg` (estensione `.svg` → tracciata).
- **Verifica**: dopo ogni step si rigenera e si fa `diff` col golden. **Deve essere vuoto.**
  Quando un cambio di comportamento è voluto, si aggiorna il golden *nello stesso commit* e si
  documenta il perché.

Nota: le funzioni attuali sono già abbastanza parametrizzate (`to_grid(data)`, `build_svg(...)` con
array espliciti, `run_time_str`/`gen_time_str` passati come stringhe) da permettere l'harness
**senza toccare il codice di produzione**. Questo rende lo Step A1 a rischio zero.

## Fasi e step (checklist)

Legenda stato: `[ ]` da fare · `[~]` in corso · `[x]` fatto.

### Fase A — Rete di sicurezza (nessun cambio al codice di produzione)
- [x] **A1** Cattura fixture Open-Meteo reali + harness `tools/snapshot.py` + golden
  `tests/golden/dashboard.svg`. Commit. Da qui in poi ogni step è protetto.
  - `tools/capture_fixture.py` (rete, una-tantum) → `tests/fixtures/piancavallo_icon_d2.json`
  - `tools/snapshot.py` (offline, deterministico): `--update` scrive il golden, senza args diffa.
  - Golden = 170577 char, verificato deterministico su due run. **Uso**: dopo ogni step, lanciare
    `py tools/snapshot.py` — deve stampare "OK: output identico al golden".

### Fase B — Strato 0 (dati)
- [x] **B1** Crea `windgram/sources/openmeteo.py`, SPOSTA lì i `fetch*` + `to_grid` da
  `windgram_arome.py`; lascia in `windgram_arome.py` uno shim che li ri-esporta. Golden invariato.
  - Spostati: `build_params, fetch, fetch_elevation, fetch_shf15, fetch_model_run, to_grid` +
    costanti `PLEVELS, HLEVELS, API, ELEV_API, META_PATH`. Shim `from windgram.sources.openmeteo
    import (...)` in cima a `windgram_arome.py` → `W.fetch` ecc. continuano a funzionare.
  - Verificato: golden identico (170577 char), `--help` OK, `W.fetch.__module__` =
    `windgram.sources.openmeteo`.

### Fase C — Strato 1 (fisica)
- [x] **C1** Crea `windgram/core/thermals.py`, SPOSTA `thermals, lapse_grid, lcl_height,
  wind_profile, make_vscale`; shim di ri-esportazione. Golden invariato.
  - Nuovo pacchetto `windgram/core/`. Shim `from windgram.core.thermals import (...)` in
    `windgram_arome.py`. Verificato: golden identico (170577 char), `--help` OK,
    `W.thermals.__module__` = `windgram.core.thermals`.
- [x] **C2** SPOSTA `climb_ceiling` (+`SINK_RATE`) da `windgram_v2.py` a `windgram/core/climb.py`.
  Golden invariato.
  - Era fisica incastonata nel file di rendering (l'entanglement peggiore). Ora `windgram_v2.py`
    fa `from windgram.core.climb import climb_ceiling, SINK_RATE`. Golden identico (170577 char).
- [x] **C3** SPOSTA `aggregate` (+`_best_block`) da `windgram_v2.py` a
  `windgram/core/aggregate.py`. Golden invariato.
  - Spostato anche `_card16` (gradi->cardinale): e' un'etichetta semantica condivisa fra
    `aggregate` (core) e la tabella in `build_svg` (render). Sta in core, il render la
    importa (dipendenza render->core, mai il contrario). `windgram_v2.py` fa
    `from windgram.core.aggregate import aggregate, _card16`. Golden identico (170577 char).
  - **Fase C completa**: tutta la fisica/logica derivata e' uscita dal file di rendering.
    `windgram_v2.py` ora e' presentazione (SVG) + orchestrazione (`main`).

### Fase D — Ritiro v1 PNG
- [x] **D1** Elimina `plot, make_colormap, _cloud_path, _smooth, _draw_cb, main` e gli import
  `matplotlib`/`scipy` da `windgram_arome.py`. (v2 non li usa → golden invariato.) Il progetto
  perde le dipendenze pesanti.
  - `windgram_arome.py` ridotto da 474 a **27 righe** (pura facciata di soli shim). Verificato:
    importando `W` **nessun** modulo matplotlib/scipy viene caricato; golden identico (170577
    char); `--help` OK. Dipendenze runtime ora: solo `requests numpy` (per v2). `matplotlib scipy`
    non servono piu'.

### Fase E — Il contratto (il passo cardine, isolato)
- [x] **E1** Definisci `windgram/contract.py`: dataclass `Forecast` v1.0 + `to_dict/from_dict/
  to_json`. Non ancora collegato. Test di round-trip (serializza→deserializza→uguale).
  - **Contratto RICCO (opzione A)**, scelto da Giovanni: porta anche la fisica derivata che oggi
    il renderer ricalcola — `WindProfile` (vento risolto alle quote native) e `LapseProfile`
    (gradiente a strati per lo sfondo) — cosi' un consumatore disegna senza rifare fisica.
  - Struttura: `Forecast{contract_version, Meta, hours[Hour{..., Surface, WindProfile,
    LapseProfile}], aggregates}`. Tipi JSON-safe (float/int/str/bool/None/list/dict), niente
    numpy/NaN (mancanti = `None`). `to_json(allow_nan=False)` fa fallire se resta un NaN.
  - Test `tests/test_contract.py` (senza pytest, `py tests/test_contract.py`): round-trip
    JSON/dict, invarianti None→null, indent. **Non ancora agganciato** al rendering (E2/E3).
    Golden invariato (170577 char).
- [x] **E2** Aggiungi in `core/` una `build_forecast(...)` che assembla il contratto dagli output
  della fisica. Test: da fixture → contratto → golden JSON `tests/golden/forecast.json`.
  - `windgram/core/forecast.py`: `build_forecast(...)` precalcola climb_top (climb_ceiling),
    profilo vento nativo (`wind_samples`, nuova in `core/thermals.py`), profilo lapse
    (`lapse_grid`), e `wstar_slope_15min` (replica ESATTA della logica di build_chart, cosi' E3
    riprodurra' il golden SVG). Contratto: aggiunto `Hour.wstar_slope_15min`; `LapseProfile.edges_m`
    ora ammette `None`.
  - `tools/snapshot.py` esteso: verifica DUE golden (SVG + `forecast.json`) con input condivisi.
    Golden SVG invariato (170577), golden contratto creato (30356 char, 13 ore). `build_forecast`
    NON ancora usato dal renderer (quello e' E3).
- **E3** Rifai `build_svg`/`build_chart` perché consumino il `Forecast` invece dei ~20 parametri
  sciolti. Il piu' delicato → **spezzato in 4 sotto-passi**, ognuno a golden SVG invariato e con
  commit proprio:
  - [x] **E3a** Sposta la costruzione del contratto in `main()`: `fisica → build_forecast →
    render(forecast, …)`. Il contratto diventa l'INGRESSO del rendering; internamente il renderer
    ancora ricalcola. Golden invariato.
    - `build_svg` ha ora `forecast` come primo parametro (non ancora consumato). `main()` chiama
      `build_forecast(...)` prima di `build_svg`. `tools/snapshot.py` estratto `_forecast_from_inputs`
      condiviso da SVG e golden JSON. Entrambi i golden invariati (170577 / 30356 char).
  - [x] **E3b** `build_chart` usa `climb_top_m` e `wstar_slope_15min` DAL contratto invece di
    ricalcolarli (rimuove la duplicazione `climb_ceiling`/`_slope` nel renderer). Golden invariato.
    - Rimossi da `build_chart` il ricalcolo `climb_ceiling` per ora e l'intera catena
      `_interp`/`_w_at`/`_slope` (col dato shf15 a 15'): ora `climb_top` si ricostruisce da
      `forecast.hours[j].climb_top_m` (None -> NaN, filtro `np.isnan` invariato) e lo slope si
      legge da `forecast.hours[j].wstar_slope_15min`. `therm_opacity` gia' tratta None come NaN.
      Il parametro `shf15` di `build_chart` e' ora inutilizzato (rimozione firma rimandata a E3d).
      Entrambi i golden invariati (170577 / 30356 char).
  - [x] **E3c** `build_chart` usa il profilo vento (`wind`) e il profilo lapse (`lapse`) dal
    contratto, non piu' ricalcolati con `wind_profile`/`lapse_grid`. Golden invariato.
    - Lapse: `edges`/`lr` (matrici nz×nt) ricomposte dalle colonne per-ora del contratto
      (`forecast.hours[j].lapse`), None->NaN nelle stesse posizioni cosi' `_lapse_at` (filtra ez
      con np.isfinite) e' identico. Vento: `forecast.hours[j].wind` da' i campioni nativi
      (`wind_samples`, la parte pre-interpolazione di `wind_profile`); si ricampiona con lo stesso
      `np.interp(tgt, ...)` -> barbe bit-identiche. `wind_profile`/`lapse_grid` non piu' chiamate
      dal renderer. Entrambi i golden invariati (170577 / 30356 char).
  - [ ] **E3d** `build_chart`/`build_svg` leggono gli scalari per-ora (wstar, zi, lcl, superficie…)
    dal contratto invece che dagli array sciolti. Firma finale: `render(forecast)`. Golden
    invariato. Da qui il renderer non fa PIU' nessuna fisica.

### Fase F — Nuove superfici abilitate dal contratto
- [ ] **F1** `windgram/render/json_api.py`: serializza il contratto (è di fatto il payload API).
- [ ] **F2** Log a costo zero: `cli.py` scrive il contratto JSON in `history/AAAA-MM-GG_run.json`
  a ogni esecuzione. Abilita la futura analisi errore.

### Fase G — Struttura finale e pulizia
- [ ] **G1** Sposta i file nel layout `windgram/` definitivo, aggiorna gli import, rimuovi gli shim
  quando nessuno usa più i percorsi vecchi. Mantieni l'entry-point `windgram_v2.py` alla radice
  come lanciatore sottile. Golden invariato.
- [ ] **G2** Aggiorna CLAUDE.md, wiki, DECISIONS.md con la nuova architettura. Aggiungi pagina wiki
  dedicata all'architettura a strati e al formato del contratto.

## Note e rischi

- **Invocazione CLI**: finché non decidiamo diversamente, resta `py windgram_v2.py --lat ...` (un
  lanciatore sottile alla radice). Un eventuale passaggio a `py -m windgram` è una scelta separata,
  non forzata da questo refactoring.
- **Windows/`py`/UTF-8**: valgono le solite regole (vedi CLAUDE.md §14).
- **Passi che cambiano comportamento**: solo E3 tocca le firme, ma a output identico. Se un giorno
  vorremo cambiare *cosa* mostra il grafico, sarà uno step separato e dichiarato, con golden
  aggiornato apposta.
- **`therm_color`/`therm_opacity`/`grad_color`/`wstar_color`**: sono mappe dato→colore, quindi
  **presentazione** — restano in `render/`, non in `core/`. Le soglie che incorporano (es. classi
  W\*) sono già documentate in DECISIONS.md.
