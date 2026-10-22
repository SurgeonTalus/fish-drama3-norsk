# Naturlig TTS på norsk med Fish Audio Drama 3

**Lag norsk tale med din egen stemme — direkte på en MacBook Pro med 16 GB RAM.**

[Fish Audio Drama 3](https://huggingface.co/fishaudio/drama-3) er laget for
NVIDIA-grafikkort og veier 22 GB. Macen din har 16 GB. Løsningen er
**ekspert-offloading**: de store ekspert-vektene ligger på disk og hentes inn
mens de brukes.

---

## Resultatet først

Målt på **Apple M1 Pro MacBook Pro, 16 GB RAM, macOS 27.0.1**.

### Anbefalt oppsett

| | |
|---|---|
| **Modell** | **Q4_K_S** (21,78 GiB) — best kvalitet, 9,5/10 i høring |
| **Kjøring** | **serveren** — modellen lastes én gang, referansen bufres |
| **Cache** | `expert_cache_size=32` (64–80 når du har RAM til det) |
| **Parallelle lesninger** | `expert_read_threads=16` |
| **Hastighet** | **RTF 18,7** med cache 32, **17,1** med 64, **15,3** med 80 |
| **Minne** | 7,4 GB fysisk footprint med cache 32 — se advarselen under |

```bash
python3 scripts/server.py start          # start serveren
python3 scripts/server.py snak "Hei hei"  # lag lyd
python3 scripts/server.py frigi           # frigjør RAM når du er ferdig
```

> **Merk: modellen tar 7,4 GB av de 16 GB mens den ligger i minnet.**
> Det er plass til den *alene*, men ikke samtidig med en LLM, Draw Things
> og et bildegenereringsverktøy. På en maskin med alt annet kjørende ble
> RTF 18,7 → **163,7**, fordi systemet swappet: serveren hadde 1,7 millioner
> sideinnlastinger per klipp.
>
> **Løsningen er `drop_expert_cache=true`** (standard fra nå): ekspertenes
> sider kastes ut av page cache med én gang de er lest, så modellen ikke
> fyller RAM-en og jager ut alt annet. Samme klipp, samme maskin, samme
> press: **RTF 23,5** — og sha256-identisk lyd.
>
> Derfor: `python3 scripts/server.py frigi` når du er ferdig med lyden, og
> MCP-laget laster modellen automatisk og loser den igjen rett etter hvert
> klipp. Vent er `idle_unload_ms` (10 min) — alt som kjører i mellomtiden
> taper minne til modellen.
>
> `min_free_memory_mb` i `scripts/innstillinger.json` står på **0** (av).
> Serverens egen estimat er vekten × 1,5 = 32,79 GiB for en 21,78 GiB
> modell, altså 4× mer enn den målte toppen: guarden ville avvist en modell
> som passer fint. Se `SETUP.md` for hele forklaringen.

**Servern er den anbefalte måten å kjøre.** Modellen lastes én gang i stedet
for ved hver forespørsel, referansens codec-koding og ryggrad-prefill gjøres
bare én gang, og `frigi` gir RAM-en tilbake når du vil — nyttig når du kjører
en LLM ved siden av. Detaljene i [SETUP.md](SETUP.md#serveren--anbefalt-måte-å-kjøre).


### Kvalitetsverifikasjon

Referansen (8 s) og modellen sier **nøyaktig samme tekst** — se
`output/verifisering/`:

> «Det er en 99 % klone. Jeg er helt sikker på at det er meg — fortelleren.
> Jeg ville ikke lagt merke til det hvis jeg ikke hadde visst.»

Det overlever 4-bits kvantisering av en 35B MoE der bare ~17 % av
ekspertene er resident om gangen, og et routing-bilde som er flatt
(193–255 av 256 eksperter per lag). Detaljene i
[docs/LYTTETEST.md](docs/LYTTETEST.md).

**Sett opp alt med ett skript:**

```bash
python3 scripts/oppsett.py --info      # hva anbefales på din maskin
python3 scripts/oppsett.py --test      # mål og finn beste innstilling
python3 scripts/oppsett.py --installer # skriv konfigurasjonen
```

Full guide: **[SETUP.md](SETUP.md)**.

### De viktigste funnene

**1. Hastighet kom fra cachen, ikke fra modellen.**

Vi startet med `expert_cache_size=8` — nøyaktig så stor som ett tokens
ekspertsett, siden Drama 3 velger 8 eksperter per lag. Da ble hvert token
tvunget til en disklesning.

| cache | treffrate | lest | RTF (16 tråder) |
|---|---|---|---|
| 8 | 20 % | 111,6 GB | 44,2 (1 tråd) |
| 32 | 42 % | 57,3 GB | 16,8 |
| **64** | **55 %** | **44,5 GB** | **15,9** |
| 96 | 64 % | 36,0 GB | 19,7 (8 tråder) |

**2. Parallelle disklesninger var den største enkeltgevinsten.**

Vi leste ekspertene sekvensielt og fikk 327 MB/s av en disk som klarer
2–3 GB/s. Med 16 tråder parallelt:

| tråder | RTF | disklesning |
|---|---|---|
| 1 | 25,5 | 175,4 s |
| 4 | 19,4 | 122,7 s |
| 8 | 17,3 | 102,9 s |
| **16** | **16,8** | **98,3 s** |

**RTF 25,5 → 16,8 (−34 %) med bit-identisk utdata.** Med cache 64
kommer vi ned i **RTF 15,9 (−38 %)**. Cache 96 blir dårligere igjen:
opplastingen til GPU-en blir flaskehals (41,6 s).

**3. Drama 3 snakker norsk.** En norsk ASR (NB AI Labs wav2vec2) skriver ut
riktig norsk, og Whisper finner språket automatisk.

**4. Kvalitetsforskjellene mellom kvantiseringene er små — målingen vår
var feil.** Vi brukte en for lang referansetekst og et for svakt
måleverktøy, og fant at Q2_K var «amerikansk». Med riktig oppsett er
forskjellene 1–2 ord per setning. Se [`docs/RETTING.md`](docs/RETTING.md).

**5. Det er ingen liten «norsk-ekspert»-gruppe.** Én norsk setning bruker
193–255 av 256 eksperter i hvert lag. Se [`docs/ROUTING.md`](docs/ROUTING.md).

**6. Pruning virker teknisk, men ødelegger kvaliteten uten trening.** 21,8 →
12,5 GiB og 6,3× raskere, men modellen blir ødelagt uten router-refit og
destillasjon (som krever en 96 GB GPU). Se [`docs/PRUNING.md`](docs/PRUNING.md).

### Modellene

| Modell | Fil | Kvalitet | RTF | Merknad |
|---|---|---|---|---|
| **Q4_K_S** | 21,78 GiB | **9,5/10** | **17,1** | **Anbefalt** |
| Q3_K_S | 18,93 GiB | 9/10 | 15,9 | 2,85 GiB mindre, litt raskere |
| Q2_K | 15,88 GiB | 7/10 | 14,4 | /r/ går tapt |
| F32-routers | 22,97 GiB | 9,4/10 | — | Ingen bedre enn Q4_K_S |
| drama3-small | 9,74 GiB | 59 % WER | 11,2 | Destillert for japansk/engelsk |

`python3 scripts/oppsett.py --modeller` viser hvilken modell som passer
**din** maskin.

### Sammenligning med andre modeller

| Modell | Norsk | Engelsk | RTF |
|---|---|---|---|
| **Drama 3** | **9–9,5/10 i høring** | holder språket | 16,8 |
| CosyVoice3 + norsk LoRA | 8/10 i høring | mister språket | 10,8 |
| Chatterbox v3 | dårlig | mister språket | 5,8 |

Detaljer: [`docs/RAPPORT.md`](docs/RAPPORT.md), høring:
[`docs/LYTTETEST.md`](docs/LYTTETEST.md).

---

## Innhold

1. [Hva du trenger](#hva-du-trenger)
2. [Installasjon](#installasjon)
3. [Lage tale](#lage-tale)
4. [Lydklipp](#lydklipp)
5. [Sammenligning av modellene](#sammenligning-av-modellene)
6. [Pruning](#pruning)
7. [Ordbok](#ordbok)
8. [Feilsøking](#feilsøking)
9. [Veien videre](#veien-videre)
10. [Kilder og prosjekter](#kilder-og-prosjekter)

### Dokumentasjon

| Dokument | Innhold |
|---|---|
| [SETUP.md](SETUP.md) | **Oppstartsguide for en ny Mac** |
| [docs/RAPPORT.md](docs/RAPPORT.md) | Alle målinger, metoder og begrensninger |
| [docs/LYTTETEST.md](docs/LYTTETEST.md) | Høring, og hva kvantiseringen faktisk gjør |
| [docs/ROUTING.md](docs/ROUTING.md) | Ekspertruting: hvor er de norske ekspertene? |
| [docs/EXPERTCACHE.md](docs/EXPERTCACHE.md) | Cachen: treffrate, RAM og hastighet |
| [docs/PARALLELLESNING.md](docs/PARALLELLESNING.md) | Parallelle ekspertlesninger |
| [docs/MIXER.md](docs/MIXER.md) | Per-lag blandet presisjon |
| [docs/LAGDROPUTING.md](docs/LAGDROPUTING.md) | Kutt i lag: hva fungerer |
| [docs/PINNING.md](docs/PINNING.md) | Låsing av varme eksperter |
| [docs/RETTING.md](docs/RETTING.md) | Målefeilen vi fant og rettet |
| [docs/VEIEN_VIDERE.md](docs/VEIEN_VIDERE.md) | Hva som gjenstår |

## Hva du trenger

| | |
|---|---|
| **Mac** | Apple Silicon: M1, M1 Pro, M2, M3, M4 |
| **RAM** | 16 GB anbefales. 8 GB fungerer med den lille modellen |
| **Disk** | 30 GB ledig (22 GB til modellen) |
| **Nett** | Trenger 22 GB nedlasting |
| **Tid** | 15–20 min for installasjon |

Ingen CUDA, ingen NVIDIA, ingen Python-pakker å installere manuelt.

---

## Installasjon

### 1. Last ned

```bash
git clone https://github.com/SurgeonTalus/fish-drama3-norsk.git
cd fish-drama3-norsk
```

### 2. Hent runtime og modell

Runtime-en er ferdigbygd for macOS med Metal. Modellen er den offisielle
Drama 3 i Q4_KS-kvantisering.

```bash
mkdir -p bin modeller

# Runtime (~32 MB) — audio.cpp, bygget for macOS arm64 Metal
curl -L -o runtime.tar.gz \
  https://github.com/0xShug0/audio.cpp/releases/download/v0.9.2-drama3-base-small/audio-v0.9.2-drama3-base-small-bin-macos-arm64-metal.tar.gz
tar -xzf runtime.tar.gz -C bin --strip-components=1

# Modellen (22 GB) — kvantisert versjon av fishaudio/drama-3
curl -L -o modeller/drama3-Q4_K_S.gguf \
  https://huggingface.co/Jmica/Drama-3-GGUF/resolve/main/drama-3-backbone-4bit-experts-Q4_K_S.gguf
```

### 3. Trenger du ffmpeg?

Bare hvis du vil lage en referansestemme fra en egen opptakelse:

```bash
brew install ffmpeg
```

### 4. Sjekk at det virker

```bash
./bin/audiocpp_cli --version
```

Du skal se `backends: cpu,metal`.

---

## Lage tale

### Med serveren (anbefalt)

```bash
python3 scripts/server.py start              # én gang
python3 scripts/server.py snak "Mal et A4-ark i grønne og gule nyanser." \
  -o output/tale.wav
open output/tale.wav
```

Serveren bruker referansestemmen og transkriptet fra `audio/` automatisk.
`frigi` slipper modellen fra RAM når du er ferdig.

### Med CLI-en (uten server)

Referansen er et kort opptak (10–30 sekunder) av stemmen din, med et
transskript. Filen `audio/referanse_stemme.wav` i dette repoet er et eksempel.

```bash
./bin/audiocpp_cli \
  --task clon \
  --family fish_drama3 \
  --backend metal \
  --mode offline \
  --model modeller/drama3-Q4_K_S.gguf \
  --voice-ref audio/referanse_stemme.wav \
  --request-option "reference_text=I dag skal vi lage et ukebladportrett med collage! Men hva er egentlig et ukebladportrett? Et portrett er et bilde av et menneske. Når vi lager et ukebladportrett, bruker vi bilder fra blader til å sette sammen et nytt ansikt." \
  --text "Mal et A4-ark i grønne og gule nyanser. Mal en stor sirkel på 25,5 cm og fyll hele sirkelen med farge." \
  --max-tokens 400 --seed 42 --threads 10 \
  --session-option fish_drama3.disk_experts=true \
  --session-option fish_drama3.expert_cache_size=32 \
  --session-option fish_drama3.expert_read_threads=16 \
  --session-option fish_drama3.cpu_expert_layers=0 \
  --session-option fish_drama3.context_length=2048 \
  --session-option fish_drama3.codec_backend=cpu \
  --session-option fish_drama3.codec_encoder_chunk_samples=65536 \
  --out tale.wav
```

Åpne i Finder:

```bash
open tale.wav
```

### Hva flaggene gjør

| Flagg | Hvorfor |
|---|---|
| `fish_drama3.disk_experts=true` | **Nødvendig på 16 GB.** Ekspertene ligger på disk og hentes inn mens de brukes. |
| `fish_drama3.drop_expert_cache=true` | **Kaster ekspertenes sider ut av page cache etter lesning.** Modellen er større enn RAM, så uten dette fyller page cache seg med modellens sider og macOS kaster ut alt annet. Målt under press: RTF 163,7 → 23,5, og lyden er bit-identisk. |
| `fish_drama3.expert_cache_size=32` | Hvor mange eksperter som holdes i RAM om gangen. 32 = 8,4 GB peak. 64 = 9,5 GB. 80 = 10,3 GB. |
| `fish_drama3.cpu_expert_layers=0` | Ekspertene kjøres fortsatt på GPU-en. Bare vektene strømmes. |
| `fish_drama3.codec_backend=cpu` | Flytter lydkoderen (747 MB) ut av GPU-minnet. Uten dette kan prosessen bli avsluttet. |
| `fish_drama3.codec_encoder_chunk_samples=65536` | Deler referanse-encodingen i biter, slik at toppminnet blir lavere. |
| `fish_drama3.context_length=2048` | Plass til tekst + referanse + generert lyd. |
| `--max-tokens 400` | Maks antall lydbiter. 21,5 biter ≈ 1 sekund. |

### Med egen stemme

```bash
# 1. Gjør opptaket klar: 44,1 kHz, mono, 8-12 sekunder
ffmpeg -i min-opptak.m4a -t 10 -ar 44100 -ac 1 -c:a pcm_s16le referanse.wav

# 2. Skriv ned hva du sa i referanse.wav
echo "Her er teksten du sa i opptaket" > referanse_tekst.txt
```

Bruk så `--voice-ref referanse.wav` og
`--request-option "reference_text=$(cat referanse_tekst.txt)"`.

**Transkriptet er viktig.** Uten et korrekt transkript blir stemmen uklar.

---

## Lydklipp

Hør selv. Alle filene ligger i `audio/`.

| Fil | Hva det er |
|---|---|
| `norsk_full_q4k.wav` | Drama 3 full, norsk — **riktig** |
| `valid_full_offload.wav` | Drama 3 full, norsk, målt med disk-offloading (RTF 24,0) |
| `norsk_small_ubrukelig.wav` | Drama 3 liten, norsk — **ubrukelig** |
| `q2k_norsk.wav` | Drama 3 Q2_K, norsk — brukbart, men dårligere enn Q4_K_S |
| `cosyvoice_norsk.wav` | CosyVoice3 + norsk LoRA, norsk |
| `chatterbox_norsk.wav` | Chatterbox v3, norsk |
| `engelsk_full_q4k.wav` | Drama 3 full, engelsk — ren engelsk |
| `cosyvoice_engelsk.wav` | CosyVoice3, engelsk — **høres ut som svensk** |
| `chatterbox_engelsk.wav` | Chatterbox v3, engelsk — **høres ut som norsk** |
| `pruned_100_alle_lag.wav` | Pruned til 100 eksperter — **ødelagt** (pruning uten trening) |
| `pruned_100_uten_destillasjon.wav` | Pruned med beskyttede lag — **ødelagt** (degenerert repetisjon) |
| `referanse_stemme.wav` | Referansestemmen som ble brukt |

---

## Sammenligning av modellene

Full oversikt med alle målinger: [`docs/RAPPORT.md`](docs/RAPPORT.md).

### Presisjon

| Modell | Språk | Ordfeilrate | Whisper sier språket er |
|---|---|---|---|
| **Drama 3 Q4_K_S** | norsk | **18–36 %** | norsk ✓ |
| **Drama 3 Q4_K_S** | engelsk | **6 %** | engelsk ✓ |
| CosyVoice3 + LoRA | norsk | 32 % | norsk ✓ |
| CosyVoice3 + LoRA | engelsk | 12 % | **svensk** ✗ |
| Chatterbox v3 | norsk | 59 % | norsk ✓ |
| Chatterbox v3 | engelsk | 15 % | **norsk** ✗ |
| Drama 3 IQ3_XXS | norsk | 59 % | norsk ✓ |

Dette bekrefter en vanlig observasjon om CosyVoice: den har mer aksent og
drifter mer. CosyVoice3 i denne testen hadde en norsk LoRA, og det er den som
trakk engelsken mot norsk — og forbi, fordi modellen er språkbundet til
referansen.

Drama 3 ble trent på 83 språk og holder derfor språket uansett hvilken
referanse du gir den.

### Hastighet

| Modell | RTF | Tid for 9 s norsk | Disk lest |
|---|---|---|---|
| Chatterbox v3 | **5,8** | 52 s | 0 |
| CosyVoice3 + LoRA | **10,8** | 97 s | 0 |
| Drama 3 IQ3_XXS | 11,2 | 100 s | 0 |
| Drama 3 Q4_K_S | 28,8 | 259 s | 351 GB |

Drama 3 er tregest fordi den er 35 milliarder parametere og må lese
ekspertene fra disk. Til gjengjeld er den den mest norske.

---

## Pruning

Du trenger ikke kjøre Drama 3 full. Vi har vist at man kan **kutte bort
eksperter som aldri brukes**, direkte i modellfilen:

```bash
# 1. Samle routing-statistikk for norsk (kjører modellen over norsk tekst)
#    og lager et bilde av hvilke eksperter norsk faktisk bruker
python3 scripts/tekst_til_pt.py routing_no.txt routing_no.pt

# 2. Kutt fra 256 til 100 eksperter per lag
python3 scripts/prune_gguf.py \
  --input modeller/drama3-Q4_K_S.gguf \
  --output modeller/drama3-pruned-100.gguf \
  --stats routing_no.pt --keep 100 --criterion mass
```

**Resultat: 21,78 GiB → 12,52 GiB, 6,3x raskere.** Ingen nedlasting av
original-checkpointet, ingen 68 GiB intermediate-fil, ingen ny kvantisering.
Det er en ren byte-kopiering.

**Men:** uten router-refit og destillasjon ødelegger kuttet modellen
kvaliteten. Det er et viktig negativt funn, dokumentert i
[`docs/PRUNING.md`](docs/PRUNING.md).

---

## Ordbok

Ord og forkortelser du møter i loggene og i dokumentasjonen.

### Ytelse og minne

| Forkortelse | Betydning | Forklaring |
|---|---|---|
| **RTF** | Real-Time Factor | Hvor mange ganger så lang tid brukte maskinen som lydens lengde. RTF 4,7 betyr at 1 sekund lyd tok 4,7 sekunder. **Lavere er bedre.** RTF 1,0 = «i sanntid». |
| **WER** | Word Error Rate | Ordfeilrate. Andelen ord i den genererte lyden som er feil sammenlignet med teksten du skrev. **Lavere er bedre.** 0 % = ordrett. |
| **CER** | Character Error Rate | Som WER, men per tegn. |
| **VRAM** | Video RAM | Minne på grafikkortet. Finnes ikke på Mac — der deler CPU og GPU samme minne. |
| **Unified memory** | Enhetsminne | Mac-teknologi der CPU og GPU deler ett minnespor. Derfor kan en Mac med 16 GB kjøre en 22 GB-modell. |
| **Swap** | Byttefil | Når minnet er fullt, legger macOS data på disk. Mye swap = alt går trege, og prosesser kan bli avsluttet **uten varsel**. |
| **Footprint** | Minnebruk | Hvor mye minne prosessen faktisk bruker. |

### Modell og vekter

| Forkortelse | Betydning | Forklaring |
|---|---|---|
| **TTS** | Text-to-Speech | Tale fra tekst. |
| **ASR** | Automatic Speech Recognition | Tale til tekst. |
| **MoE** | Mixture of Experts | En modell der bare noen «eksperter» aktiveres per ord. Drama 3 har 35 milliarder parametere, men bruker bare 3 milliarder om gangen. |
| **A3B** | Active 3B | 35B totalt, 3B aktive per token. |
| **GGUF** | GGML Format | Filformatet modellene ligger i. Kan leses direkte uten å pakke om. |
| **Q4_K_S** | 4-bits kvantisering | Vektene er komprimert til 4 bit. Kvaliteten er nesten like god som full presisjon, men filen blir mye mindre. |
| **IQ3_XXS** | 3-bits kvantisering | Enda mindre og raskere, men med mer kvalitetstap. |
| **Q2_K** | 2-bits kvantisering | Minst mulig størrelse, størst kvalitetstap. |
| **FP8 / BF16 / FP16** | Flyt-tallsformater | Full presisjon. 8-, 16- og 32-bit. |
| **bpw** | Bits per weight | Biter per vekt. 2,13 bpw for Q4_K_S. Det er grunnen til at 35B-modellen blir 22 GB i stedet for 70 GB. |
| **Pruning** | Beskjæring | å fjerne deler av en modell som ikke trengs. |
| **Distillasjon** | — | Å lære en mindre modell å etterligne en større. |
| **LoRA** | Low-Rank Adaptation | Liten ekstra treningsfil som tilpasser en stor modell. |
| **Hadamard-rotasjon** | — | Matematisk transformasjon modellen bruker. Derfor kan ikke vanlig llama.cpp lese filene. |
| **Routing** | — | Hvilke eksperter modellen velger for hvert ord. |

### Runtime

| Forkortelse | Betydning | Forklaring |
|---|---|---|
| **Metal** | — | Apples grafikk-API. Tilsvarer CUDA på NVIDIA-kort. |
| **CUDA** | — | NVIDIAs grafikk-API. Drama 3 er bygget for dette. |
| **Prefill** | — | Når modellen leser hele teksten og referansen på forhånd. Koster tid før talen begynner. |
| **Decode** | — | Når modellen genererer lyd ord for ord. |
| **Context / kontekstvindu** | — | Hvor mye tekst og lyd modellen holder i minnet samtidig. |
| **KV-cache** | — | Mellomresultatene for hvert ord, så modellen ikke må regne ut igjen. Lager minne. |
| **Ekspert-offloading** | — | Ekspertene ligger på disk og strømmes til RAM mens de brukes. |
| **Ekspert-cache** | — | Hvor mange eksperter som holdes i RAM om gangen. |
| **Codebook / MTP** | Multi-Token Prediction | Modellen lager lyd ved å velge fra et sett lydbiter. |

---

## Feilsøking

**«Prosessen forsvinner med ingen feilmelding»**
Macen har gått tom for minne, og macOS avslutter prosessen. Sjekk
`sysctl vm.swapusage`. Løsning: `codec_backend=cpu` (allerede satt opp) og
kortere referanse (8–12 sekunder).

**«Norsk lyder rart»**
- Sjekk at transkriptet i `reference_text` faktisk er det som ble sagt
- Skriv tall ut som ord: «25,5 cm» blir ofte «5-12 cm»
- Prøv den store modellen, ikke IQ3_XXS

**«Det går utrolig langsomt»**
Forventet med den store modellen. 33 sekunders tale tar ~16 minutter.
Bruk kortere tekst, eller `CACHE_SIZE=32` for færre disklesninger.

**«tensor type 142/143 is invalid» eller «unknown type»**
Du bruker vanlig llama.cpp. Drama 3 krever Prism MLs fork eller audio.cpp.

**«ffmpeg mangler»**
```bash
brew install ffmpeg
```

**«Feil ved lasting: tensor shape mismatch»**
Modellfilen er kuttet feil. Kjør `scripts/prune_gguf.py` på nytt.

---

## Veien videre

Fra dette prosjektet til en ferdig norsk modell. Tre uavhengige spor:

| Spor | Mål | Varer | Koster |
|---|---|---|---|
| **A** | Q4/Q2-blanding per lag — passer bedre på 16 GB | 1 time | $0 |
| **B** | Destillasjon for å redde en pruned modell | 1–2 døgn | $10–30 (leid GPU) |
| **C** | LoRA-finetuning av CosyVoice3 for norsk | 2–5 døgn | $0 (på din Mac) |

**Spor A** er mest aktuelt akkurat nå: Q2_K er raskere, men oppfører seg mer
«amerikansk». Ved å holde Q4_K på lagene som bærer norsk og bruke Q2_K på
resten får vi en mindre modell uten å ødelegge routeren — som var problemet
med pruning.

**Spor C** krever ingen GPU og kan kjøre parallelt. Norsk data finnes i
Språkbanksen under CC0: NST Norwegian Speech Synthesis (5 363 uttrykk),
NB Tale (12 t, 380 talere, 12 dialekter), NST ASR (980 talere),
parlamentskorpuset (59 t). For din egen stemme er 20–30 minutter med opptak
på 24 kHz mono nok til en LoRA.

Full detalj, kommandoer og kostnadsestimater:
[`docs/VEIEN_VIDERE.md`](docs/VEIEN_VIDERE.md).

---

## Kilder og prosjekter

### Prosjekter vi har brukt

| Prosjekt | Hva det er | Lenke |
|---|---|---|
| **Fish Audio Drama 3** | Selve modellen. 35B MoE, 83 språk, Apache 2.0 | [huggingface.co/fishaudio/drama-3](https://huggingface.co/fishaudio/drama-3) |
| **audio.cpp** | Runtime-en vi bruker. Rent C++, 62 modellfamilier, Metal-støtte | [github.com/0xShug0/audio.cpp](https://github.com/0xShug0/audio.cpp) |
| **Drama 3-dokumentasjon** | All konfigurasjon for ekspert-offloading | [docs/models/fish_drama3.md](https://github.com/0xShug0/audio.cpp/blob/main/docs/models/fish_drama3.md) |
| **JarodMica/Drama-3-GGUF** | GGUF-konverteringen vi bruker | [huggingface.co/Jmica/Drama-3-GGUF](https://huggingface.co/Jmica/Drama-3-GGUF) |
| **pentacoxian-dev/drama3-small-GGUF** | Den lille modellen (IQ3_XXS) | [huggingface.co/pentacoxian-dev/drama3-small-GGUF](https://huggingface.co/pentacoxian-dev/drama3-small-GGUF) |
| **PrismML-Eng/llama.cpp** | Prism MLs fork — også nødvendig for Drama 3 | [github.com/PrismML-Eng/llama.cpp](https://github.com/PrismML-Eng/llama.cpp) |
| **fish-speech** | Oppsream for modellen og lydkoderen | [github.com/fishaudio/fish-speech](https://github.com/fishaudio/fish-speech) |
| **CosyVoice** | Alternativet vi sammenligner mot | [github.com/FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice) |
| **Chatterbox** | Alternativet vi sammenligner mot | [github.com/resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox) |
| **drama3-mac** | MLX-port av Drama 3, raskeste Mac-alternativet | [github.com/JordiPosthumus/drama3-mac](https://github.com/JordiPosthumus/drama3-mac) |
| **CosyVoice MCP** | Verktøy for å generere lyd fra CosyVoice | via denne guiden |

### Rapporter

| Rapport | Innhold |
|---|---|
| [`docs/RAPPORT.md`](docs/RAPPORT.md) | Alle målinger: hastighet, presisjon, minne, modellsammenligning |
| [`docs/PRUNING.md`](docs/PRUNING.md) | Hvordan pruningen fungerer, og hva som er vanskelig |
| [`docs/METODE.md`](docs/METODE.md) | Testoppsettet, slik at resultatene kan reproduseres |

### Drama 3-teknisk rapport

[arxiv.org/abs/2610.18010](https://arxiv.org/abs/2610.18010) — «Fish Audio Drama 3 Technical Report»

---

## Lisens

Denne guiden og scriptene er MIT-lisensiert.

Modellene er under **Fish Audio Community License v1.0** — ikke MIT. Gratis for
forskning og ikke-kommersiell bruk; begrenset kommersiell bruk under
500 000 USD i årlig omsetning.

Lydklippene i `audio/` er laget med forfatterens egen stemme som referanse,
for å dokumentere resultatene.
