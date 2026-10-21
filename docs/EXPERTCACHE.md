# Ekspert-cache: hvor mye RAM, hvor mye fart

Drama 3 har 40 lag × 256 eksperter. Routeren velger 8 eksperter per token.
Modellen er 21,78 GiB — den får ikke plass i 16 GB.

audio.cpp løser det med tre nivåer:

```
fish_drama3.disk_experts=true      ekspertbankene på SSD (mmap)
fish_drama3.expert_cache_size=N    N eksperter per lag i GPU-RAM
fish_drama3.cpu_expert_layers=K    K lag holdes i sin helhet i CPU-RAM
```

## Hvorfor cache-størrelsen er så viktig

`num_experts_per_tok` er 8. Med `expert_cache_size=8` er cachen **akkurat
like stor som ett tokens ekspertsett** — så hvert token som bruker en
annen kombinasjon tvinger en disklesning. Det er derfor RTF var 24 og
98 GB ble lest fra disk per kjøring.

Cachen er **LRU** (`last_used` i `disk_expert_weight_store.cpp`): den
beholder det *senest brukte*, ikke det *mest brukte*. Det er ikke det
samme, og det er derfor en stor cache trengs.

## Målt på MacBook Pro M1 Pro 16 GB

Q4_K_S-pakken (4-bit dense), samme tekst, samme seed, bare cache-størrelsen
varierer:

| `expert_cache_size` | treffrate | ekspertlast | bytes lest fra disk | RTF | wall |
|---|---|---|---|---|---|
| 8 | 20,0 % | 63 048 | 111,6 GB | 44,2 | 476 s |
| 16 | 30,0 % | 55 684 | 98,5 GB | **27,4** | 297 s |
| 32 | 40,0 % | 46 403 | 82,1 GB | **26,4** | 287 s |

**Hovedfunnet: 8 → 16 gir 38 % lavere RTF.** 16 → 32 gir lite ekstra fart,
men disklesningen faller 98,5 → 82,1 GB.

Samme måling på drama3-small:

| `expert_cache_size` | treffrate | bytes lest |
|---|---|---|
| 8 | 31,5 % | 17,7 GB |
| 16 | 42,2 % | 14,9 GB |
| 32 | 55,8 % | **11,4 GB** |

Kurven hadde ikke flatet ut ved 32.

## Hva cache-størrelsen betyr i praksis

### Hva cache-størrelsen betyr

| Modell | Fil | `expert_cache_size` | Eksperter i RAM | RAM totalt | På SSD igjen | Treffrate | Lest fra SSD | **RTF** |
|---|---|---|---|---|---|---|---|---|
| Miksen | 18.94 GiB | **32** eksperter/lag | 1.40 GB | 6.0 GB | 12.96 GiB | 46 % | 61 GB | **21.6** |
| Q2_K | 15.88 GiB | **32** eksperter/lag | 1.23 GB | 7.2 GB | 8.62 GiB | 38 % | 43 GB | **22.2** |
| Q3_K_S | 18.93 GiB | **32** eksperter/lag | 1.61 GB | 7.6 GB | 11.28 GiB | 40 % | 63 GB | **22.8** |
| Q3_K_S | 18.93 GiB | **64** eksperter/lag | 3.23 GB | 9.2 GB | 9.67 GiB | 50 % | 49 GB | **21.5** |
| Q4_K_S | 21.78 GiB | **8** eksperter/lag | 0.53 GB | 5.4 GB | 16.35 GiB | 20 % | 112 GB | **44.2** |
| Q4_K_S | 21.78 GiB | **16** eksperter/lag | 1.06 GB | 5.9 GB | 15.82 GiB | 30 % | 98 GB | **27.4** |
| Q4_K_S | 21.78 GiB | **32** eksperter/lag | 2.11 GB | 7.0 GB | 14.77 GiB | 40 % | 82 GB | **26.4** |
| Q4_K_S | 21.78 GiB | **64** eksperter/lag | 4.22 GB | 9.1 GB | 12.65 GiB | 50 % | 62 GB | **21.3** |

### Modellene side om side (cache 32)

| Modell | Fil | RAM (eksperter) | RAM totalt | På SSD | Treffrate | Lest fra SSD | **RTF** |
|---|---|---|---|---|---|---|---|
| Miksen | 18.94 GiB | 1.40 GB | 6.0 GB | 12.96 GiB | 46 % | 61 GB | **21.6** |
| Q2_K | 15.88 GiB | 1.23 GB | 7.2 GB | 8.62 GiB | 38 % | 43 GB | **22.2** |
| Q3_K_S | 18.93 GiB | 1.61 GB | 7.6 GB | 11.28 GiB | 40 % | 63 GB | **22.8** |
| Q4_K_S | 21.78 GiB | 2.11 GB | 7.0 GB | 14.77 GiB | 40 % | 82 GB | **26.4** |

## Om `pin_experts`

Runtime-en har også `fish_drama3.pin_experts=true`, som kopierer hele
ekspertbanken per lag til pinned host RAM. Det er **CUDA-only** — på Metal
kaster den:

```
pinned experts require a backend with pinned host buffers
```

Det ville dessuten krevd 256 × 1,69 MB × 40 lag = **17,3 GB** for
fullmodellen, altså mer enn maskinen har. For drama3-small (9,74 GiB)
ville det gått.

## Hva vi ikke har gjort

Vi har **ikke** testet å låse bestemte eksperter (aldri evict) mot
LRU. Det er en liten endring i `disk_expert_weight_store.cpp` — skille
mellom låste slots og vanlige slots — men først etter at sweepen viser
om rene `expert_cache_size` er nok.

Se `docs/RETTING.md` for en annen målefeil vi fant og rettet.
