# En målefeil vi fant — og hva den betydde

Dette dokumentet beskriver en feil i testoppsettet vårt, hvordan vi fant
den, og hva vi gjorde med den. Vi publiserer den fordi feilen er
instruktiv: den rammet alle målingene vi hadde gjort, og den treffer
nøyaktig den egenskapen vi var ute etter å måle.

---

## Feilen

Drama 3 er en stemmekloningsmodell. Den får to ting fra oss:

| | |
|---|---|
| **Referanselyd** | 8 sekunder med norsk tale |
| **Referansetekst** | hva det står i lyden |

Disse to må matche. Vi hadde ikke sjekket at de gjorde det.

**Referanselyden** (`ref/voice_ref_8s.wav`, 8,0 s) inneholder tre setninger:

> *«I dag skal vi lage et ukebladportrett med collage! Men hva er egentlig
> et ukebladportrett? Et portrett er et bilde av et menneske.»*

**Referanseteksten** vi brukte, hadde fire setninger:

> *«I dag skal vi lage et ukebladportrett med collage! Men hva er egentlig
> et ukebladportrett? Et portrett er et bilde av et menneske. **Når vi lager
> et ukebladportrett, bruker vi bilder fra blader til å sette sammen et nytt
> ansikt.**»*

Den fjerde setningen finnes ikke i lyden. I to av skriptene
(`scripts/run_norwegian.sh`, `scripts/run_english.sh`) brukte vi en helt
`ref/reference_text.txt` med **77 ord i seks setninger** — altså tre til
fire ganger så lang som det klippen faktisk inneholdt.

---

## Hvordan vi fant den

Vi transkriberte selve referanseklippen for å sjekke hva den inneholdt.
Whisper `small` gjengav de tre første setningene og stoppte midt i den
tredje. Da ble det tydelig at teksten vi ga modellen ikke passet med
lyden den skulle gjengi.

Etterpå fant vi samme avvik i alle kjøringsskriptene.

---

## Hva det gjorde med målingene

### Det rammet alle Drama 3-målinger

| Fil | Modell | Referansetekst | Klippen har |
|---|---|---|---|
| `norwegian.wav` | Q4_K_S | 6 setninger / 77 ord | 3 setninger |
| `valid_full_offload.wav` | Q4_K_S | 4 setninger | 3 setninger |
| `q2k_norsk_offload.wav` | Q2_K | 4 setninger | 3 setninger |
| `pruned_100_*.wav` | pruned | 4 setninger | 3 setninger |
| `drama3-small`, CosyVoice3, Chatterbox | — | samme oppsett | 3 setninger |

### Det påvirket ikke modellene

Referanseteksten er et **runtime-input ved generering**
(`--request-option "reference_text=..."`). Den inngår ikke i modellfilen.
Verken kvantiseringen, pruneringen, routingen eller destillasjonen
rører den. **Modellene er fine. Testoppsettet var feil.**

### Det ødde et viktig signal

Mekanismen er verdt å forstå: **referanselyden er kilden for aksenten.**
Modellen kopierer ikke språket fra teksten — den kopierer det fra lyden,
og bruker teksten til å vite hva den hører.

Når teksten og lyden ikke matcher, blir betingingen inkonsistent. Og
det forventede resultatet av inkonsistent betinging er nettopp det vi
observerte: **aksentdrift** — sluttkonsonanter faller bort, tall blir
uforståelige, modellen glider mot engelsk.

Vi hadde tilskrevet dette til kvantiseringen. Det kan fortsatt være
riktig, men vi kan ikke skille mellom kvantisering og dårlig
referanse uten å måle på nytt.

### Et eksperiment som avslører at tallene var støy

Samme modell, samme oppsett, to kjøringer:

| Kjøring | Referansetekst | WER (Whisper small) |
|---|---|---|
| A | 6 setninger (3–4× for lang) | **18,2 %** |
| B | 4 setninger (1 for lang) | **36,4 %** |

Den *dårligere* referansen ga det *bedre* tallet. Det betyr at WER-verdien
var dominert av måleverktøyets feil, ikke av modellens kvalitet.

---

## To feil, ikke én

1. **Referanseteksten var for lang** — denne rettingen.
2. **Måleverktøyet var for svakt** — Whisper `small` med tvunget `no`
   skrev norske ord i engelsk ortografi og bommet tall. Vi byttet til
   `NbAiLab/nb-wav2vec2-1b-bokmaal`, en norsk ASR med 6,33 % WER på
   norsk referansemateriale.

Med den norske ASR-en, på de gamle opptakene:

| Modell | Transkripsjon | WER |
|---|---|---|
| Q4_K_S | *mal et afirark i grønne og gule nyanser mal en stor sirkel på tu tjilefem komma fem sentimeter og fyller hele sirkelen med farge* | 36,4 % |
| Q2_K | *mal et a fire ark i grønne og gole nyanser **ma** en stor sirkel på **fainaufe antaan procentemitt** og fyller hele sirkelen med **ferge*** | 50,0 % |

Aksentdriften hos Q2_K er tydelig i transkripsjonen: *Mal* → **Ma**,
*gule* → **gole**, *farge* → **ferge**, og tallet *25,5 cm* blir
uforståelig. Men disse opptakene er fortsatt tatt med feil referansetekst,
så tallene er **ikke** sluttresultatet.

---

## Rettelsen

**Referansetekst:** `audio/referansetekst_8s.txt` — de tre setningene som
 faktisk står i klippen. Alle skripter bruker den nå.

**Måleverktøy:** `scripts/maal_norsk.py` (norsk ASR) og `scripts/maal_sett.py`
(hele settet). Whisper `small` beholdes bare til auto-språkdeteksjon.

**Testkorpus:** `audio/testtekster.txt` — vanlig norsk bokmål uten
sjarvord eller tall, fordi slike nettopp er det både modellen og
måleverktøyet snubler på.

**Aksent:** `scripts/lyttepakke.sh` — samme setning fra flere modeller,
vurdert av et menneske.

---

## Hva vi gjorde med de gamle tallene

**Vi fjernet dem.** De publiserte WER-tallene i `RAPPORT.md` er merket som
foreldete inntil de er målt på nytt med riktig referansetekst og norsk ASR.
Påstander om at «Q2_K gjør modellen amerikansk» er trukket tilbake
inntil de er dokumentert på nytt.

Det er ikke pinlig å gjøre en feil. Det er pinlig å publisere en feil
som et resultat.
