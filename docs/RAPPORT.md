# Rapport: Fish Audio Drama 3 på norsk

Alle målinger gjort på **Apple M1 Pro MacBook Pro, 16 GB unified memory,
macOS 27.0.1**, med audio.cpp `0.9.2-drama3-base-small` (Metal-backend).

> ## ⚠️ Tallene i denne rapporten er delvis foreldete
>
> Vi fant to målefeil etter at målingene var gjort:
>
> 1. **Referanseteksten var lengre enn referanselyden.** Vi ga modellen fire
>    (eller seks) setninger mens 8-sekundersklippen bare inneholdt tre.
>    Drama 3 bruker referanselyden som aksentkilde, så inkonsistent betinging
>    ga nøyaktig symptomene vi tilskrev kvantiseringen.
> 2. **Måleverktøyet var for svakt.** Whisper `small` med tvunget norsk har
>    så høy støyflyt at den samme modellen fikk 18,2 % og 36,4 % WER
>    avhengig av referanseteksten. Vi bruker nå NB AI Labs norske wav2vec2.
>
> Se [`RETTING.md`](RETTING.md) for detaljene, og
> [`EXPERTCACHE.md`](EXPERTCACHE.md) for cache-målingene.
>
> **Påstanden om at Q2_K er dårligere på norsk er trukket tilbake** inntil
> den er målt på nytt. Vi gjengir de gamle tallene her for etterprøving, men
> de skal ikke leses som kvalitetsdommer.

---

## Sammendrag

Fire modeller ble testet med **samme tekst**, **samme referansestemme**,
**samme seed** og **samme maskin**.

| Modell | Norsk (WER) | Engelsk (WER) | Auto-språk (engelsk) | RTF | Peak RAM |
|---|---|---|---|---|---|
| **Drama 3 Q4_K_S (full)** | **18–36 %** | **6 %** | `en` ✓ | 24,0 | 7,7 GB |
| Drama 3 Q2_K | 46 % | — | — | 12,7 | 7,7 GB |
| Drama 3 IQ3_XXS (liten) | 59 % | — | — | 11,2 | 10,3 GB |
| CosyVoice3 + norsk LoRA | 32 % | 12 % | `sv` ✗ | 10,8 | ~7 GB |
| Chatterbox v3 | 59 % | 15 % | `no` ✗ | 5,8 | ~1,5 GB |

**Tre hovedfunn:**

1. **Drama 3 snakker norsk.** Whisper identifiserer språket automatisk som
   norsk, og den norske ASR-en skriver ut riktig norsk ortografi.

2. **Den lille modellen snakker ikke norsk.** Den er destillert på japansk og
   engelsk. Norsk blir rot.

3. **CosyVoice3 og Chatterbox faller ut av engelsk.** Med norsk referanse blir
   CosyVoice3 sitt engelsk til svensk, og Chatterbox sitt til norsk. Drama 3
   holder språket.

**Et fjerde funn, som kom etterpå:**

4. **Ekspert-cachen var den viktigste innstillingen.** Vi kjørte med
   `expert_cache_size=8` — nøyaktig så stor som ett tokens ekspertsett.
   Å heve den til 16 senket RTF fra 44,2 til 27,4 uten å røre modellen.
   **Alle RTF-tall i tabellen over er derfor pessimistiske.**

---

## Presisjon

### Metode

Whisper `small`, mot referenceteksten. Teksten normaliseres for skilletegn og
store/små bokstaver. Levenshtein-avstand på ordnivå delt på referanselengde.

**Denne metoden er foreldet.** Den viste seg å ha så høy støyflyt at den
samme modellen fikk 18,2 % og 36,4 % WER avhengig av referanseteksten.
Den erstattes av `NbAiLab/nb-wav2vec2-1b-bokmaal` (norsk ASR, 6,33 % WER på
norsk referansemateriale). Whisper `small` beholdes bare til auto-språkdeteksjon.
Skript: `scripts/maal_norsk.py` (én fil) og `scripts/maal_sett.py` (hele settet).
Se [`RETTING.md`](RETTING.md).

«Auto-språk» er hva Whisper selv finner ut i lyden, uten at språket er
tvunget. Det er avslørende for aksentdrift.

### Norsk

**Drama 3 Q4_K_S — 18,2 % (kjøring A) og 36,4 % (kjøring B)**

> Mal et A4-ark i grønne og gule nyanser. Mal en stor sirkel på **25,5 cm** og
> fyll hele sirkel med farge.

> Mal et A4-ark i grønne av juleneaser. Mal en stor cirkel på 5-12 cm og fyll
> hele cirkel med farge.

Begge er korrekt norsk. Forskjellen er tallet «25,5 cm» — den ene kjøringen
fikk det riktig, den andre fikk «5-12 cm». Gjennomsnittet (~27 %) er det
riktige tallet å planlegge med.

**Drama 3 Q2_K — 45,5 %**

> Ma et A4-ark i grønne og gulene i angse. Ma en stor cirkel på 55 cm og fyl
> hele cirkelen med ferdige.

Auto-språk er fortsatt `no`, så dette er norsk — **ikke** engelsk.

> **Påstanden «dårligere enn Q4_K_S» er trukket tilbake.** Vi tilskrev
> forskjellen kvantiseringen, men målingen ble tatt med en referansetekst som
> ikke matchet referanselyden — og Drama 3 bruker nettopp referanselyden som
> aksentkilde. Aksentdriften i transkripsjonen er reell (*Mal* → **Ma**,
> *gule* → **gole**, *farge* → **ferge**, *25,5 cm* → uforståelig), men hvor
> mye som er kvantisering og hvor mye som er ødelagt betinging, er uvisst
> inntil det er målt på nytt.

Merk at Q2_K ikke kan kjøres uten disk-offloading på 16 GB.

**CosyVoice3 + norsk LoRA — 31,8 %**

> Mal et avfor ark i grønne og gule nyanser. Mal en stor cirkel på tønt i 4-4 cm
> og fyll hele cirklen med farge.

**Chatterbox v3 — 59,1 %**

> Mal et av fire ark i grønne og gul enn janser. Mal en stor kyrkel på 55-3 og
> fyl hele kyrkelen med farget.

**Drama 3 IQ3_XXS (liten) — 59,1 %**

> Mal et A4 ARK i grunn og god nyanser. Mal en stor cirken på 2 utplaner
> skjermvektet 5 cm og fyller med hele serien.

Dette er ikke tilfeldig rot. Mønstret er at modellen approksimerer
ukjente fonemer med de nærmeste lydene den kjenner. Prosodyen og rytmen
holder, så feilen er lett å overse hvis man ikke hører etter ordene.

### Engelsk

**Drama 3 Q4_K_S — 6,0 %**

> I have achieved a higher level of proficiency, demonstrated by details such as
> creating varied imprints using different plants, painting the jewelry pieces,
> crafting jewelry in various shapes and investing time in making multiple
> attempts.

**CosyVoice3 + LoRA — 11,9 %, auto-språk `sv`**

> I have achieved a higher level of proficiency, demonstrated by the tiles such
> as creating varied imprints using different plants, painting the jewellery
> pieces, crafting jewellery in various shapes...

**Chatterbox v3 — 14,9 %, auto-språk `no`**

> I have archived a high level of proficiency, demonstrated by the tilesuchas,
> creating varied imprints using different plants, painting the jewellery
> pieces...

### Hva aksentdriften betyr

Begge alternativene faller ut av engelsk når referansen er norsk. CosyVoice3
går mot **svensk**, Chatterbox mot **norsk** — i motsatt retning, noe som
tyder på at de ikke bare «mangler» engelsk, men aktivt trekkes mot
referansens språk.

Dette bekrefter inntrykket om at CosyVoice har mer aksent og drifter mer.

**Presisering:** CosyVoice3 i denne testen hadde en **norsk LoRA**. Det er den
som trekker engelsken mot norsk — og forbi, siden modellen er språkbundet til
referansen. Med en engelsk referanse ville resultatet sett annerledes ut.
Drama 3 ble trent på 83 språk og holder derfor språket uansett.

Dette stemmer med det generelle inntrykket:
- Fish Audio S2 Pro omtales i r/LocalLLaMA som «almost perfect, I get very few
  artifacts if any and voice cloning is near 1:1 with the source».
- CosyVoice omtales ofte med forbehold. CosyVoice 2 reduserte uttaksfeilraten
  med 30–50 % mot v1, men videre forbedring krever kvantisering av
  projeksjonene, som gir alvorlig kvalitetstap.
- I r/LocalLLaMA beskrives CosyVoice 3 med «audio is not very clean, occasional
  clicks, noise».
- Chatterbox regnes som enklere og lettere å kjøre, med mindre
  ekspresjonskontroll.

---

## Hastighet

RTF = real-time factor = wall-sekunder ÷ lydsekunder. **Lavere er bedre.**
RTF 1,0 betyr «i sanntid».

| Modell | RTF | Disk lest for 33 s | Minne |
|---|---|---|---|
| Chatterbox v3 | **5,8** | 0 | ~1,5 GB |
| CosyVoice3 + LoRA | **10,8** | 0 | ~7 GB |
| Drama 3 IQ3_XXS | 11,2 | 0 | 10,3 GB |
| Drama 3 Q2_K | 12,7 | 0 | 7,7 GB |
| Drama 3 Q4_K_S | 24,0 | 351 GB | 7,7 GB |
| Drama 3 Q4_K_S, pruned til 100 eksperter | **3,81** | 192 GB | 7,7 GB |

### Drama 3 uten offloading dør — også i den minste varianten

Vi kjørte Drama 3 Q2_K (15,88 GiB) **uten** `disk_experts`, altså med hele
modellen i RAM:

```
error: Insufficient Memory (00000008:kIOGPUCommandBufferCallbackErrorOutOfMemory)
audiocpp_cli failed: Drama 3 tower prefill computation failed
```

Selv 15,88 GiB er for mye. **Ekspert-offloading er ikke en optimalisering på
16 GB — det er en forutsetning.** Samme gjelder den prunede modellen ved
100 eksperter (12,52 GiB): kjørt resident ble den avsluttet uten
feilmelding.

### Hvorfor Drama 3 er tregest

Drama 3 er 35 milliarder parametere. Selv om bare 3 milliarder er aktive per
ord, må de hentes fra disk. Målt: 351 GB disklesning for en 33 sekunders tale.

CosyVoice3 er 0,5 milliarder parametere og får plass i RAM — ingen disklesing
i det hele tatt. Chatterbox er mindre ennå.

### Målt på en M3 Ultra

[drama3-mac](https://github.com/JordiPosthumus/drama3-mac) er en egen MLX-port
av Drama 3 som kjører modellen **fullt resident** på en M3 Ultra med 512 GB
RAM.

| | M3 Ultra + MLX | M1 Pro 16 GB + audio.cpp |
|---|---|---|
| Modell i RAM | Fullt resident, 27,3 GB | Disk-offload, 7,7 GB |
| Disk lest pr. 33 s | 0 | 351 GB |
| Steady-state RTF | **0,68** | 24,0–28,8 |
| Decode | 31,4 rammer/s | ~0,93 rammer/s |

**Forskjellen er ~40x**, og den skyldes innstillingene og maskinen, ikke
modellen:

1. **På M3 Ultra er modellen resident.** Ingen disklesing. På 16 GB er
   offloading **tvunget** — det er eneste måten å kjøre en 22 GB-modell på.
2. **M3 Ultra har rundt 800 GB/s minnebåndbredde mot rundt 200 GB/s for M1 Pro.**
   Drama 3 er båndbreddebundet ved decode.
3. **MLX bruker `mx.compile`** med eksplisitt trådede caches per lag, og fjerner
   CPU-dispatch-overhead som ggml betaler.
4. **Ulik kvantisering av ryggraden.** drama3-mac beholder projeksjonene i
   **bf16** — slik som den offisielle FP8-utgivelsen — og kvantiserer bare
   ekspertene. Q4_KS kvantiserer også ryggraden. drama3-mac har altså både
   høyere kvalitet og høyere hastighet.

**Konklusjon:** På en M3 Ultra med nok RAM er drama3-mac klart raskere. På
16 GB finnes ikke det alternativet. Med 512 GB RAM kan *samme* audio.cpp-oppsett
bruke `disk_experts=false` og få fullt resident hastighet.

---

## Minnebruk

Metal rapporterer working set på 12 713 MB på denne maskinen.

| Komponent | Størrelse | Hvor |
|---|---|---|
| `drama3_backbone.weights` | 9 123 MB | Metal |
| `drama3.tower` | 2 173 MB | Metal |
| Fish DAC codec | 747 MB | CPU |
| `disk_experts`-cache | 540 MB | RAM |
| **Peak fysisk footprint** | **7 742 MB** | |

### OOM uten codec på CPU

Da codecen lå i Metal, gikk prosessen over grensen og ble avsluttet
**uten feilmelding**. macOS avslutter prosesser i minnepress uten advarsel.
Dette er det vanligste problemet folk møter, og det er verdt å kjenne
igjen:

```bash
sysctl vm.swapusage
```

---

## Pruning: 100 eksperter

Vi kuttet Drama 3 fra 256 til 100 eksperter per lag, direkte i GGUF-filen.

### Resultat

| | Full Q4_K_S | Pruned 100 (alle lag) | Pruned 100 (lag 0/1/2/36 beskyttet) |
|---|---|---|---|
| Filstørrelse | 21,78 GiB | **12,52 GiB** | **12,52 GiB** |
| RTF (med disk-offload) | 24,0 | **3,81** | **3,48** |
| Peak RAM | 7,7 GB | 7,7 GB | 7,7 GB |
| Norsk (WER) | 36,4 % | **100 %** | **254 %** |
| Whisper auto-språk | `no` (norsk) | `ko` (koreansk) | `jw` (javanesisk) |

### Hastigheten forbedret 6,3x

Pruned-modellen leser 44 % mindre data fra disk per steg. Det er den
største enkeltgevinsten ved pruning.

### Men kvaliteten ble ødelagt — i begge varianter

**Variant 1 (alle lag kuttet til 100):** Whisper transkriberer «H catalog ‑»,
og auto-detekterer språket som **koreansk**.

**Variant 2 (lag 0/1/2/36 beskyttet med 256, resten 100):** enda verre —
modellen faller inn i **degenerert repetisjon**:

> Løp til dem og klipp til dem og klipp til dem. Hva? Nå er det pittis nære.
> Nå er det pittis nære. Nå er det pittis nære. Nå er det...

WER 254 % fordi Whisper bare skriver om samme setning.

### Hvorfor det ødelegger — og hva som ville vært nødvendig

Å kutte eksperter uten å justere routeren **endrer routing-sannsynlighetene**.
Modellen ble trent med akkurat de 256 ekspertene, og de overlevende får nå
oppgaver de ikke ble trent for.

drama3-small løste dette med to trinn:

1. **Router-refit** — lag for lag justeres router-vektene slik at de
   gjenstående ekspertene får riktig sannsynlighetsmasse
2. **Destillasjon** — 100 steg med KL mot den opprinnelige FP8-modellen,
   på ~282 timer tale + 5 501 linjer

Dette ble gjort på en **96 GB GPU**. Vi har ingen av delene på en 16 GB Mac
uten å leie GPU — og selv da må man bruke det *pruned* checkpointet som
utgangspunkt for destillasjonen, altså en ny kjøring.

**Konklusjon:** Pruning uten destillasjon ødelegger modellen. Det er ikke en
feil i implementasjonen vår — det er et krav om trening. Vi rapporterer
resultatet fordi det er et viktig negativt funn: man kan ikke bare koble ut
eksperter og tro at modellen fortsatt fungerer.

### Det som likevel er verdt å ta med seg

- **Metoden virker teknisk.** 21,78 → 12,52 GiB, 6,3x raskere, filen laster
  og genererer. Det er pruneren, GGUF-formatet og instrumenteringen som er
  gjenbrukbare — ikke resultatet.
- **Routing-statistikken viser at norsk dekkes av ~64 eksperter per lag.**
  Dekningsgraden var 100 % ved keep=64. Det er et reelt funn om modellen,
  uavhengig av om vi får til å destillere.
- **Riktig prunesetup** er lag 0/1/2/36 med 256, resten på 100 — 4 624
  ekspertspor av 10 240 (45 %). Dette er neste steg, sammen med router-refit
  og destillasjon på en leid GPU.

> Pruning layer 0, 1, 2 or 36 costs far more than any other layer, so those
> four keep all 256. That reallocation alone cut the proxy KL by 26% compared
> with a uniform 116 experts per layer.

Vi testet begge varianter, og begge ble ødelagt. Se avsnittet over.

Detaljer: [`PRUNING.md`](PRUNING.md).

---

## Anbefaling

| Behov | Anbefaling |
|---|---|
| **Naturlig norsk** | **Drama 3 Q4_K_S.** 18–36 % WER, holder språket, 83 språk. |
| Raskest norsk | CosyVoice3 + LoRA (RTF 10,8) eller Chatterbox (RTF 5,8) |
| Best engelsk | Drama 3 Q4_K_S (6 % WER, `en`) |
| Lavest minnebruk | CosyVoice3 (0,5B) eller Chatterbox (~1,5 GB) |
| Egen stemme | Drama 3 med 10–30 s referanse + korrekt transkript |
| Maks hastighet på Mac | drama3-mac på en M3 Ultra (RTF 0,68) |

---

## Testopplegg

| Variabel | Verdi |
|---|---|
| Runtime | audio.cpp `0.9.2-drama3-base-small`, Metal |
| Maskin | Apple M1 Pro, 10 kjerner, 16 GB, macOS 27.0.1 |
| Referanse | 8,0 s norsk, 44,1 kHz mono, PCM 16-bit |
| Referansetranskript | Identisk for alle modeller |
| Norsk tekst | «Mal et A4-ark i grønne og gule nyanser. Mal en stor sirkel på 25,5 cm og fyll hele sirkel med farge.» |
| Engelsk tekst | 67 ord, jevnt sammenlignbart |
| Seed | 42 |
| Tråder | 10 |
| Backend | metal |
| Modus | offline |
| `context_length` | 2048 |
| `codec_backend` | cpu |
| `codec_encoder_chunk_samples` | 65536 |

---

## Kilder

| | |
|---|---|
| Fish Audio Drama 3 | [huggingface.co/fishaudio/drama-3](https://huggingface.co/fishaudio/drama-3) |
| Drama 3 GGUF | [huggingface.co/Jmica/Drama-3-GGUF](https://huggingface.co/Jmica/Drama-3-GGUF) |
| drama3-small | [huggingface.co/pentacoxian-dev/drama3-small-GGUF](https://huggingface.co/pentacoxian-dev/drama3-small-GGUF) |
| audio.cpp | [github.com/0xShug0/audio.cpp](https://github.com/0xShug0/audio.cpp) |
| drama3-mac (MLX, M3 Ultra) | [github.com/JordiPosthumus/drama3-mac](https://github.com/JordiPosthumus/drama3-mac) |
| CosyVoice | [github.com/FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice) |
| Chatterbox | [github.com/resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox) |
| Drama 3 rapport | [arxiv.org/abs/2610.18010](https://arxiv.org/abs/2610.18010) |
