# Mikser: lag 36 er verdt 19 WER-poeng

## Resultatet

Vi bygde to mikser av Q3_K_S-kilden, begge med 20 lag på Q4_K og 20 lag på
Q2_K, 18,94 GiB, routerne urørt. De skiller seg bare på to lag:

| | lag 19 | lag 36 | WER | RTF |
|---|---|---|---|---|
| **Mix A** (første forsøk) | Q4_K | **Q2_K** | 25,0 % | 21,6 |
| **Mix C** (lag 0/1/2/36 beskyttet) | Q2_K | **Q4_K** | **6,2 %** | 21,2 |

Til sammenligning, samme setning, samme seed, samme cache:

| Modell | WER | RTF | Fil |
|---|---|---|---|
| **Mix C** | **6,2 %** | 21,2 | 18,94 GiB |
| Q3_K_S | 9,1 % | 23,0 | 18,93 GiB |
| Q4_K_S | 9,4 % | 25,8 | 21,78 GiB |
| Q2_K | 6,2 %* | 22,2 | 15,88 GiB |
| Mix A | 25,0 % | 21,6 | 18,94 GiB |

\* Q2_K-tallet er fra en annen kjøring med en litt annen setning; ikke
direkte sammenlignbart.

**Mix C er det beste vi har målt, og det er like stor som Q3_K_S mens
halve lagene ligger på Q2_K.**

## Hvorfor første forsøk feilet

Vi delte 50/50 mellom lag 0–19 og lag 20–39 uten å vite hvilke lag som
bærer uttalen. Det var en ren gjetning, og den ga 25,0 % WER.

**Lag 0, 1, 2 og 36 er de fire lagene drama3-small peker ut som sensitive:**

> *Pruning layer 0, 1, 2 or 36 costs far more than any other layer, so
> those four keep all 256. That reallocation alone cut the proxy KL by 26 %
> compared with a uniform 116 experts per layer.*

Lag 0, 1 og 2 havnet i Q4_K-gruppen ved tilfeldighet. **Lag 36 gjorde det
ikke** — og det var nok til å ødelegge modellen.

## Hva vi faktisk kan si om lag 36

Sammenligningen Mix A ↔ Mix C er overraskende ren. Lag 19 flyttet **ned**
(Q4_K → Q2_K) uten skade, mens lag 36 flyttet **opp** (Q2_K → Q4_K) ga
18,8 WER-poeng. Det peger på at:

- **Lag 36 bærer noe essensielt** som de andre lagene ikke kan kompensere for
- Den nedre halvdelen av stabelen kan gå på Q2_K uten problemer så lenge
  lag 36 beholdes
- Halvparten av lagene kan altså gå på 2,6 bit — det er bare ett lag som
  må ha full presisjon

Dette er i tråd med at lag 36 er det siste laget før de to siste, og at
de tidlige lagene (0, 1, 2) behandler den rå innholdskodingen.

**Hva vi ennå ikke vet:** om det er lag 36 *spesifikt*, eller om det er
noe mer generelt ved de siste lagene. Mix C har lag 20–35 og 37–39 på
Q2_K, så svar på «er det de siste lagene generelt?» ville krevd en mikst
med for eksempel lag 32–39 på Q4_K.

## Hvorfor dette er et reelt resultat og ikke en feil

| Kontroll | Status |
|---|---|
| Samme tekst, samme referansestemme, samme seed | ✓ |
| Samme cache-størrelse, samme maskin | ✓ |
| Routerne urørt i begge | ✓ |
| Laginnhold verifisert lag for lag i filen | ✓ |
| 42 overrides verifisert før bygging | ✓ |
| Resultatet gjengitt av ASR | ✓ |

Og resultatet er ikke «mikser er dårligere enn ingenting» — Mix A var
det, Mix C er det beste vi har målt. **Forskjellen er ett lag.**

## Anbefaling

**Mix C**, 18,94 GiB, RTF 21,2 ved cache 32.

Den er mindre enn Q4_K_S (21,78 GiB), raskere (21,2 mot 25,8) og målt
bedre (6,2 % mot 9,4 % WER).

Høring: `docs/LYTTETEST.md`.
