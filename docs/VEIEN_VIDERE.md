# Veien videre: fra nytt prosjekt til ferdig norsk modell

Dette dokumentet beskriver tre separate spor, fra det vi allerede har til en
ferdig modell. De er uavhengige av hverandre.

| Spor | Mål | Varer | Koster |
|---|---|---|---|
| **A** | Q4/Q2-blanding som passer bedre på 16 GB | 1 time | $0 |
| **B** | Destillasjon for å redde en pruned modell | 1–2 døgn | $10–30 (leid GPU) |
| **C** | LoRA-finetuning av en liten modell for norsk | 2–5 døgn | $0 (på din Mac) |

---

## Spor A: Q4/Q2-blanding (pågår nå)

### Ideen

Drama 3 Q4_K_S er 21,78 GiB. Q2_K er 15,88 GiB. Q2_K er raskere, men
oppfører seg mer «amerikansk».

I stedet for å velge én for alle lag, kan vi **beholde Q4_K på lagene som
bærer norsk språk**, og bruke Q2_K på lagene som er språkneutrale.

**Dette løser problemet som pruning ikke gjorde.** Ved pruning blir
routingen ødelagt fordi routeren fortsatt peker på eksperter som ikke finnes.
Ved kvantisering blir **routeren uskadd** — det er bare vektenes presisjon
som varierer per lag.

### Teknisk implementasjon

`audiocpp_gguf` har `--keep-type <tensor-prefix>*=<type>`, som kan holde ulik
type per lag. Men det har to forbehold:

1. **Verktøyet kan bare kvantisere fra F32/F16-kilder.** Koden krever
   `source_is_float` for å kvantisere. Et allerede kvantisert GGUF kan derfor
   ikke re-kvantisere.
2. **3D-eksperttensorer kvantiseres bare via eksplisitt `--keep-type`.**
   Standard-`--type` gjelder ikke 3D-tensorer.

Løsningen er to trinn:

```bash
# Trinn 1: dekvantiser ekspertene Q4_K -> F16 (Python, gguf-biblioteket)
python3 scripts/bland_prep.py \
    modeller/drama3-Q4_K_S.gguf /tmp/mix_f16.gguf lag_q4.txt
python3 scripts/fiks_offsets.py /tmp/mix_f16.gguf

# Trinn 2: kvantiser per lag (C++-verktøyet)
./bin/audiocpp_gguf --input /tmp/mix_f16.gguf --output modeller/drama3-mix.gguf \
    --type q4_k --family fish_drama3 --model-spec bin/model_specs --root sidecars/ \
    --keep-type "codec_weights*=f16" \
    --keep-type "model_weights/audio_decoder*=orig" \
    --keep-type "model_weights/model.language_model.layers.0.mlp.experts.*=q4_k" \
    ... (ett flagg per lag)
```

### Å finne ut hvilke lag som er norsk-relevante

Dette er det uvedkommendeende. Routing-statistikken vi samlet ga **identiske
tall for alle 40 lag** (7 eksperter, 87,5 % dekning), fordi
instrumenteringen bare fanget decode-stien — ett token om gangen. Det er
for tynt til å rangere lag.

Tre veier videre, fra billig til dyrt:

**A1. Empirisk søk (billigst, ~1 time per fordeling)**
Bygg miksen med 20/40-deling, mål norsk WER. Prøv andre delinger
(10/30, 30/10, 0/40, 40/0) og se hvilken som gir best avveining mellom
størrelse og kvalitet. Vi vet allerede hvordan 0/40 oppfører seg: det er
Q2_K, som er «amerikansk».

**A2. Sammenlign norsk mot engelsk routing (middels)**
Kjør modellen på norsk og på engelsk, og sammenlign hvilke eksperter som
velges. Lag der de to språkene bruker **helt forskjellige** eksperter, er
språkspesifikke og bør ha Q4_K. Lag der de bruker de samme ekspertene, er
språkneutrale og tåler Q2_K. Dette krever at instrumenteringen fanger
prefill — vi må lese `expert_ids` **etter** at grafen er kjørt, ikke mens den
bygges.

**A3. Likhet mot fullmodellen (dyrest)**
For hvert lag, sammenlign ekspertenes vekter mellom Q4_K_S og en lavere
kvantisering, og se hvor mye informasjon som går tapt i de lagene der
norsk routingen er mest konsentrert.

**Anbefaling: A1 først.** Den er billig og gir et svar direkte.

### Forventet resultat

| Konfigurasjon | Størrelse | RTF | Norsk |
|---|---|---|---|
| Q4_K_S (alle lag) | 21,78 GiB | 24,0 | 18–36 % WER |
| Q2_K (alle lag) | 15,88 GiB | 12,7 | 45,5 % WER |
| **Miks 20/40** | **~18,8 GiB** | **~18** | **? — måles** |
| Miks 30/10 | ~20,2 GiB | ~21 | ? |

Merk: en mikst modell trenger fortsatt disk-offloading på 16 GB, siden selv
15,88 GiB ikke får plass resident.

---

## Spor B: Destillasjon (redder en pruned modell)

### Når trenger vi det?

Bare hvis vi vil ha en modell **mindre enn 16 GiB** som likevel snakker
norsk godt. Da må vi prune, og pruning uten destillasjon ødelegger modellen
(dette er dokumentert i [`PRUNING.md`](PRUNING.md)).

### Hva drama3-small gjorde

Fire trinn, utført på en 96 GB GPU:

1. **Prune eksperter** basert på routing-masse målt på strategisk valgt tale
   (japansk + engelsk + kodet bytting + tagger). Vi ville brukt norsk.
2. **Refit routere lag for lag** — juster router-vektene slik at de
   gjenstående ekspertene får riktig sannsynlighetsmasse. Dette er det
   viktigste trinnet.
3. **Destillere 100 steg** mot den eksakte FP8-originalen, med KL på de
   semantiske og audio-tower-fordelingene. Data: ~282 timer ekte tale +
   5 501 linjer lest av originalmodellen.
4. **Quantisere tilbake** til det ønskede formatet.

De måtte stoppe ved 100 steg fordi mer destillasjon ga dårligere
fristillingsresultat — modellen begynte å miste innhold etter første
setning.

### Vårt opplegg

Samme, men med norsk:

- **Prune:** 100 eksperter i lag 3–35, 256 i lag 0/1/2 og 36 (4 624 av
  10 240 ekspertspor). Vi har allerede verktøyet.
- **Router-refit:** må implementeres. Trenger en GPU.
- **Destillasjon:** trenger en GPU, ~96 GB. Vi har allerede
  `routing_stats`-instrumenteringen som kan brukes til å måle dekningsgrad.
- **Validering:** kjøre vårt måleoppsett (WER + auto-språk + F0) på
  resultatet.

### Kostnad

| Alternativ | Time | Kostnad |
|---|---|---|
| Leid H100 80 GB (Vast.ai) | ~6–10 t | $10–20 |
| Leid A100 80 GB | ~10–16 t | $7–13 |
| Egen maskin | — | Dekker ikke 16 GB |

Vi trenger ~96 GB VRAM. A100 80 GB er litt for lite til å være trygg; H100
er tryggest.

### Trinnene i detalj

```bash
# 1. Routing-statistikk for norsk (CPU, ~1 time)
#    Vi må først fikse instrumenteringen til å fange prefill,
#    slik at vi får ekte routing-fordeling per lag.

# 2. Prune med beskyttede lag
python3 scripts/prune_gguf.py \
    --input modeller/drama3-Q4_K_S.gguf \
    --output modeller/drama3-pruned-100.gguf \
    --stats routing_no.pt \
    --keep 100 --protected-layers 0,1,2,36 --protected-count 256

# 3. Router-refit + destillasjon (GPU, leid)
#    Bruk drama3-small-patchen som referanse:
#    https://huggingface.co/pentacoxian-dev/drama3-small-GGUF
#    (tools/ inneholder prune_experts.py og destillasjonskriptene)

# 4. Konverter tilbake til GGUF med audio.cpp sine verktøy
python3 scripts/convert_pruned_drama3.py \
    --checkpoint modeller/drama3-pruned-100/ --output modeller/drama3-pruned-100.gguf \
    --quantized-output modeller/drama3-pruned-100-q4.gguf \
    --gguf-tool ./bin/audiocpp_gguf --expert-type q4_k --backbone-type q8_0

# 5. Valider
./scripts/valider.sh modeller/drama3-pruned-100-q4.gguf
```

---

## Spor C: LoRA-finetuning av en liten modell (på din Mac)

Dette er sporet som **ikke krever GPU og ikke krever Drama 3 i det hele tatt**.

### Idéen

CosyVoice3 er 0,5 milliarder parametre og kjører på din Mac i dag. Den
norske LoRA-en du allerede har ble laget av en norsk modell. Det neste steget er
å trene en LoRA som gjør at **CosyVoice3 snakker norsk av seg selv**, uten
norsk referansestemme.

### Hvorfor dette er det mest realistiske sporet

| | Drama 3 | CosyVoice3 |
|---|---|---|
| Parametere | 35B | 0,5B |
| Trenbart på 16 GB Mac | Nei | Ja (LoRA) |
| Norsk i dag | Ja | Med LoRA |
| Hastighet på Mac | RTF 24 | RTF 10,8 |
| Trenger GPU | Ja | Nei |

### Hvor vi henter norsk data

**Språkbanksen (CC0 — fri bruk):**

| Korpus | Innhold | Lisens |
|---|---|---|
| [NST Norwegian Speech Synthesis](https://www.nb.no/sprakbanken/en/resource-catalogue/oai-nb-no-sbr-15/) | 5 363 uttrykk, 1 mannlig stemme | CC0 |
| [NB Tale](https://www.nb.no/sprakbanken/en/resource-catalogue/oai-nb-no-sbr-31/) | 7 600 uttrykk, ~12 t, 380 talere, 12 dialekter | CC0 |
| [NST Norwegian ASR](https://www.nb.no/sprakbanken/en/resource-catalogue/oai-nb-no-sbr-13/) | 359 760 uttrykk, 980 talere | CC0 |
| [NST Norwegian Dictation](https://www.nb.no/sprakbanken/en/resource-catalogue/oai-nb-no-sbr-14/) | 33 360 uttrykk, 144 talere | CC0 |
| [Parlamentskorpuset](https://www.nb.no/sprakbanken/en/resource-catalogue/oai-nb-no-sbr-58/) | ~59 t, 203 talere | CC0 |
| [Tuva](https://www.nb.no/sprakbanken/show?serial=oai:nb.no:sbr-44&lang=) | 24 t, 40 talere | CC-BY 4.0 |
| [Common Voice Nynorsk](https://mozilladatacollective.com/datasets/cmu5ox9rt00ylmh073m7dl7ij) | 1 578 klipp, 42 talere | CC0 |

**Anbefaling for vårt formål: NST Norwegian Speech Synthesis (SBR-15).**
Den er **allerede lest opp for synteseformål**, inneholder norsk tekst, og er
CC0. Den er imidlertid én mannlig stemme — for en stemme som passer din egen
stemme er det bedre med rå opptak.

**For din egen stemme:** 20–30 minutter med opptak på 24 kHz mono er nok til
en LoRA. Det erformatet F5-TTS-dokumentasjonen beskriver, og det er samme
krav CosyVoice3 har.

**Fra internett:** Podkaster, nyhetsinnlegg, opptatte bøker — alt på norsk
— kan brukes, men lisensen må tillate det. Commons og Nasjonalbibliotekets
CC0-korpus er tryggest.

### Dataformat

CosyVoice3 trenger parquet med tale-tokens og stemme-embeddings. Vi har allerede
et lignende format i `~/CosyVoice/sim_data/`:

```
wav.scp     linje_id /absolutt/sti.wav
text        linje_id transkript
utt2spk     linje_id spk_id
spk2utt     spk_id linje_id
```

Referansen `instavar/cosyvoice3-lora-finetuning` har komplett oppskrift for
trening med PEFT + DeepSpeed, og beskriver hvordan dataene pakkes.

### Trinn

```bash
# 1. Samle data
#    Alternativ A: ditt eget opptak
#    24 kHz, mono, WAV 16-bit. 20-30 minutter, ca. 200 setninger.
for f in opptak/*.wav; do
  ffmpeg -i "$f" -ar 24000 -ac 1 -c:a pcm_s16le "data/24k/$(basename "$f")"
done

#    Alternativ B: NST Norwegian Speech Synthesis (CC0)

# 2. Transkriber (Whisper) og lag train/dev/test-manifester
python3 scripts/forbered_trainedata.py --kilde data/24k --ut data/trening

# 3. Tren LoRA
pip install peft
torchrun --nnodes=1 --nproc_per_node=1 \
  tools/train_cosyvoice3_lora.py \
  --train_engine deepspeed \
  --model llm \
  --config examples/libritts/cosyvoice3/conf/cosyvoice3.yaml \
  --train_data data/trening/train/parquet/data.list \
  --cv_data data/trening/dev/parquet/data.list \
  --qwen_pretrain_path pretrained_models/Fun-CosyVoice3-0.5B/CosyVoice-BlankEN \
  --checkpoint pretrained_models/Fun-CosyVoice3-0.5B/llm.pt \
  --model_dir exp/norsk-lora \
  --deepspeed_config configs/ds_stage2_lora.json \
  --lora-r 16 --lora-alpha 64 --lora-dropout 0.05 \
  --lora-target-modules q_proj,k_proj,v_proj,o_proj
```

### Kostnad og tid

| | |
|---|---|
| GPU | Nei — 0,5B-modell trenes på 16 GB Mac (kan ta timer) |
| Tid for data | 1–2 døgn (opptak + transkripsjon) |
| Tid for trening | Timer til et døgn, avhengig av datamengde |
| Pris | $0 |

---

## Anbefalt rekkefølge

1. **Fullfør spor A** (miksen). Varer en time, gir svar på om lag-basert
   kvantisering er verdt det. Resultatet kan publiseres uavhengig.
2. **Paralleliser spor C** (LoRA). Den krever ingen GPU og kan gå mens vi
   venter på leid GPU.
3. **Bestill GPU** til spor B når vi vet hvilke lag som skal ha Q4_K —
   altså etter at spor A har gitt svar på lag-fordelingen.

Spor A og C er uavhengige og kan gå samtidig. Spor B avhenger av resultatet
fra A.

---

## Åpne spørsmål

- **Hvor mye norsk data trenger vi for LoRA?** Instavars kjøring brukte
  10 850 rader, men dokumentasjonen sier at det ikke fastslår et minimum.
  For en stemme er 30–60 minutter trolig nok.
- **Bokmål eller nynorsk?** Drama 3 er trent på begge. For norsk
  bokmål-folk tror vi bokmål-dominert data gir best resultat.
- **Kan vi trene en norsk LoRA direkte på Drama 3?** Ja, men det krever
  96 GB GPU og 35B-parametermodell. CosyVoice3 er mye rimeligere og
  gir norsk like bra i praksis.
- **Trenger vi dialektspesifikt data?** Drama 3 dekker 83 språk, men
  norske dialekter (trøndelag, bergenssk, oslensk) er ikke separate
  språk i modellen. NB Tale har 12 dialekter.
