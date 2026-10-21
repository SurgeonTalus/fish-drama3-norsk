# Parallelle ekspertlesninger: prefetch-vinduet vi ikke bruker

## Problemet

Drama 3 er en Mixture-of-Experts-modell. For hvert token velger routeren de
8 beste ekspertene i hvert av 40 lagene. Ekspertene ligger på SSD og hentes
ved bruk.

Vår måling, Q3_K_S ved cache 32:

| | verdi |
|---|---|
| ekspertressninger | 78 995 |
| ekspertlast | 45 545 |
| treffrate | 42,3 % |
| bytes lest | 57,3 GB |
| **disklesningstid** | **175,4 s** |
| opplastingstid | 14,6 s |
| ryggrad-steg | 37,2 s |
| **wall** | **236 s** |
| RTF | 25,5 |

**3,85 ms per ekspert på 1,29 MB = 335 MB/s effektivt.** Apple-disken
klarer 2–3 GB/s sekvensielt. Vi får altså bare rundt 13 % av
båndbredden.

Årsaken: de 8 ekspertene i et lag leses **sekvensielt**. Hver lesning er
en sidefeil, og sidefeilene serialiseres.

## Løsningen: les ekspertene parallelt

I `disk_expert_weight_store.cpp` er lesingen av misses endret til å skje i
flere tråder samtidig:

```cpp
const size_t traader = std::min<size_t>(read_threads, antall);
for (size_t t = 0; t < traader; ++t) {
    pool.emplace_back([&, t]() {
        for (size_t m = t; m < antall; m += traader) {
            std::memcpy(staging + offset + m * bytes,
                mapped_file.data() + projection.offset + misses[m].id * bytes, bytes);
        }
    });
}
```

Trådene skriver til distinkte områder i staging-bufferen, så de kan ikke
kollidere. Antallet tråder er en konstruktør-parameter
(`read_threads`, standard 8).

**Hvor mange som kan parallelliseres:**

| | antall |
|---|---|
| under decode | 8 eksperter per lag (top-k = 8) |
| under prefill | langt flere — vi målte 91 520 rutede rader |
| taktgrense | antall misses i én kaller, og SSD-køedepthen |

## Målt effekt

Q3_K_S, samme tekst, samme seed, alt annet likt:

| kjøring | RTF | treffrate | lest | disklesning | wall |
|---|---|---|---|---|---|
| cache 32, sekvensiell | 25,5 | 42,3 % | 57,3 GB | 175,4 s | 235,9 s |
| **cache 32, 8 parallelle** | **17,3** | 42,3 % | 57,3 GB | **102,9 s** | 159,5 s |
| cache 96, sekvensiell | 19,9 | 63,8 % | 36,0 GB | 109,6 s | 183,7 s |
| cache 96, 8 parallelle | 19,7 | 63,8 % | 36,0 GB | 74,1 s | 182,2 s |

**RTF 25,5 → 17,3 (−32 %) ved cache 32.** Parallell lesing slår cache 96
sekvensiell (19,9) selv om cache 96 leser halvparten så mye data.

**Ved cache 96 flyttet flaskehalsen:** disktiden falt 35 s, men wallen
beholdt seg. Da er det opplastingen eller CPU-konkurransen med
Metal-beregningen som begrenser. Derfor må trådtallet tunes, og
kombinasjonen cache 96 med flere tråder må måles.

**Utdata er bit-identisk.** Parallelliseringen rører ingen matematikk.

### Innstilling

```bash
--session-option fish_drama3.expert_read_threads=16
```

Standard er 8.

## Referanse i bransjen

Samme idé finnes to steder:

- **llama.cpp-diskusjon #27149**, «Expert-Aware SSD Streaming for MoE
  Models on Memory-Constrained Hardware»:

  > *The router completes before attention finishes, creating a prefetch
  > window for expert I/O. This is the "model predicts its own working set"
  > property — the information about which parameters are needed arrives
  > before they're needed.*

  De måler 11,4× mindre I/O per lag, og 2,09× fra dobbelbufring alene.

- **llama.cpp-omni**, «LES» (Lookahead Expert Scheduling): 3,38 → 11,34 tok/s
  på iPhone med 12 GB, deretter → 17,16 med blandet presisjon.

Diskusjon #23324 har en uavhengig Metal-PoC på 13 tok/s med LRU
ekspertpaging på M1 Pro 16 GB.
