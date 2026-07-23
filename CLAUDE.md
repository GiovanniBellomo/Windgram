# CLAUDE.md — Progetto Windgram Piancavallo (previsione termica parapendio)

Contesto per Claude Code. Leggere tutto prima di modificare il codice.
L'utente (Giovanni) comunica in **italiano**, ambiente **Windows 11 + PowerShell**,
lancia Python con `py` (non `python`). Preferisce deliverable precisi e strutturati.

## Regole di lavoro permanenti (volute esplicitamente da Giovanni, 2026-07-23 — non derogabili)

1. **Commit dopo ogni modifica al codice**, uno per cambio logico — non accumulare. Il push verso
   `origin` va comunque confermato con l'utente (non è automatico). Vedi §15.
2. **Documentazione sempre aggiornata, senza trascurare nulla**: `CLAUDE.md` (fonte primaria) e il
   [Wiki GitHub](https://github.com/GiovanniBellomo/Windgram/wiki) (trasposizione human-friendly,
   repo separato — vedi §16) vanno risincronizzati **ad ogni modifica rilevante**, non a fine
   sessione. Se cambia qualcosa che tocca una sezione di CLAUDE.md, aggiornare anche la pagina
   wiki corrispondente nello stesso giro di lavoro.
3. **TODO / punti aperti sempre aggiornati** — §13 di questo file e la pagina wiki `TODO`. Quando
   un punto viene chiuso, toglierlo; quando emerge un limite o un "andrebbe tarato", aggiungerlo
   subito, non rimandare.
4. **Commentare sempre il codice in italiano** (coerente con lo stile già presente in
   `windgram_v2.py`/`windgram_arome.py`).
5. **Tabella decisioni e fatti sempre aggiornata**: [`DECISIONS.md`](DECISIONS.md) — ogni scelta
   di design non ovvia dal codice (con motivazione) e ogni fatto empirico scoperto (specialmente
   su Open-Meteo/ICON-D2, spesso richiedono una verifica diretta per essere confermati) va
   registrato lì, con la data. Non aspettare la fine della sessione.
6. **Verifiche di coerenza periodiche**: a intervalli ragionevoli (dopo un batch corposo di
   modifiche, o quando sono passate diverse sessioni), Claude propone di sua iniziativa una
   verifica che codice, `CLAUDE.md`, wiki e `DECISIONS.md` siano ancora allineati fra loro —
   senza aspettare che l'utente lo chieda.

---

## 1. Cos'è il progetto

Generatore di **windgram** (diagramma tempo-quota per il volo termico in parapendio) per il
sito di decollo **Piancavallo – Antenne Castaldia** (Prealpi Carniche, FVG), coord.
`lat 46.087557, lon 12.530206`, quota decollo ~1098 m slm (rilevata dal DEM).

Ispirato ai windgram RASP/FIVL (blipmap di DrJack / XCTherm-RegTherm), ricostruiti da dati
del modello **ICON-D2 (~2.2 km)** via **API pubblica Open-Meteo** (gratuita, no key, CORS ok).

Due deliverable:
- **v1** `windgram_arome.py` — grafico tecnico PNG (matplotlib). Il file attualmente nella
  cartella è la versione **COMPLETA** (~720 righe: motore dati/fisica + `plot()` + `main()` per
  il rendering PNG) — vedi §3.
- **v2** `windgram_v2.py` — **dashboard HTML+SVG** (cruscotto da pilota). È il focus attuale.

---

## 2. Come si esegue

```
py windgram_v2.py --lat 46.087557 --lon 12.530206 --name "Piancavallo - Antenne Castaldia" --start 9 --end 19 --out windgram.html
```
Produce `windgram.html` (un unico `<svg>` inline). Doppio clic = apre nel browser.

Argomenti: `--lat --lon --elev(auto DEM) --name --start --end --top-agl(5000) --model(icon_d2) --out`.

Dipendenze: `requests numpy` (v2). La v1 completa richiede anche `matplotlib scipy`.
`py -m pip install requests numpy` (aggiungere `matplotlib scipy` per v1 completa).

---

## 3. File del progetto e stato

| File | Ruolo | Stato |
|------|-------|-------|
| `windgram_arome.py` | Motore dati/fisica (fetch, parsing, calcoli termici) **+ rendering PNG completo** (`plot()`, `make_colormap`, `_cloud_path`, `_smooth`, `_draw_cb`, `main()`). ~720 righe. | Attivo, importato da v2 |
| `windgram_v2.py` | Dashboard HTML+SVG. Importa `windgram_arome as W`. ~1140 righe. | In sviluppo attivo |
| `windgram_v2_spec.md` | Specifica del layout v2 e mappatura dato→elemento | Non presente in cartella al momento — solo riferimento storico se ricreato |

**IMPORTANTISSIMO:** `windgram_v2.py` fa `import windgram_arome as W`. I due file DEVONO stare
nella **stessa cartella**. Da `windgram_arome.py`, v2 usa solo il motore:
`fetch, fetch_elevation, fetch_model_run, fetch_shf15, to_grid, lapse_grid, thermals,
wind_profile, make_vscale` (+ costanti `PLEVELS, HLEVELS, API, ELEV_API`) — non tocca
`plot()`/`main()`.
Se in futuro si dovesse tornare a una versione "motore-only" senza matplotlib/scipy per alleggerire
l'import in v2 (che oggi trascina comunque le dipendenze pesanti di v1 solo per importare il
modulo), va isolata separatamente: **non dare per scontato che il file in cartella sia snello,
verificare sempre con `grep "^def plot\|^def main" windgram_arome.py` prima di assumerlo.**

---

## 4. Sorgente dati — Open-Meteo / ICON-D2

Endpoint forecast: `https://api.open-meteo.com/v1/forecast`. Elevation (DEM 90 m):
`/v1/elevation`. Orario corsa modello: `https://api.open-meteo.com/data/{path}/static/meta.json`
campo `last_run_initialisation_time` (Unix ts) — `path` per icon_d2 = `dwd_icon_d2`.

Campi richiesti (superficie): `temperature_2m, dew_point_2m, precipitation, cloud_cover,
cloud_cover_low, cloud_cover_mid, freezing_level_height, cape, lifted_index,
shortwave_radiation, boundary_layer_height, sensible_heat_flux, surface_pressure,
wind_speed_10m, wind_direction_10m, wind_gusts_10m`.
Livelli di pressione (per ogni p in `PLEVELS`): `temperature, relative_humidity, wind_speed,
wind_direction, geopotential_height, cloud_cover`. Venti height-level: 10/80/120/180 m.
`wind_speed_unit=ms`, `timezone=Europe/Rome`, `forecast_days=2`.

**Scelta del modello — cruciale:** `arome_france_hd` (1.3 km) su Open-Meteo **NON espone i
livelli di pressione** (solo superficie+near-surface), quindi NON è usabile per un windgram
tempo-quota. Si usa **`icon_d2`** (2.2 km), che espone i livelli E copre bene le Alpi orientali
(è anche il modello che XCTherm/FIVL usano per la zona). Alternative con livelli:
`italia_meteo_arpae_icon_2i` (2 km, Italia), `icon_eu` (7 km). A 1098 m i livelli 1000/950/925/900
hPa sono sotto il suolo → il primo utile è ~850 hPa (~1500 m). Fascia 0-380 m sopra il decollo
risolta grossolanamente (limite del dato, non dello script).

Nota copertura: interrogando `models=arome_france_hd` per un punto fuori dominio, l'endpoint
generico fa **fallback silenzioso** su ARPEGE — un dato che torna NON garantisce che sia HD.

---

## 5. Fisica / calcoli (`thermals`, in windgram_arome)

Approccio RASP-equivalente sui parametri PUNTUALI, usando i campi FISICI già calcolati da ICON-D2
(ICON è un modello mesoscala completo: la fisica del boundary layer è già girata).

- **Top boundary layer `zi`** = `elev + boundary_layer_height` (PBL del modello). Fallback:
  metodo della particella secca (adiabatica secca 0.98 °C/100 m fino all'incrocio col profilo).
- **W\* (Deardorff)** = `[ (g/T0) * (Qs/(rho*cp)) * D ]^(1/3)` con
  `Qs = sensible_heat_flux` (W/m²), `D = boundary_layer_height`, `rho = psurf*100/(287*Tk)`,
  `cp=1005`, `g=9.81`. Uso `abs(shf)` nelle ore diurne (`shortwave_radiation>20`) per robustezza
  sulla convenzione di segno (verso l'alto pos/neg varia). Notte → W\*=0. **NON è più un proxy**:
  è la scala convettiva reale. I "nuclei reali" (core) valgono ~2× il W\* medio.
- **Base cumuli `lcl`** = `elev + 125*(T2m - Td2m)` (formula di Espy, m slm).
- **Top termica operativo `work_top`** = `min(zi, lcl)` — fin dove sali SENZA entrare in nube.
  Giornate secche: coincide con zi. Con cumuli: si aggancia a lcl.
- **Sovrasviluppo `overdev`** (bool) = `depth>1200 AND (cape>250 OR lifted_index<-2)`, con
  `depth = zi-lcl` quando zi>lcl. Cima convettiva stimata (indicativa) =
  `min(ztop, max(zi+800, lcl+1500 + cape*1.5))`.
- **Gradiente `lapse` (ΔT/100 m)** = da `lapse_grid`: strati tra livelli (suolo incluso, con T2m
  come pseudo-livello a terra), piecewise per riempire il colore fino a terra.

Ritorno `thermals`: `(zi, wstar, lcl, work_top, overdev)`. NON confondere: `zi` cima BL (termica
secca), `lcl` base cumuli, `work_top` quota di lavoro, sovrasviluppo = crescita SOPRA zi (allerta).

**Onestà (da NON rimuovere dai footer/disclaimer):** parametri puntuali ~RASP-equivalenti, ma
restano SOTTO RASP/RegTherm su effetti sub-griglia legati al terreno (brezze di pendio, inneschi
locali) perché ICON-D2 è a 2.2 km fisso e non ha le "regioni" topografiche di RegTherm.

---

## 6. Scala verticale (`make_vscale`) — asse riferito al decollo, etichette in m slm

Compressione a 3 bande su AGL (metri sopra il decollo), default 45/25/30 %:
- 0-1000 m AGL → 45% dello spazio (massimo dettaglio, dove si vola)
- 1000-2000 m → 25%
- 2000-5000 m → 30%
`make_vscale(elev, top_agl, f1=0.45, f2=0.25)` ritorna `z_to_y, agl_to_y, top_agl, (f1,f2,f3)`
con `y` display in [0,1] (0=suolo in basso, 1=top).

Etichette asse = **m slm** (NON AGL): il fondo mostra la quota decollo esatta (es. 1098), prima
tacca arrotondata per eccesso al primo 50 utile (1098→1150), poi numeri tondi; passi 50/100/200 m
per banda; sopra i 2000 m tacche ogni 200 m (non più rade). Scala UNICA a destra.

---

## 7. v2 — Layout dashboard (`build_svg` in windgram_v2.py)

Canvas SVG `viewBox 0 0 1500 1000`. Font Inter/Segoe UI. Card arrotondate, ombra (`filter #sh`),
palette morbida. Sei zone:

- **Header** (y 0-86, full): a sinistra nome sito (maiuscolo grande) e sotto, in blu/bold,
  **"Altitudine {elev} m slm"** (il vecchio nome modello è stato tolto da qui, resta solo nel
  footer). Al centro data estesa IT + periodo. A destra **testo pulito senza box scuro**,
  allineato a destra, 2 righe in **ora locale Europe/Rome** (mai UTC in header): **"Modello dati
  aggiornato alle HH:MM"** (corsa modello — rinominato da "Aggiornato alle" poi da "Modello dati
  delle", più chiaro che è l'orario della corsa e non un refresh dei dati), "Grafico generato alle
  HH:MM" (ora di esecuzione dello script). La riga "Prossimo aggiornamento dati" (corsa + 3h) è
  stata **rimossa** (non aggiunta di nuovo): la stima non è affidabile, ignora il ritardo reale di
  pubblicazione — vedi `DECISIONS.md` e §11 punto 10.
- **Colonna sinistra** (x 24-274, y 100-824): card **"STIMA GIORNATA"** (rinominata da "RIASSUNTO
  GIORNATA" — meno assertiva, segnala che è una previsione). Badge navy in testa; **stelle**
  grandi centrate (il giudizio testuale tipo "Molto buone" è stato **rimosso**, troppo assertivo
  per una stima — restano solo le stelle); poi 4 righe **icona a sinistra + testo a destra**,
  ridistribuite su **tutta l'altezza della card** (divisori a y 204/352/500/648, righe centrate a
  y 278/426/574/722): TOP TERMICA (freccia magenta), BASE CUMULI/LCL (nuvola azzurra), SVILUPPO
  CUMULI (doppia nuvola — ora mostra **anche la stima della quota massima raggiunta**, es.
  "eccessivo · fino a 3140 m", non solo il range %), VENTO (icona vento blu). Il box verde
  **"FINESTRA MIGLIORE" è stato rimosso** (con l'icona `ic_clock`, ora eliminata dal codice).
  Testo lungo va **a capo** (funzione `_wrap`, riduce a 18px poi 2 righe).
- **Pannello grafico** (card x 290-1188, y 100-824). Plot area `geom = (px=372, py=200,
  pw=720, ph=558)`. Sopra il plot, fascia **INTENSITÀ TERMICA**: titolo
  "INTENSITÀ TERMICA ATTESA (core ×2)"; numeri W\* per ora; **barra colore** intensità (gradiente
  `wbar` verde→rosso per ora). La barra è SEPARATA dal plot. (La vecchia scritta "corsa" in rosso
  accanto al titolo è stata rimossa da qui — resta solo nel footer.)
- **Colonna destra** (x 1204-1476, y 100-969, fino in fondo, bottom allineato alla tabella):
  3 box — **LEGENDA** (quota raggiungibile, copertura cumuli %, sviluppo verticale, zero termico
  stimato — 4 voci; la voce "Top termica operativo" è stata tolta insieme alla linea che
  rappresentava, rimossa dal grafico il 2026-07-23; la voce "Base cumuli LCL" era già stata tolta
  in precedenza insieme alla banda tratteggiata che rappresentava), **GRADIENTE TERMICO** (scala
  qualitativa a bande, palette aggiornata — vedi §9), **VENTO** (legenda barbe).
- **Tabella** (x 24-1188, y 838-969): 3 righe con icona ed etichetta. **Le colonne numeriche sono
  allineate alle ore del grafico**: `TX(j)` usa la funzione condivisa `hour_x(px, pw, nt, j)` —
  la STESSA usata dal corpo del grafico (`build_chart`) e dalla fascia W\* (`Xh`), unica fonte di
  verità per la mappatura ora→X, così le colonne restano allineate ovunque anche se cambia `nt`
  o la larghezza del plot.
- **Footer** (y ~990, full): fonte, corsa (qui sì in UTC), unità barbe, W\* Deardorff, PBL, decollo,
  **coordinate GPS usate per il calcolo** (`lat, lon` in decimali, 6 cifre — passate a `build_svg`
  come parametri in fondo alla firma; utile per verificare a colpo d'occhio quale punto è stato
  interrogato, specie se `--lat/--lon` non sono quelli di default).

**Chart body (`build_chart`)** — molto rivisto:
- `X(j) = hour_x(px, pw, nt, j)` con `HOUR_XPAD=28` px di margine ai due estremi (09 e 19 non
  stanno più esattamente sul bordo), così le bandierine di inizio/fine non escono lateralmente.
- Mappatura verticale con margine: `Yfrac/Yz/Yagl` comprimono la scala reale (da `make_vscale`)
  dentro `[py+YPAD_TOP, py+ph-YPAD_BOT]` (`YPAD_TOP=26`, `YPAD_BOT=30`), lasciando un bordo
  colorato pieno sopra e una banda del suolo più ampia sotto per lo stesso motivo (le bandierine
  delle barbe non escono più dall'area colorata, né sopra né sotto).
- **Sfondo**: una colonna per ora (gradiente verticale dal profilo `lapse`, `fill-opacity=0.5`),
  le colonne sono sfumate tra loro con un **filtro di sfocatura orizzontale** (`#hblur`,
  `feGaussianBlur` solo su X, clippato al plot con `#plotclip`) così il gradiente termico si legge
  come una mappa colore continua da un'ora all'altra invece che a bande nette.
- **Griglia**: tacche minori e maggiori ora **specchiate sia a sinistra che a destra** (prima solo
  a sinistra); la vecchia griglia bianca orizzontale interna è stata **rimossa** (non serviva);
  restano i separatori tratteggiati a 1000/2000 m AGL. Le etichette agli estremi (in alto e in
  basso) sono tenute dentro il riquadro del plot con un clamp verticale.
- **Banda suolo**: marrone chiaro (`#ad8258`), ora **allargata** dalla quota di decollo fino al
  bordo inferiore del plot (non più una riga sottile) — vedi punto sopra sul margine verticale.
- **Barbe vento**: righe scelte **non più a passo fisso in metri** ma camminando sulla quota finché
  non si accumula un gap minimo di `MIN_BARB_GAP_PX=18` px reali — così restano sempre separate
  anche nella banda alta, dove la scala è molto compressa (non serve precisione sulla quota esatta
  di ogni riga). `wind_barb` è stata riscritta: l'**asta è centrata** sul punto quota/ora (metà
  verso la provenienza, metà nella direzione opposta — non più ancorata a un'estremità), e tutte
  le proporzioni (spessore, lunghezza barbe/pennant) **scalano con `L`**, così nel grafico si può
  usare un simbolo piccolo (`L=14`, griglia fitta) mantenendo la forma corretta; la legenda usa
  `L=24`.
- **Nuvole**: soglia minima di copertura per disegnarle alzata da 10% a **40%** (sotto non si
  disegnano). La base non è più centrata sulla lcl: il suo **bordo inferiore è ancorato 25 m sopra
  la lcl** (`CLOUD_GAP`), così non viene mai tagliato dalla linea rosa (che sta sempre ≤ lcl).
  **Opacità del riempimento della testa proporzionale alla copertura %** (da ~0.58 a 40% fino a
  1.0 a 100%, non più fissa). Il gambo (linea grigia verticale) è **più largo e trasparente**
  (`stroke-opacity=0.32`) e il suo spessore **scala con quanto è "cattivo" lo sviluppo**
  (copertura % + bonus se sovrasviluppo), con un tetto al 90% della larghezza della testa (non
  supera mai la base). L'etichetta della quota base è ora piccola e normale (10px, `MUTE`, peso
  normale) — stessa formattazione di quella della cima, non più blu/bold.
- **Linea "top termica operativo"** (`work_top`, soffitto meteorologico) — **rimossa
  completamente dal grafico e dalla legenda** (2026-07-23): dato ritenuto inutile da visualizzare,
  sovrastimava sistematicamente la quota raggiungibile reale (vedi `climb_ceiling` in §5). Il dato
  del modello resta comunque calcolato e disponibile (`work_top` da `thermals()`) — usato in
  sidebar per la card "TOP TERMICA" (§8) — solo non più disegnato come linea nel plot.
- **Linea "quota raggiungibile"** (`climb_ceiling`): colorata con un vero `<linearGradient>` SVG
  (colore + trasparenza continui, non a tratti/blocchi) in base al W\* di ogni ora, vedi §9/§10
  per i dettagli. Solo la linea liscia, **niente pallini né etichette numeriche per ogni ora**
  (aggiunti in un round di modifiche, poi tolti su richiesta esplicita perché disorientavano).
- **Linea "zero termico stimato"**: quota isoterma 0°C da `freezing_level_height`
  (`surf["fzl"]`). **In secondo piano** rispetto a tutti gli altri simboli del grafico (griglia,
  barbe, nuvole, etichette) — disegnata subito dopo lo sfondo, prima di tutto il resto, così non
  compete mai con i dati operativi. Stile: sottile (`stroke-width=1.6`, era 3.4), **tratteggiata**
  (`stroke-dasharray="5 4"`) e semi-trasparente (`stroke-opacity=0.7`), colore azzurro ghiaccio
  (`ICE = "#6fd0ea"`). Un **fiocco di neve** (`ic_snowflake`, 3 assi incrociati) segna ogni ora
  sopra la linea, per restarne leggibile anche così in secondo piano.
- **Barre di pioggia** (nuove): per ogni ora con `precipitation > 0.05 mm`, una barra verticale
  **azzurra** (`RAIN = "#3f9bdb"`, semi-trasparente) dalla **sommità del plot** verso il basso;
  **profondità** proporzionale all'intensità relativa al massimo della giornata; **larghezza
  fissa al 50%** della colonna oraria (il dato è un accumulo orario, non c'è informazione
  sotto-oraria, quindi "durata" non può realisticamente variare — quel 50% rappresenta onestamente
  "è piovuto per un'ora intera"); etichetta numerica in azzurro `"X.X mm/h"`.
- Riquadro **"VENTO IN QUOTA"** in alto a sinistra del plot, invariato.

---

## 8. v2 — Aggregazioni e formule (`aggregate` in windgram_v2.py)

Sulla finestra **diurna** (`shortwave_radiation>20`). "Ore con nuvole" = `cloud_cover_low>=10`.

- **Top termica**: `max(work_top)`, ora = argmax.
- **Base cumuli**: range `[min,max]` di `lcl` sulle ore con nuvole; qualificatore da spread:
  <300 "stabile", 300-600 "variabile", >600 "molto variabile".
- **Sviluppo cumuli**: range `[min,max]` di `cloud_cover_low`; giudizio da max: <20 scarso,
  20-70 buono, 70-85 abbondante, >85 eccessivo. **`cc_top`** (nuovo): stima della quota massima
  raggiunta dai cumuli sulle ore con nuvole, stessa formula della cima convettiva disegnata nel
  grafico (`zi`/`work_top` + extra se sovrasviluppo, uso di `cape`) — mostrata in sidebar accanto
  al range %.
- **Vento**: intensità da `max(gust·3.6)`: <15 debole, 15-28 debole/moderato, 28-45 moderato,
  >45 forte. Direzione = **media vettoriale** del vento 10 m → cardinale 16 punti.
  (Alternativa da valutare: direzione nell'ora di punta della termica.)
- **Stelle (0.5-5)**: sotto-punteggi 0-1: `S_forza=clip(max(wstar)/2.2)`,
  `S_quota=clip((max(work_top)-elev)/2000)`, `S_vento=clip(1-max(0,max_gust_kmh-20)/30, .05,1)`,
  `S_fin=clip(N_ore_buone/6)` con ora buona = `wstar>=0.6*max AND gust_kmh<35`.
  `Base = 0.34*forza+0.26*quota+0.26*vento+0.14*fin`. Penalità ×: 0.75 se overdev in ore 11-17,
  0.60 se `max precip>0.3`, 0.85 se copertura media >85%. `Stelle=clip(round(Base*10)/2,0.5,5)`.
  Giudizio: >=4.5 Ottime, >=4 Molto buone, >=3 Buone, >=2 Discrete, >=1 Deboli, else Scarse.
- **Finestra migliore (flyscore)**: per ora diurna
  `flyscore = 0.55*(wstar/max) + 0.25*f_vento + 0.20*f_overdev`, con
  `f_vento = 1(<25) / 0.5(25-35) / 0.15(>=35)` km/h, `f_overdev = 0.3 se overdev else 1`.
  Finestra = blocco contiguo più lungo con `flyscore>=0.65`, allargato ±30 min. Se nessuna: picco.

**Soglie da tarare** (scelte ragionevoli, NON validate su voli reali): 2.2 (W\*), 2000 (quota),
limiti stelle, `flyscore>=0.65`. Calibrare su alcune giornate reali dell'utente.

---

## 9. Scale colore

- **Gradiente termico** (sfondo grafico, smooth): `GRAD_STOPS` rosso(1.05)→…→blu(-0.2),
  interpolato in RGB (`grad_color`). Palette rifatta per differenziare meglio le tinte (rosso più
  puro, verde vero invece di verde-teal): `#dc2b28→#f0632a→#f5b02a→#f5e043→#a3d945→#26b357→
  #3f9bdb→#525fcf`. Sfondo disegnato con `fill-opacity=0.5` (non pieno — deve restare tenue) +
  sfocatura orizzontale tra colonne (vedi §7) per continuità cromatica. Legenda destra = versione
  **qualitativa a bande** (`GRAD_CLASSES`, stessi hex dei relativi stop): Instabile >0.9 rosso,
  Buona 0.65-0.9 arancio, Moderata 0.32-0.65 verde-giallo, Debole 0-0.32 verde, Stabile <0 blu.
- **Intensità W\*** (barra in cima): `WSTAR_STOPS` verde(0)→…→rosso(2.4) (`wstar_color`).
- **Intensità termica della linea "quota raggiungibile"** (`THERM_CLASSES`/`THERM_STOPS`,
  `therm_color`): 5 control point sugli STESSI colori di `GRAD_CLASSES` (in ordine crescente
  zero→molto forte: blu→verde→verde-giallo→arancio→rosso), classificati per W\* in m/s —
  `0.0-0.5` Zero, `0.5-1.0` Debole, `1.0-2.0` Sfruttabile, `2.0-3.0` Forte, `>3.0` Molto forte
  (soglia del rosso abbassata da 4.0 a 3.0 il 2026-07-23, il vecchio limite era quasi mai
  raggiunto nella pratica). `therm_color(w)`
  interpola con continuità tra i control point (stessa tecnica RGB di `grad_color`/`wstar_color`),
  NON sceglie un colore a blocchi: la linea è disegnata come un unico `<linearGradient>`
  orizzontale con uno `<stop>` esatto ad ogni ora (`x = X(j)`, colore `therm_color(wstar[j])`),
  così il colore "puro" di ogni ora cade esattamente sulla sua ascissa e sfuma con continuità
  verso le ore vicine (interpolazione nativa del browser, non discretizzata). Soglie NON tarate
  su voli reali (stesso discorso di §8).
- Colori chiave: `PINK #e5197f` (icona/testo "TOP TERMICA" in sidebar — non più il colore della
  linea nel grafico), `BLUEC #2f7fd0`, `ICE #6fd0ea` (zero termico stimato), `RAIN #3f9bdb`
  (barre di pioggia), `INK #1b2a4a`, `MUTE #5a6b86`.

## 10. Convenzioni grafiche

- **Barbe vento** (`wind_barb`): asta **centrata** sul punto quota/ora (metà verso la PROVENIENZA,
  metà nella direzione opposta — non più ancorata a un'estremità, così il simbolo non "pende" da
  un lato della quota che rappresenta); barba intera = 10 km/h, mezza = 5, pennant = 50.
  **< 5 km/h = pallino "o"** (calma, standard). Tutte le proporzioni (spessore, lunghezza
  barbe/pennant) **scalano con `L`** — nel grafico v2 `L=14` (griglia fitta, righe scelte per
  restare separate in pixel, vedi §7), in legenda `L=24`. Unità default km/h (barbe + tabella).
  `--wind-unit kt` disponibile in v1.
- **Nuvole** (`cloud_path`): sagoma SVG chiusa (un solo path, ricentrata sul baricentro d'area così
  la % è centrata). In v2 disegnate solo se copertura ≥40%; base con bordo inferiore ancorato
  25 m sopra la lcl (`CLOUD_GAP`, mai centrata sulla lcl) così la linea della termica non la taglia
  mai; opacità del riempimento proporzionale alla copertura % (100% copertura = opaca, meno
  copertura = più trasparente). Testa alla base (grigio + %), gambo verticale **largo e
  trasparente** (`stroke-opacity=0.32`, spessore proporzionale a quanto è "cattivo" lo sviluppo —
  copertura + bonus overdev — capato al 90% della larghezza della testa), cima (`zi` o convettiva
  se overdev → tratteggiata + "Cb"). Quota base sotto (piccola, stile uguale alla quota cima) e
  quota cima sopra.
- **Trasparenza della linea "top termica"** (`therm_opacity(w, slope)`): oltre al colore (sopra),
  anche l'opacità è un gradiente continuo per-ora, prodotto di due fattori — **intensità**:
  `w<1.0 → 0.15+0.30·w` (range 0.15-0.45, "poco visibile" sotto 1 m/s come richiesto), `w≥1.0 →
  0.45+0.55·clip((w-1)/3,0,1)` (fino a piena opacità 1.0 verso 4 m/s); **stabilità**: `slope =
  (wstar[j+1]-wstar[j-1])/2` (differenza centrata sull'ora prima/dopo, ai bordi solo il vicino
  disponibile), `stab = clip(1-|slope|/1.0, 0.45, 1.0)` — termica piatta/stabile = 1.0 (nessuna
  riduzione), variazione rapida (≥1 m/s tra un'ora e l'altra) = scende fino a 0.45. Opacità finale
  `clip(mag·stab, 0.12, 1.0)` (mai sotto 0.12, mai sopra 1.0). Costanti NON tarate su voli reali.

---

## 11. Limitazioni oneste (mantenere nei disclaimer)

1. AROME HD non ha livelli di pressione su Open-Meteo → si usa ICON-D2 (2.2 km).
2. Risoluzione 2.2 km fissa: no brezze di pendio / inneschi sub-griglia (RegTherm sì).
3. Fascia 0-~380 m sopra il decollo risolta grossolanamente (primo livello ~850 hPa).
4. W\* Deardorff robusto ma segno flusso gestito con `abs()`; cima Cb è stima.
5. Endpoint orario corsa: se non risponde, lo script NON si rompe (mostra "corsa n/d").
6. Non sostituisce FIVL/XCTherm: strumento di CROSS-CHECK e secondo parere sul punto.
7. Il nodo griglia ICON-D2 usato da Open-Meteo per Piancavallo (46.087557, 12.530206) è
   **46.08°N / 12.52°E**, cella (griglia di output 0.02°×0.02°) ≈ **2.23 km (N-S) × 1.54 km (E-O)**,
   lat `[46.07°, 46.09°)` / lon `[12.51°, 12.53°)`. Il decollo è ~0.84 km a nord e ~0.79 km a est
   del centro cella (verso lo spigolo NE, non al centro) — verificato empiricamente con uno sweep
   di query a lat/lon leggermente spostate (vedi conversazione del 2026-07-22). Il campo
   `elevation` restituito dalla stessa chiamata forecast (oggi 1098 m, identico al DEM) **non è
   l'orografia interna a 2.2 km che ICON-D2 usa per la sua fisica di cella**: è un lookup DEM fine
   sul punto esatto (cambia con continuità anche spostando la query di poche decine di metri pur
   restando sulla stessa cella/nodo orario). La vera quota di orografia interna del modello per
   quella cella non è esposta dall'API e potrebbe scostarsi da 1098 m, specie su pendio ripido.
8. **Quota realisticamente raggiungibile** (`climb_ceiling`, §5) — profilo di decadimento della
   termica con la quota e soglia di affondo (`SINK_RATE=1.0`) scelti come approssimazione
   ragionevole, **non tarati su voli reali**. Vedi §13.
9. **Soglie di stelle/flyscore/palette termica** (§8, §9) — scelte ragionevoli ma non validate su
   voli reali. Vedi §13.
10. **"Prossimo aggiornamento dati"** — la stima (corsa + 3h nominali ICON-D2) **non teneva conto
    del ritardo reale di pubblicazione** dei dati da parte di Open-Meteo, che può essere di ore
    oltre il ciclo nominale. Verificato empiricamente il 2026-07-23 (vedi `DECISIONS.md`): alle
    18:16 locali la corsa disponibile era ancora quella delle 14:00, non delle 17:00 come la stima
    avrebbe promesso. **Risolto rimuovendo la riga dall'header** (2026-07-23) invece di correggere
    la stima — non c'era un modo affidabile di calcolarla con i dati esposti dall'API.

---

## 12. Cronologia rifiniture v2 (cosa è già stato fatto)

**Prima fase** (colonna sinistra su mockup, colonna destra a piena altezza, tabella con colonne
allineate alle ore, fascia intensità termica separata dalle barbe, W\* Deardorff integrato, asse
in m slm dalla quota decollo) — vedi dettagli nella memoria di progetto se serve lo storico.

**Seconda fase, sessione 2026-07-22** (rifinitura ampia, molti round di feedback): header pulito
in ora locale (via niente più badge scuro/UTC); barbe di vento centrate sulla quota, spaziate a
gap minimo in pixel (non più a passo fisso in metri) e ridotte di dimensione per non sovrapporsi;
margini orizzontale (`HOUR_XPAD`) e verticale (`YPAD_TOP/BOT`) aggiunti al plot così le bandierine
restano sempre dentro l'area colorata; tacche asse Y specchiate a destra; griglia bianca interna
rimossa; banda del suolo allargata; sfondo termico con palette più differenziata, opacità ridotta
e sfumato in orizzontale tra le ore (continuità cromatica); nuvole sotto 40% nascoste, base
scostata 25 m sopra la lcl (mai più tagliata dalla linea rosa), opacità e spessore del gambo
proporzionali a copertura/sovrasviluppo, etichetta quota base uniformata a quella della cima;
aggiunte linea "zero termico stimato" e barre di pioggia in cima al plot; sidebar sinistra
ridistribuita, box "FINESTRA MIGLIORE" e giudizio testuale rimossi, titolo cambiato in "STIMA
GIORNATA", aggiunta stima quota massima cumuli.

**Terza fase, sessione 2026-07-22/23**: la linea "top termica operativo" non è più a tinta rosa
fissa — colorata con un `<linearGradient>` SVG continuo (colore + trasparenza) in base al W\* di
ogni ora (vedi §9/§10, `therm_color`/`therm_opacity`); header "Aggiornato alle"→"Modello dati
delle" (meno ambiguo); footer con coordinate GPS aggiunte in fondo.

**Quarta fase, sessione 2026-07-23**: introdotta `climb_ceiling` come linea separata da
`work_top` (quota realisticamente raggiungibile, tiene conto dell'affondo dell'ala e del profilo
di indebolimento della termica con la quota — eredita il linguaggio colore/trasparenza che prima
era sulla linea del soffitto); soglia colore "rosso" spostata da W\*≥4 a W\*≥3; finestra di calcolo
della stabilità ridotta da ±1h a ±15'; parametri `mag` ricalibrati (0.15-0.5 sotto W\*=1, 0.5-1.0
fino a W\*=2.5); **flusso di calore reale a 15'** (`fetch_shf15`) per rifinire il W\* locale nel
calcolo di stabilità, con un bug trovato e corretto (interpolava `boundary_layer_height` grezzo,
spesso NaN, invece di riusare `zi` già risolto); minimo di opacità portato a 0 (era 0.12), con
`W*≤0 → opacità 0` esplicito. Inizializzato il repository **git**, poi reso pubblico su GitHub e
collegato a un **Wiki** (`https://github.com/GiovanniBellomo/Windgram/wiki`, trasposizione
human-friendly di questo file). Introdotte le **regole di lavoro permanenti** in cima a questo
file e la tabella `DECISIONS.md`. Dettaglio completo di ogni scelta con motivazione: `DECISIONS.md`.

**Quinta fase, sessione 2026-07-23**: la linea "top termica operativo" (`work_top`) è stata
**rimossa completamente** dal grafico e dalla legenda (dato ritenuto inutile da visualizzare, il
dato del modello resta comunque disponibile per la sidebar); la linea "zero termico stimato" è
stata spostata **in secondo piano** (disegnata subito dopo lo sfondo, prima di griglia/barbe/
nuvole/etichette), resa più sottile, tratteggiata, semi-trasparente (`stroke-opacity=0.7`), con
un'icona a fiocco di neve (`ic_snowflake`) ad ogni ora per restare leggibile; rimossa la riga
"Prossimo aggiornamento dati" in header (stima inaffidabile, vedi §11 punto 10); "Modello dati
delle"→"Modello dati aggiornato alle".

## 13. TODO / prossimi passi

- **Tarare** soglie stelle/flyscore su giornate reali (vedi §8) — non ancora fatto.
- **Tarare** `SINK_RATE` e il coefficiente del profilo verticale in `climb_ceiling` (vedi §5) su
  voli reali — non ancora fatto.
- Valutare direzione vento "ora di punta" vs media vettoriale.
- Eventuale confronto multi-modello (ICON-D2 vs ICON-2I) affiancato.

## 14. Gotchas operativi

- Windows: usare `py`, non `python`. Salvare i .py in **UTF-8** (contengono °, ×, ΔT, à…).
- I due file .py DEVONO stare nella stessa cartella (v2 importa v1).
- L'utente ha avuto problemi di **download dal browser** (claude.ai): a volte i file vanno
  ricevuti via copia-incolla. Tenerne conto nella consegna.
- Test senza rete: nessun `test_v2.py` è presente in cartella al momento. Se serve sviluppare il
  rendering offline, costruire a mano un dict `data["hourly"]` compatibile con `to_grid` con dati
  sintetici. Per l'anteprima grafica si è usato in passato `cairosvg` (svg2png) — solo in sviluppo,
  non runtime, e non è tra le dipendenze installate di default.
- `to_grid` filtra al **primo giorno** nella finestra oraria; con `forecast_days=2` prende oggi.

## 15. Controllo versione (git)

Repository git inizializzato il 2026-07-23. Collegato a **GitHub** come repository **pubblico**
(passato da privato a pubblico lo stesso giorno, scelta consapevole di Giovanni per sbloccare la
funzione Wiki — su piano gratuito il Wiki richiede repo pubblico):
`https://github.com/GiovanniBellomo/Windgram` (remote `origin`, branch `main`).

`.gitignore` esclude: output generati (`*.html`, `*.png` — rigenerabili da codice + dati live,
non ha senso versionarli) e `.claude/` (config locale di Claude Code, specifica della macchina).
Restano tracciati: `windgram_v2.py`, `windgram_arome.py`, `CLAUDE.md`, `DECISIONS.md`,
`Esecuzione.txt`.

Regola di commit/push: vedi le **Regole di lavoro permanenti** in cima a questo file.

## 16. Wiki del progetto

`https://github.com/GiovanniBellomo/Windgram/wiki` — 12 pagine organizzate per argomento,
trasposizione human-friendly di questo stesso file (repo del wiki separato, clonabile da
`https://github.com/GiovanniBellomo/Windgram.wiki.git`, branch `master` non `main`). **Se
CLAUDE.md viene aggiornato, il wiki andrebbe risincronizzato di conseguenza** (non è automatico) —
altrimenti le due fonti divergono nel tempo. `CLAUDE.md` resta la fonte di verità primaria.
