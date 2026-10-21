# Lag-droputing: en modell som får plass i RAM

## Ideen

Runtime-en i audio.cpp laster lagene 0, 1, 2, … opp til
`num_hidden_layers` og kjører dem i den rekkefølgen. Lagene er navngitt
i modellfilen:

```
model_weights/model.language_model.layers.N.mlp.experts.gate_proj.weight
```

**Derfor kan vi bygge en modell med et vilkårlig lagsett uten å endre
runtime-en:** vi fjerner de lagene vi ikke vil ha, og skriver de
gjenværende om til 0, 1, 2, …

Verktøyet er `scripts/bygg_lagvalg.py` (i `~/drama3-prune`):

```bash
python3 bygg_lagvalg.py --input kilder.gguf --output ut.gguf \
    --behold 0,1,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,39
```

Det patcher også `num_hidden_layers` i den embedded `config.json`, uten å
endre lengden på noe (så filen forblir gyldig).

## Hvorfor akkurat denne modellen

Vi beholdt lag **0, 1, 2** (de tre mest sensitive, ifølge drama3-small),
**36** (den fjerde sensitive) og **38, 39** (de to siste, som ferdigstiller
token-prediksjonen). De 18 lagene i mellom er de som ble kuttet.

Mellomrommet er ikke tilfeldig: de overlevende lagene ligger **spredt i
hele stabelen**, slik at hvert av dem må gjøre jobben for to. Det er
forskjellen på lag-droputing og trunkering — trunkering (beholde 0–19)
fjerner halve stabelen helt, og er et langt hardere inngrep.

## Hvorfor dette er bedre enn å kutte eksperter

**Kutting av eksperter krever router-refit og destillasjon.** drama3-small
trengte en 96 GB GPU og 282 timer tale. Uten det ødelegger det — vårt eget
eksperiment ga WER 100 % og 254 %.

**Kutting av lag krever ikke router-refit.** Hvert lag beholder sin egen
router og sine egne eksperter, så routeren blir ikke rot. Idealistisk sett
ville en lett finetuning (1–5 % av originalens data) tatt igjen, men det
er ikke en forutsetning for at modellen kjører.

## Hva får plass i 12,7 GiB

Modellen består av tre deler: ekspertene, en per-lag-del (attention +
delt ekspert) og en fast del (embedding, hode, codec, normer).

| Modell | lag | eksperter/lag som får plass | 100 | 128 | **200** | 256 |
|---|---|---|---|---|---|---|
| Q3_K_S (vår GGUF) | 40 | **132** | 11,05 GiB | 12,46 GiB | 16,08 GiB | 18,90 GiB |
| Q3_K_S | **22** | **alle 256** | 8,17 GiB | 8,94 GiB | 10,94 GiB | **12,49 GiB** |
| MLX 3-bit | 40 | **173** | 8,91 GiB | 10,35 GiB | 14,04 GiB | 16,91 GiB |
| MLX 3-bit | 22 | alle 256 | 5,17 GiB | 5,96 GiB | 7,99 GiB | 9,57 GiB |

**200 eksperter per lag er ikke mulig med 40 lag** — men det er mulig hvis
du samtidig kutter lag. Og da er det allerede bygget.

Regnestykket: `scripts/eksperter_per_budsjett.py`. Det er kontrollert mot
den målte filen: 22 lag × 256 eksperter gir 12,49 GiB.

## Om cache-størrelsen ved 96 eksperter

`expert_cache_size=96` for Q3_K_S bruker 4,83 GB med eksperter og 10,8 GB
totalt (RTF 19,2). For Q4_K_S blir det 6,33 + 4,87 = **11,2 GB**, og da
presser det: vi fikk 8,6 GB swap og generasjonen stod nesten helt stille.
**96 er akkurat på grensen. 64 er trygt** (9,1–9,2 GB totalt).

## Målt resultat

Se `docs/LYTTETEST.md` for høring, og `docs/RAPPORT.md` for tabellene.

---

## Resultatet: uten trening ødelegger lag-droputing modellen

**Testet:** 24 lag, grupper {0, 1, 3, 5, 7, 9} — 13,21 GiB, maks hopp 4 lag,
alle 10 full-attention-lag beholdt, lag 0/1/2 og 36 beholdt.

| | |
|---|---|
| RTF | **18,4** (mot 23,0 for 40 lag) |
| Treffrate | **69,0 %** (mot 42,0 %) |
| Lest fra SSD | **23,9 GB** (mot 57,3 GB) |
| **WER (norsk ASR)** | **96,9 %** |

Transkripsjonen:

> *trygg år omgående ja de stilt på vedde forskeren kan altså det tvillings*

**Modellen snakker norsk-formet babbel.** Ordene har riktig form, men
ingen betydning. De 16 kuttede lagene bærer tyngden av språkforståelsen.

**Dette er forventet.** Lag-droputing i litteraturen krever en lett
finetuning — typisk 1–5 % av originalens treningsdata. Vi har ingen
finetuning gjort, så resultatet er et resultat, ikke et nederlag.

### Hva det betyr for veien videre

| Tilnærming | Størrelse | Trenger trening? | Kost |
|---|---|---|---|
| Lag-droputing uten trening | 13,2 GiB | — | ødelagt |
| **Lag-droputing + lett LoRA-finetune** | 13,2 GiB | Ja, **men lite** | ~$2–5 på H100 |
| Ekspert-pruning + refit + destillasjon | 4,5 GiB | Ja, mye | ~$45–56 |
| Q3_K_S uendret | 18,9 GiB | Nei | $0 |
| Q3_K_S @ cache 96 | 18,9 GiB | Nei | $0 |

**Lag-droputing + lett finetuning ser ut til å være den billigste veien til en
liten modell.** Vi trenger kanskje 5–20 timer norsk tale, ikke de 282
timene drama3-small brukte, fordi vi ikke rører ekspertene — bare dybden.
Og LoRA på en 13 GiB modell passer lett på en H100.

### En begrensning vi må huske

Runtime-en krever at lagtypen følger *posisjonen*:

```cpp
const auto expected = (layer + 1) % 4 == 0 ? "full_attention" : "linear_attention";
```

Så lag kan bare kuttes i hele grupper på fire. Innenfor det er de beste
fordelingene:

| lag | grupper | maks hopp | beholder 0,1,2 og 36 | størrelse |
|---|---|---|---|---|
| 24 | {0,1,3,5,7,9} | 4 | ja | 13,21 GiB |
| 20 | {0,2,4,6,9} | 8 | ja | 11,78 GiB |
| 20 | {0,2,4,6,8} | 4 | mister 36 | 11,78 GiB |
| 28 | {0,1,2,4,6,8,9} | 4 | ja | 14,5 GiB |
