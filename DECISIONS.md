# Decisioni e Fatti — Windgram

Registro delle scelte progettuali (con motivazione) e dei fatti empirici scoperti lavorando sul
progetto. Va tenuto aggiornato a ogni modifica rilevante — non solo il codice, anche il *perché*.

Due tabelle separate:
- **Decisioni**: scelte deliberate, con alternative scartate e motivo.
- **Fatti**: osservazioni empiriche/scoperte (spesso su Open-Meteo/ICON-D2) che non sono scelte
  ma vincoli con cui il progetto deve convivere.

---

## Decisioni

| Data | Decisione | Motivazione |
|---|---|---|
| — | Modello meteo: **ICON-D2**, non `arome_france_hd` | AROME HD su Open-Meteo non espone i livelli di pressione (solo superficie) — inutilizzabile per un windgram tempo-quota. ICON-D2 (2.2 km) espone i livelli e copre bene le Prealpi. |
| — | `work_top = min(zi, lcl)` come soffitto operativo | Fin dove si sale senza entrare in nube — combina termica secca e base cumuli nel modo più restrittivo. |
| 2026-07-23 | Introdotta **`climb_ceiling`** come linea separata da `work_top` | `work_top`/`zi` sono il soffitto *meteorologico* del modello, non la quota che un pilota può realisticamente raggiungere: l'ala ha un affondo proprio (~1 m/s) e la termica si indebolisce salendo verso `zi`, non è costante. `work_top` da solo sovrastimava sistematicamente la raggiungibilità reale. |
| 2026-07-23 | `SINK_RATE = 1.0` m/s come soglia di affondo in `climb_ceiling` | Valore tipico di affondo minimo di un'ala da parapendio in aria calma, scelto da Giovanni. **Non tarato su voli reali** — vedi TODO. |
| 2026-07-23 | Soglia colore "rosso" (Molto forte) in `THERM_CLASSES`: **W\*≥3**, non più ≥4 | Richiesta esplicita — il vecchio limite lasciava il rosso quasi mai raggiunto nella pratica. |
| 2026-07-23 | Parametri `mag` (intensità → opacità) ricalibrati: 0.15-0.5 sotto W\*=1, 0.5-1.0 fino a W\*=2.5 | W\*=1 è già "soglia di galleggiamento" (deve leggersi discretamente), W\*=2.5 è già una bella termica (deve leggersi a piena visibilità) — la vecchia scala arrivava a piena opacità solo a W\*=4, troppo raro. |
| 2026-07-23 | Finestra di calcolo della "stabilità" (variabilità locale) ridotta da ±1 ora a **±15 minuti** | Il dato sorgente è orario, ma interpolando linearmente il delta a ±15' è esattamente metà di quello a ±1h — soglia di riferimento più stretta, variazioni piccole pesano meno. Poi rifinito col flusso di calore reale a 15' (vedi Fatti). |
| 2026-07-23 | Minimo di opacità della linea "quota raggiungibile" portato a **0** (rimosso floor 0.12); caso esplicito `W*≤0 → opacità 0` | "Se non c'è condizione [termica], inutile mostrare qualcosa" — richiesta esplicita di Giovanni. |
| 2026-07-23 | Nuvole disegnate solo se copertura **≥40%** (prima 10%) | Sotto quella soglia affollavano il grafico senza portare informazione utile. |
| 2026-07-23 | Base nuvola ancorata **25 m sopra la lcl** (non centrata sulla lcl) | Con la sagoma centrata sulla lcl, la linea della termica (che sta sempre ≤ lcl) a volte tagliava la nuvola. |
| 2026-07-23 | Barbe vento con asta **centrata** sul punto quota/ora (non ancorata a un'estremità) | Il vecchio disegno faceva "pendere" tutta la barba da un lato della quota che rappresentava, fuorviante. |
| 2026-07-23 | Box "FINESTRA MIGLIORE" e giudizio testuale (es. "Molto buone") **rimossi** dalla sidebar | Troppo assertivi per una stima probabilistica — restano solo le stelle. Titolo card cambiato in "STIMA GIORNATA" per lo stesso motivo. |
| 2026-07-23 | Header: "Aggiornato alle" → **"Modello dati delle"** | La vecchia dicitura suggeriva un refresh live, mentre è l'orario della corsa del modello. |
| 2026-07-23 | Repository git creato, poi reso **pubblico** su GitHub | Necessario per sbloccare la funzione Wiki nativa di GitHub su piano gratuito (i repo privati non la supportano). Rischio valutato: nessun segreto nel codice, coordinate GPS del decollo già pubbliche (sito FIVL/XCTherm noto); unico costo reale è nome+email dell'autore visibili nella cronologia commit. |
| 2026-07-23 | Regola permanente: **commit dopo ogni modifica**, **documentazione (CLAUDE.md + wiki) sempre aggiornata**, **commenti sempre in italiano**, **verifiche di coerenza periodiche proposte da Claude** | Richiesta esplicita di Giovanni — il progetto è cresciuto molto e serve disciplina per non perdere storico/contesto. |
| 2026-07-23 | Linea "top termica operativo" (`work_top`) **rimossa completamente** dal grafico e dalla legenda | Richiesta esplicita — dato ritenuto inutile da visualizzare (sovrastimava la raggiungibilità reale, `climb_ceiling` la sostituisce già come informazione). Il dato del modello resta comunque calcolato/disponibile per la sidebar. |
| 2026-07-23 | Linea "zero termico stimato" spostata **in secondo piano** (disegnata subito dopo lo sfondo, prima di griglia/barbe/nuvole/etichette), resa sottile/tratteggiata/semi-trasparente (opacità 0.7), con icona a fiocco di neve ad ogni ora | Richiesta esplicita — è un riferimento di massima, non deve competere visivamente con i dati operativi; il fiocco di neve la mantiene individuabile anche così. |
| 2026-07-23 | Rimossa la riga "Prossimo aggiornamento dati" dall'header (non corretta la stima) | La stima (corsa+3h) non è affidabile — vedi Fatti sotto — e non c'è modo di calcolarla in modo affidabile con i dati esposti dall'API. Meglio niente che un orario spesso sbagliato. |
| 2026-07-23 | Header: "Modello dati delle" → **"Modello dati aggiornato alle"** | Chiarezza ulteriore su cosa rappresenta l'orario mostrato. |
| 2026-07-23 | **Refactoring a strati** (sources/core/contract/render) per piccoli passi, con rete di sicurezza golden-snapshot | Progetto cresciuto: strati entangled (fisica dentro il file di rendering). Obiettivo: multipiattaforma (mobile/WordPress), monetizzazione (API=contratto JSON), correzione statistica futura. Piano completo in `REFACTOR.md`. |
| 2026-07-23 | **v1 PNG (matplotlib) RITIRATA** (eseguito in D1): rimossi `plot/make_colormap/_cloud_path/_smooth/_draw_cb/main` e gli import `matplotlib`/`scipy` da `windgram_arome.py` (ridotto a 27 righe di soli shim) | Confermato da Giovanni. Il rendering utile e' la dashboard SVG (v2); il PNG tecnico non serve piu' e trascinava matplotlib/scipy sull'intero progetto. Dipendenze runtime ora solo `requests numpy`. |
| 2026-07-23 | **Contratto RICCO (opzione A)**: `Forecast` porta anche la fisica derivata (profilo vento risolto, profilo lapse, `wstar_slope_15min`, `climb_top`) | Scelto da Giovanni. E' l'unico modo per un confine netto vero: un consumatore (mobile/widget/API) disegna dal solo JSON, senza rifare fisica. `wstar_slope_15min` sta nel contratto perche' dipende dal dato a 15' (shf15), non ricavabile a valle dai soli scalari orari. |
| 2026-07-23 | **E3 spezzato in 4 sotto-passi (E3a–E3d)** invece di un unico refactor del renderer | E3 (far consumare il contratto a build_svg/build_chart) e' il passo piu' delicato (~500 righe che ricalcolano fisica). Spezzarlo tiene ogni commit piccolo e a golden invariato. Dettaglio in `REFACTOR.md`. **Sessione fermata a E2, si riprende da E3a.** |

## Fatti

| Data scoperta | Fatto | Come verificato |
|---|---|---|
| 2026-07-22 | La cella di griglia ICON-D2 per Piancavallo è il nodo **46.08°N/12.52°E**, estensione ≈2.23×1.54 km; il decollo è ~1.1 km dal centro cella (verso NE) | Sweep empirico di query a lat/lon leggermente spostate, osservando dove "scattava" il nodo restituito da Open-Meteo |
| 2026-07-22 | Il campo `elevation` della risposta forecast **non è** l'orografia interna che ICON-D2 usa per la sua fisica di cella — è un lookup DEM fine sul punto esatto (cambia con continuità anche spostando la query di poche decine di metri, restando sulla stessa cella) | Query a lat/lon variati di ~20-100 m, osservando `elevation` cambiare pur restando sullo stesso nodo orario |
| 2026-07-23 | `sensible_heat_flux` **è** disponibile a risoluzione **15 minuti** per icon_d2 via `minutely_15`, con valori genuinamente diversi ogni 15' (non il dato orario ripetuto) | Chiamata diretta all'endpoint con `minutely_15=sensible_heat_flux`, ispezione dei valori consecutivi |
| 2026-07-23 | `boundary_layer_height` **non** è disponibile a 15' (sempre `null`), anche quando `sensible_heat_flux` lo è | Stessa chiamata di cui sopra, campo sempre `None` su 96 slot testate |
| 2026-07-23 | Per Piancavallo, `boundary_layer_height` può essere **interamente `NaN` anche a risoluzione oraria** — `thermals()` in quel caso ricade sul fallback a particella secca (dentro `zi`) | Ispezione diretta di `surf['blh']` su una finestra di fetch reale — causa di un bug (vedi sotto) |
| 2026-07-23 | Bug trovato: la prima versione di `climb_ceiling`/rifinitura W\* interpolava `boundary_layer_height` **grezzo** invece di riusare `zi` (già risolto da `thermals()` col fallback) — quando `blh` è NaN il ramo "flusso reale a 15'" non si attivava mai, ricadendo silenziosamente sulla sola interpolazione oraria senza errori visibili | Confronto numerico diretto fra i due metodi: risultati identici finché non corretto (poi genuinamente diversi) |
| 2026-07-23 | La stima "Prossimo aggiornamento dati" (corsa + 3h) **non tiene conto del ritardo reale di pubblicazione** — verificato che alle 18:16 locali la corsa disponibile era ancora quella delle 14:00, non quella delle 17:00 come la stima prometteva | Confronto diretto fra `fetch_model_run()` e l'ora corrente, alle 18:16 del 2026-07-23 |
| 2026-07-21 | `windgram_arome.py` è la versione **completa** (695 righe, `plot()`+`main()` inclusi), non una versione "motore-only" come una vecchia nota in CLAUDE.md sosteneva | `grep "^def plot\|^def main" windgram_arome.py` |
| — | Wiki di GitHub su piano gratuito richiede repository **pubblico** | Verificato da Giovanni direttamente sull'interfaccia GitHub |

---

*Nota per le prossime sessioni: aggiungere una riga qui ogni volta che si prende una decisione di
design non ovvia dal codice, o si scopre un fatto empirico (specialmente su Open-Meteo/ICON-D2)
che ha richiesto una verifica per essere confermato. Non aspettare la fine della sessione.*
