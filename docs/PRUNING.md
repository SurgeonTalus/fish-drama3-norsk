# Pruning av Drama 3 direkte i GGUF-filen

Denne guiden viser hvordan man kutter bort eksperter som en språk ikke bruker,
**uten å laste ned original-checkpointet på nytt**.

---

## Hvorfor det er verdt å gjøre

Drama 3 har 256 eksperter per lag, hvorav 8 velges for hvert ord. Modellen
trenger derfor ikke alle 256 for å fungere — den trenger bare de som
språket faktisk bruker.

Ved å kutte fra 256 til 100 eksperter:

- **filen blir 43 % mindre** (21,78 → 12,52 GiB)
- **den leser 44 % mindre data fra disk per steg** → 6,3x raskere
- modellen får plass i RAM med mye større margin

---

## Nøkkelobservasjonen

I GGUF-formatet ligger ekspertene allerede som kvantisert Q4_K-tensorer med formen:

```
gate_proj / up_proj:  (2048, 512, 256)     ← siste dims = ekspertantall
down_proj:            (512, 2048, 256)
router:               (2048, 256)
```

GGML lagrer `ne0` fastest-varying, og Q4_K har blokkstørrelse 256. Derfor er
hver eksperts data et sett av uavhengige blokker langs `ne0`, og å kuttet bort
eksperter er **ren byte-kopiering**:

```
gammel rad (i1, ekspert_old) = i1 * 256 + ekspert_old
ny rad    (i1, k_new)        = i1 * n_keep + k_new
```

Ingen dekvantisering. Ingen ny kvantisering. Ingen 38,7 GB nedlasting. Ingen
68 GiB intermediate-fil.

Den vanlige veien for å prune en MoE-modell er nemlig å laste ned
original-checkpointet, konvertere til FP16, og kvantisere på nytt. Det er
døgn av arbeid og ~110 GB disk. Denne metoden er cirka **20 minutter**.

---

## Fremgangsmåte

### 1. Samle routing-statistikk

Modellen må kjøres over norsk tekst, og vi logger hvilke eksperter som velges.
Det gjør vi med en ekstra session-option i audio.cpp:

```bash
--session-option fish_drama3.collect_routing_stats=true \
--session-option fish_drama3.routing_stats_path=routing.txt
```

Filen får linjer på formen `lag ekspert antall masse`.

Korpuset bruker vi ligger i `scripts/norsk_korpus.txt` — 35 norske setninger.

### 2. Konverter til .pt

```bash
python3 scripts/tekst_til_pt.py routing.txt routing_no.pt
```

Utskriften viser dekningsgraden for hvert mulig keep-nivå:

```
Skrev routing_no.pt: 40 lag, 256 eksperter
  keep=192: min=100.0% mean=100.0%
  keep=128: min=100.0% mean=100.0%
  keep=100: min=100.0% mean=100.0%
  keep= 64: min=100.0% mean=100.0%
```

Dekning på 100 % betyr at de 64 mest brukte ekspertene per lag dekker all
routing-massen. Det norske språket bruker altså et begrenset sett eksperter.

### 3. Kutt modellen

```bash
python3 scripts/prune_gguf.py \
  --input modeller/drama3-Q4_K_S.gguf \
  --output modeller/drama3-pruned-100.gguf \
  --stats routing_no.pt --keep 100 --criterion mass
```

Resultat:

```
ekspertspor: 4000 av 10240 (39.1 %)
dekning: min=100.0%  mean=100.0%
Ferdig: drama3-pruned-100.gguf
  størrelse: 12.52 GiB (fra 21.78 GiB)
```

---

## Det viktige: beskytte lag 0/1/2/36

**Vår første test ødelegde kvaliteten.** Vi kuttet alle 40 lag likt til 100
eksperter, og resultatet var ubrukelig lyd (Whisper: «H catalog ‑»).

Årsaken er dokumentert i drama3-smalls modellkort:

> Pruning layer 0, 1, 2 or 36 costs far more than any other layer, so those four
> keep all 256. That reallocation alone cut the proxy KL by 26% compared with a
> uniform 116 experts per layer.

De fire første og siste lagene bærer tungt ansvar. Kutter du dem, ødelegger
du modellen. **Dette var en feil i oppsettet vårt, ikke et resultat.**

Riktig oppsett:

```bash
python3 scripts/prune_gguf.py \
  --input modeller/drama3-Q4_K_S.gguf \
  --output modeller/drama3-pruned-100-prot.gguf \
  --stats routing_no.pt \
  --keep 100 --protected-layers 0,1,2,36 --protected-count 256
```

Dette gir 4 lag med 256 eksperter og 36 lag med 100, altså:

```
4×256 + 36×100 = 4624 ekspertspor av 10240 (45 %)
```

### Begrensning i runtime-en

`num_experts_per_layer` i config.json støtter at lag har ulikt eksperttall, og
audio.cpp leser det. Men vår pruner skriver foreløpig bare ett antall for alle
lag. Støtten for per-lag-antall må inn i `prune_gguf.py` før varianten med
beskyttede lag kan kjøres.

---

## GGUF-detaljer som må være riktige

Dette er de fire tingene som var vanskeligst å finne ut, og som alle må være
korrekte for at filen skal lastes:

**1. `tensor_shapes` og `tensor_ranks` må være konsistente.**
Runtime-en leser `ranks[i]` verdier fra `tensor_shapes` per tensor, og krever at
summen av ranks er lik lengden på shapes. Originalfilen er inkonsistent her
(99 tensors har rank 3 når de har rank 2) — vi skriver de eksakte formene.

**2. Shapes er omvendt dims.**
`info.shape` leses som `reversed(dims)`, altså ne0 først. Tensors med
`dims[0] == 1` får én ekstra `1` i originalen, og det må bevares.

**3. `config.json` må skrives med samme byte-lengde.**
Den ligger i `embedded_files.data` som en binær blob. Enten den blir
byte-lengre eller -kortere, flyttes alle offsetene etterpå, og da havner
data-seksjonen på feil grense. Løsningen: skriv den nye configen og fyll ut
resten med mellomrom, slik at lengden bevares.

**4. Paddingen er relativ til `data_start`.**
`GGML_PAD(bytes, 32)` gjelder byte-tellingen *innenfor* data-seksjonen, ikke
absolutt filposisjon. Bruker du absolutt posisjon, blir alle offsetene feil.

I tillegg: `ggml_nbytes` for F16 med rank > 1 er **ikke** produktet av dims.
Formelen er `elemsize + sum((ne[i]-1) * nb[i])` der `nb[i] = nb[i-1] * ne[i]`.
En rank-2 F16-tensor med dims `[1, 96]` er 18 242 byte, ikke 192.

---

## Resultat og begrensning

| Måling | Full Q4_K_S | Pruned 100 (alle lag) | Pruned 100 (lag 0/1/2/36 beskyttet) |
|---|---|---|---|
| Filstørrelse | 21,78 GiB | **12,52 GiB** | **12,52 GiB** |
| RTF (disk-offload) | 24,0 | **3,81** | **3,48** |
| Peak RAM | 7,7 GB | 7,7 GB | 7,7 GB |
| Norsk (WER) | 36,4 % | **100 %** | **254 %** |
| Whisper auto-språk | `no` | `ko` | `jw` |

**Begge pruned-varianter ødelegger modellen.** Variant 2 med beskyttede lag
faller inn i degenerert repetisjon:

> Løp til dem og klipp til dem og klipp til dem. Hva? Nå er det pittis nære.
> Nå er det pittis nære. Nå er det pittis nære. Nå er det...

### Hvorfor — og hva som ville vært nødvendig

Å kutte eksperter uten å justere routeren **endrer routing-sannsynlighetene**.
Modellen ble trent med akkurat de 256 ekspertene, og de overlevende får nå
oppgaver de ikke ble trent for.

drama3-small løste dette med to trinn:

1. **Router-refit** — lag for lag justeres router-vektene slik at de
   gjenstående ekspertene får riktig sannsynlighetsmasse
2. **Destillasjon** — 100 steg med KL mot den opprinnelige FP8-modellen,
   på ~282 timer tale + 5 501 linjer

Dette ble gjort på en **96 GB GPU**. Uten router-refit og destillasjon er
resultatet en ødelagt modell, uansett hvor godt ekspertene er valgt.

**Konklusjon:** Pruning uten trening er ikke en vei til en brukbar modell.
Det er et krav om trening, og treningen krever en GPU.

### Det som likevel er verdt å ta med seg

- **Metoden virker teknisk.** 21,78 → 12,52 GiB, 6,3x raskere, filen laster
  og genererer. Det er pruneren, GGUF-formatet og instrumenteringen som er
  gjenbrukbare — ikke resultatet.
- **Routing-statistikken viser at norsk dekkes av ~64 eksperter per lag.**
  Dekningsgraden var 100 % ved keep=64. Det er et reelt funn om modellen.
- **Riktig prunesetup** er lag 0/1/2/36 med 256, resten på 100 — 4 624
  ekspertspor av 10 240 (45 %). Per-lag-antall støttes av både config.json
  (`num_experts_per_layer`) og audio.cpp, og vår pruner skriver det riktig.
  Det som mangler er router-refit og destillasjon.

### Neste steg, hvis du vil gå videre

1. Kutt med `--keep 100 --protected-layers 0,1,2,36 --protected-count 256`
2. Kjør router-refit på det prunede checkpointet
3. Destiller 100 steg mot fishaudio/drama-3 (FP8) — krever ~96 GB GPU
4. Konverter tilbake til GGUF og valider

Trinn 2–3 er det samme arbeidet drama3-small gjorde, og krever GPU. Alt
annet i dette repoet — pruneren, GGUF-håndteringen, routing-instrumenteringen,
måleoppsettet — er klart for det.

---

## Verktøy

| Fil | Hva det er |
|---|---|
| `scripts/prune_gguf.py` | Pruneren. Slicer eksperter direkte i GGUF. |
| `scripts/tekst_til_pt.py` | Konverterer routing-statistikk til .pt-format. |
| `scripts/norsk_korpus.txt` | 35 norske setninger for routing-måling. |
| `scripts/audio_cpp_endringer.patch` | Endringene i audio.cpp: pause-clamp og routing-statistikk. |
