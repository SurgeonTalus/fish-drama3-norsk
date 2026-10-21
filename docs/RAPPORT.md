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

Modellene ble testet med **samme tekst**, **samme referansestemme**,
**samme seed** og **samme maskin**.

### Målt med norsk ASR, vanlig norsk setning, cache 32

| Modell | Fil | Norsk (WER) | RTF | Peak RAM |
|---|---|---|---|---|
| **Drama 3 Q2_K** | 15,88 GiB | **6,1 %** | 14,4 | ~7 GB |
| **Drama 3 Q3_K_S** | 18,93 GiB | **9,1 %** | **22,8** | ~7 GB |
| Drama 3 Q4_K_S | 21,78 GiB | 12,1 % | 26,3 | ~7 GB |
| Drama 3 Q3_K_S, cache 64 | 18,93 GiB | 9,1 % | **21,5** | ~11 GB |

**Forskjellene er 1–2 ord av 32 — altså støy.** Med riktig oppsett er
Q2_K, Q3_K_S og Q4_K_S **like gode på intelligibilitet**.

### CosyVoice3 og Chatterbox (eldre målinger, foreldet)

| Modell | Norsk (WER) | Engelsk (WER) | Auto-språk (engelsk) | RTF |
|---|---|---|---|---|
| CosyVoice3 + norsk LoRA | 32 % | 12 % | `sv` ✗ | 10,8 |
| Chatterbox v3 | 59 % | 15 % | `no` ✗ | 5,8 |
| Drama 3 IQ3_XXS (liten) | 59 % | — | — | 11,2 |

> **Merk:** disse ble målt med den gamle metoden (Whisper `small`, for lang
> referansetekst) og må måles på nytt før de brukes. Se
> [`RETTING.md`](RETTING.md).

### Fire hovedfunn

1. **Drama 3 snakker norsk.** Den norske ASR-en skriver ut riktig norsk
   ortografi, og Whisper identifiserer språket automatisk som norsk.

2. **Kvantiseringen ødelegger ikke norsk.** Q2_K (2,6 bit) er like bra som
   Q4_K_S (4,5 bit) på intelligibilitet. Den tidligere påstanden om at
   «Q2_K gjør modellen amerikansk» gjaldt **aksent**, ikke forståelighet —
   og den skyldtes delvis en målefeil.

3. **Ekspert-cachen var den viktigste innstillingen.** `expert_cache_size`
   8 → 64 senker RTF fra 44,2 til 21,3 uten å røre modellen.

4. **Det finnes ikke 64 norske eksperter.** Én norsk setning bruker 193–255
   av 256 eksperter i hvert lag, og topp-64 dekker bare 43–52 % av
   tilgangene. Språkspesialiseringen finnes, men som gradient: norsk og
   engelsk deler omtrent halvparten av de varme ekspertene. Se
   [`ROUTING.md`](ROUTING.md).

---

## Presisjon

### Metode

**Måleverktøy:** `NbAiLab/nb-wav2vec2-1b-bokmaal` (Nasjonalbibliotekets AI-lab).
Norsk ASR med **6,33 % WER** på norsk referansemateriale. Lyden resamples til
16 kHz mono.

**Referanse:** `audio/referansetekst_8s.txt` — de tre setningene som faktisk
står i 8-sekundersklippen.

**Testtekst:** en vanlig norsk setning uten sjarvord eller tall, fordi slike
nettopp er det både modellen og måleverktøyet snubler på.

Skript: `scripts/maal_norsk.py` (én fil), `scripts/maal_sett.py` (hele settet).

### Resultat

Alle modeller genererte **samme setning**, med samme referansestemme, samme
seed og samme maskin. `expert_cache_size=32`.

| Modell | Fil | WER | RTF |
|---|---|---|---|
| Drama 3 Q2_K | 15,88 GiB | **6,1 %** | 14,4 |
| Drama 3 Q3_K_S | 18,93 GiB | 9,1 % | **22,8** |
| Drama 3 Q3_K_S (cache 64) | 18,93 GiB | 9,1 % | 21,5 |
| Drama 3 Q4_K_S | 21,78 GiB | 12,1 % | 26,3 |

**Forskjellene er 1–2 ord av 32 — altså støy, ikke kvalitet.** Transkripsjonene
er nesten identiske:

> **Q2_K** — *i går gikk jeg en tur langs elven sammen med min sønn vi snakket
> om sommerfjerjen og om det nye huset vi skal flytte inn i det skal bli fint
> så synes jeg*
>
> **Q3_K_S** — *i går ikke jeg en tur langs elven sammen med min sønn vi
> snakket om sommerferien og om det nye huset vi skal flytte inn i det skal bli
> fint så syns jeg*
>
> **Q4_K_S** — *i går gikk en tur langs elven sammen med min sønn vi snakket om
> sommerferien om det nye huset vi skal flytte inn det skal bli fint så synes
> jeg*

### Hva vi så

**1. Q2_K er ikke dårligere enn Q4_K_S.** Den tidligere påstanden kom fra to
målefeil — en for lang referansetekst og Whisper `small` — ikke fra modellen.
Med riktig oppsett er forskjellen mellom dem **1–2 ord på én setning**.

**2. Aksent er en egen dimensjon som WER ikke fanger.** Ved høring høres
Q2_K tydelig mer «amerikansk» enn Q3_K_S. Det er reelt, men det er ikke det
samme som intelligibilitet, og WER kan ikke skille dem.

**3. Q3_K_S er det beste kompromisset.** Nesten like god WER som Q4_K_S,
men 2,85 GiB mindre og ~15 % raskere. Og med en større cache kan den holde
96 eksperter per lag i RAM med god margin.

**4. Vi trenger flere setninger for å skille modellene.** Én setning gir
1–2 feil, og forskjellene er under støynivået. Det er grunnen til at vi
lagde et lytteopplegg: aksent må vurderes av et menneske.


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

### Ekspert-cachen: den viktigste innstillingen

Alle RTF-tall over er målt med `expert_cache_size=8` — nøyaktig så stor som
ett tokens ekspertsett (`num_experts_per_tok` er 8). Med bare 8 slots tvinges
hvert eneste token som bruker en annen kombinasjon til en disklesning.

Vi kjørte samme modell, samme tekst og samme seed, og varierte bare
cache-størrelsen:

| `expert_cache_size` | Treffrate | Ekspertlast | Bytes lest | **RTF** |
|---|---|---|---|---|
| 8 | 20,0 % | 63 048 | 111,6 GB | 44,2 |
| 16 | 30,0 % | 55 684 | 98,5 GB | **27,4** |
| 32 | 40,0 % | 46 403 | 82,1 GB | **26,4** |
| 64 | 50,0 % | 34 873 | 61,7 GB | **21,3** |

**RTF 44,2 → 21,3 (−52 %) og disklesningen 111,6 → 61,7 GB (−45 %) — uten å
røre modellen.** Ingen ny kvantisering, ingen ny kode. Bare en innstilling.

### RAM-kostnaden

Én ekspert per lag = 3 projeksjoner × 2048 × 512 elementer.

| Profil | per ekspert per lag | cache 64 | cache 96 | cache 128 |
|---|---|---|---|---|
| Q4_K_S (4-bit dense) | 1,69 MB | 4,22 GB | 6,33 GB | 8,44 GB |
| **Q3_K_S (8-bit dense)** | **1,29 MB** | **3,22 GB** | **4,83 GB** | **6,45 GB** |
| Q2_K (8-bit dense) | 0,98 MB | 2,46 GB | 3,69 GB | 4,92 GB |

Modellen trenger ellers ~7,2 GB. **Q3_K_S kan altså holde 96 eksperter per lag
i RAM med god margin**, der Q4_K_S måtte nøye seg med 64. Og Q3_K_S flytter
24 % mindre data per miss, så samme treffrate koster mindre I/O.

Full detalj i [`EXPERTCACHE.md`](EXPERTCACHE.md).

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
