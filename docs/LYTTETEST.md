# Lyttetest: kvalitet slik et menneske hører den

Ordfeilrate kan ikke skille mellom modeller på dette nivået, og den
ser ikke aksent i det hele tatt. Derfor er lytting den viktigste
kvalitetsmålingen i dette prosjektet.

**Testoppsett:** samme norske setning, samme 8-sekunders referansestemme,
samme seed (42), samme maskin, `expert_cache_size=32`.

---

## Resultatet

| Modell | Fil | WER | **Høring** | Kommentar |
|---|---|---|---|---|
| **Drama 3 Q4_K_S** | 21,78 GiB | 9,4 % | **9,5 / 10** | «enormously convincing», utmerket norsk, langt foran CosyVoice |
| **Drama 3 Q3_K_S** | 18,93 GiB | 3,1 % | **9 / 10** | bedre enn CosyVoice, men flat n i «inn» |
| Drama 3 Q2_K | 15,88 GiB | 6,2 % | **7 / 10** | kan ikke si «r» — høres ut som taleforstyrrelse |
| CosyVoice3 + norsk LoRA | ~1 GB | — | 8 / 10 | «allerede troverdig» |
| **Drama 3 Q4/Q2-miks** | 18,94 GiB | **25,0 %** | **ikke hørt ennå** | se nedenfor |

## Verifikasjon: modellen mot referansen

Den sterkeste kvalitetsprøven vi har gjort. Referansen
(`audio/referanse_stemme.wav`, 8 s) og modellen sier **nøyaktig samme
tekst**, så det er ingen tvil om hva som skal bli sagt:

| Fil | Innhold |
|---|---|
| `output/verifisering/00_referanse_original.wav` | referansen, uendret |
| `output/verifisering/01_modell_sier_samme.wav` | modellens versjon av samme tekst |
| `output/verifisering/TRANSKRIPT.txt` | transkriptet |

> **«Det er en 99 % klone. Jeg er helt sikker på at det er meg — fortelleren.
> Jeg ville ikke lagt merke til det hvis jeg ikke hadde visst. Det er vanvittig
> når det genererer det samme som inputen.»**

Dette er verdt å merke seg, fordi det er *ikke* selvfølgelig:

- **Drama 3 kloner ikke en bølgeform, men et tokensett.** Referansen kodes
  inn i modellens eget semantiske tokenrom, og stemmen blir en fortsettelse
  av referansen inne i modellen. Derfor er «samme tekst som inputen» det
  letteste tilfellet.
- **Rutingen er flat** (193–255 av 256 eksperter per lag). Det finnes ingen
  liten «stemme-ekspertgruppe» som kunne bli ødelagt — identiteten ligger
  spredt i hele modellen.
- Likevel overlever den **4-bits kvantisering av en 35B MoE** der bare
  ~17 % av ekspertene er resident om gangen.

**Forbehold:** «samme tekst som referansen» er det lette tilfellet for
enhver klone-modell. Den reelle prøven er ny tekst, og den er avgjort
overfor: **9,5 / 10** for Q4_K_S.

**Og resultatet validerer referansetekst-retningen** (se `RETTING.md`): de
dårlige ordfeilratene vi så tidligere var måleverktøyets feil, ikke
modellens.

---

## Hva kvalitetsforskjellene faktisk er

Det er ikke «norsk mot ikke-norsk». Alle tre Drama 3-modellene snakker
norsk. Forskjellen er **artikulatorisk presisjon**, og den forsvinner
stegvis med bit-bredden:

| Bit (effektiv) | Modell | Hva som går tapt |
|---|---|---|
| 4,5 | Q4_K_S | intet merkbart |
| 3,1 | Q3_K_S | **flat n** i «inn» — høres som n i «ng»-kombinasjoner |
| 2,6 | Q2_K | **/r/ er borte** — høres ut som taleforstyrrelse |

**Norsk /r/ er en retrofleks alveolart approximant** — en svært
diskret, lav-amplitudes artikulatorisk bevegelse. Den krever presis
vektorrepresentasjon, og det er den første som går tapt. Det er en
riktig norsk lyd, ikke en aksent — så dette er ikke «amerikansk»-problemet,
men et kvantiseringsproblem.

**Rekkefølgen er nyttig:** tapet går r → n. R er den vanskeligste
artikulatoren, så det er rimelig at den rammes først.

## Miksen (lag 0–19 @ Q4_K, lag 20–39 @ Q2_K)

**WER 25,0 %** mot 3–9 % for de andre. Transkripsjonen viser det samme
som hørselen gjorde hos Q3_K_S:

> *år gikk en tur langs elven sammen med **sønd** vi snakket om sommerferien
> om det nye huset vi skal flytte inn **ny** det skal bli fint **syns** jeg*

«sønn» → «sønd», «inn i» → «inn ny», «sa synes» → «syns».

**Konklusjon: miksen slik den er bygd, er dårligere enn alle de tre
referansemodellene.** Hypotesen «halve lagene på Q2_K er greit, fordi
routeren er urørt» er **avkreftet**.

### Lagkartet var feil

Vi delte 50/50 uten å beskytte lagene drama3-small peker ut. Verifisert
innhold i miksen:

```
lag  0-19: Q4_K     lag 20-39: Q2_K
```

Lag 0, 1 og 2 havnet i Q4_K-gruppen ved tilfeldighet, men **lag 36 ligger
i Q2_K-gruppen** — ett av de fire lagene drama3-small beskriver som
langt mer sensitive enn resten:

> *Pruning layer 0, 1, 2 or 36 costs far more than any other layer, so
> those four keep all 256.*

**Vi beskyttet dem ikke.** Vi bygger nå en mikst der lag 0, 1, 2 og 36
holdes på Q4_K.

### To forvekslinger vi må skille fra hverandre

1. **Dobbelt kvantisering.** Miksen ble bygd som
   Q4_K → F16 → (Q4_K | Q2_K). Q2_K-lagene arver altså Q4_K-feilen
   *i tillegg* til sin egen. Q2_K-pakken vi sammenligner med ble bygd
   FP8 → F16 → Q2_K, altså med én kvantisering.
2. **Feil lagkart.** Vi delte 50/50 uten å vite hvilke lag som bærer
   uttalen. drama3-small dokumenterer at lag 0, 1, 2 og 36 er de
   følsomme.

**Testen som skiller dem:** bygg miksen motsatt vei — lag 0–19 @ Q2_K,
lag 20–39 @ Q4_K.

- Blir den **like dårlig** → det er presisjonen Q2_K som skader, ikke
  lagevalget.
- Blir den **bedre** → de sene lagene bærer uttalen, og vårt opprinnelige
  lagkart var feil.

Vi bygger den nå.

## Hva vi gjør med resultatene

**Valget mellom Q4_K_S og Q3_K_S blir et reelt valg, ikke en avveining:**

| | Q4_K_S | Q3_K_S |
|---|---|---|
| Kvalitet | 9,5 / 10 | 9 / 10 |
| Fil | 21,78 GiB | 18,93 GiB |
| RTF (cache 32) | 25,8 | 23,0 |
| RTF (cache 64) | 21,3 | 21,5 |
| Eksperter i RAM | 64 | **96** |
| Modellen norsk | ja | ja |

Q3_K_S er 2,85 GiB mindre og holder 32 flere eksperter per lag i RAM.
Forskjellen i høring er liten, men den er reell: flat n i «inn» er
merkbar for en norsktalende.

**Q2_K faller ut** på kvalitet, uansett hastighet.

## Filene

```
~/fish-drama3-norsk/output/lyttepakke/     samme setning, 4 modeller
~/fish-drama3-norsk/output/lyttepakke2/    3 setninger x 4 modeller
~/fish-drama3-norsk/output/cache_sweep/    samme modell, 4 cache-størrelser
```

Filnavn: `<modell>_s<N>.wav`, der N er setningsnummeret.
