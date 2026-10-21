# Ekspertruting: hvor er de norske ekspertene?

Dette er svaret på spørsmålet vi startet med: *finnes det et lite sett
eksperter som bærer norsk språk?*

Dataene kommer fra en instrumentering vi la inn i audio.cpp sin
disk-expert-cache. Hver gang routeren ber om en ekspert, teller vi den —
uansett om den allerede lå i cachen. Telleren sitter i
`disk_expert_weight_store.cpp`, der ekspert-id-ene allerede finnes som
vanlige C++-variabler. Ingen graph-tensor-readback (det var det som
krasjet i et tidligere forsøk), og prefill og decode fanges begge.

Reproduksjon:

```bash
./bin/audiocpp_cli --task clon --family fish_drama3 --backend metal --mode offline \
  --model-spec-override ./spec_override --model models/<modell>.gguf \
  --voice-ref audio/referanse_stemme.wav \
  --request-option "reference_text=$(cat audio/referansetekst_8s.txt)" \
  --text "<norsk tekst>" --max-tokens 400 --seed 42 --threads 8 \
  --session-option fish_drama3.disk_experts=true \
  --session-option fish_drama3.expert_cache_size=32 \
  --session-option fish_drama3.routing_stats_path=/tmp/routing.txt \
  --out /tmp/ut.wav

python3 scripts/analyser_ruting.py /tmp/routing.txt --topp 64
python3 scripts/sammenlign_sprak.py /tmp/routing_no.txt /tmp/routing_en.txt
```

---

## Svar 1: det finnes ikke 64 norske eksperter

Én norsk setning bruker **193–255 av de 256 ekspertene i hvert lag**:

| Lag | Unike eksperter brukt | Topp-8 dekning | Topp-64 dekning |
|---|---|---|---|
| 0 | 255 | 8,1 % | 43,0 % |
| 12 | 227 | 12,7 % | 46,9 % |
| 25 | 202 | 13,8 % | 51,1 % |
| 39 | 193 | 18,6 % | 51,0 % |

Topp-64 per lag dekker altså bare **43–52 %** av tilgangene.

**Rutingen er bred og flat, ikke konsentrert.** Det forklarer den lineære
treffraten i ekspert-cachen: 20 % @ 8 slots, 30 % @ 16, 40 % @ 32,
50 % @ 64. Halvparten av ekspertene brukes omtrent like mye.

Konsekvens: **den vanlige ideen om «de 64 viktige ekspertene per lag» er
feil for dette problemet.** Derfor:

- **Per-ekspert blandet presisjon** ville gitt liten gevinst: bare halvparten
  av tilgangene ville fått full presisjon.
- **Pinning av topp-64** gir omtrent samme treffrate som en vanlig cache på
  64 slots — fordi de varme ekspertene allerede holdes av LRU.
- **Pruning målt på absolutt antall** (drama3-small brukte 100 per lag)
  fungerer likevel, fordi de refit routeren og destillerer etterpå. Det
  er *relativ* routing-masse som betyr noe, ikke antall.

## Svar 2: språkspesialiseringen finnes, men som gradient

Vi samlet den samme historikken for en engelsk setning, med samme
norske referansestemme, og sammenlignet topp-64 per lag:

| | Norsk | Engelsk |
|---|---|---|
| Unike eksperter brukt per lag | 193–255 | 207–230 |
| Topp-64 felles | **27–33 av 64** | |
| Tilfeldig overlapp (to tilfeldige 64-sett av 256) | 16 | |

**Overlappen er omtrent dobbelt så stor som tilfeldig.** Og bare
**25–34 %** av hvert språks tilganger lander på eksperter som er varme i
begge språkene.

Bildet er:

- **Delt kjerne** — omtrent halvparten av de varme ekspertene er felles.
  Antakelig fonetikk, timing og generell språkstruktur.
- **Språkspesifikt periferi** — resten. Merk at fordelingen er flat:
  det er ikke 20 eksperter som er «norske» og resten engelske, det er
  en forskyvning i hele fordelingen.

## Svar 3: hva det betyr for hva vi gjør

| Plan | Status | Begrunnelse |
|---|---|---|
| Per-lag Q4/Q2-miks | **kjørt** | 19 GiB, routeren urørt |
| Per-ekspert Q4/Q2-miks | **lav prioritet** | topp-64 dekker bare ~50 %, så gevinsten er liten — og krever C++-endring |
| Prune til 64/100 eksperter | **krever refit + destillasjon** | drama3-small viser at det må til; uten ble resultatet rot (WER 100 %) |
| Pinning av varme eksperter | **implementert og testet** | gir omtrent samme treffrate som LRU; nyttig for å gjøre valget deterministisk |
| Per-ekspert routing-observasjon | **implementert** | `fish_drama3.routing_stats_path` |

---

## Tillegg: lag-fordeling, konsentrasjon og pinning

### Lag-fordelingen er uniform — det finnes ingen varmt lag

| | tilganger | andel |
|---|---|---|
| Sterkeste lag (0) | 335 | 2,79 % |
| Svakeste lag (38) | 262 | 2,18 % |
| Forhold | 1,28× | |

Alle 40 lag brukes omtrent like mye. **Det finnes ingen gruppe lag som
dominerer**, så det gir ingen mening å «låse de 32 mest brukte lagene»
i den forstanden — alle lag trengs like mye.

### Det som varierer er konsentrasjonen, og den varierer systematisk med dybde

| | lag 0 | lag 12 | lag 25 | lag 39 |
|---|---|---|---|---|
| Unike eksperter brukt | **255** av 256 | 227 | 202 | 193 |
| topp-8 dekning | **8,1 %** | 12,7 % | 13,8 % | 18,6 % |
| topp-32 dekning | 24,5 % | 31,6 % | 34,4 % | 38,8 % |
| topp-64 dekning | 43,0 % | 46,9 % | 51,1 % | 51,0 % |
| topp-128 dekning | 62,1 % | 67,8 % | 73,8 % | 75,3 % |

**Tidlige lag er flate: de bruker nesten alle 256 ekspertene, og de
varmeste åtte står bare for 8 % av tilgangene. Sene lag er konsentrerte.**

Det forklarer drama3-small sitt funn. Lag 0, 1 og 2 er de flatteste
(255, 251 og 255 unike eksperter) — altså lagene som *mister mest* når
man fjerner eksperter. Lag 36 har 203 unike og topp-8 på 15,5 %.

**Konsekvens for kvantisering:** lag med flat routing tåler ikke bare
mindre presisjon — de tåler det dårligere, fordi ingen enkelt ekspert
kan kompensere for en annen.

### Pinning: simulert med implementasjonens egen eviction-regel

Vi simulerte LRU-cachen på den ekte tilgangssekvensen, med nøyaktig samme
regel som `disk_expert_weight_store.cpp`: en låst ekspert kastes ikke ut
så lenge en ulast slot finnes, og når de låste ikke får plass, skjøver de
hverandre i LRU-rekkefølge.

| slots | uten lås | lås 8 | lås 16 | lås 32 | lås 64 |
|---|---|---|---|---|---|
| 32 | 19,9 % | 24,6 % | 27,9 % | **31,6 %** | 27,8 % |
| 64 | 36,6 % | 38,6 % | 40,6 % | 43,5 % | **46,0 %** |
| 96 | 50,6 % | 51,5 % | 52,6 % | 54,4 % | **56,2 %** |
| 128 | 63,1 % | 63,4 % | 63,9 % | 64,8 % | **65,9 %** |

Mønsteret er entydig: **optimalt antall låste ≈ antall slots.** Lås like
mange som du har plass til.

**Men simuleringen er for optimistisk, og det viser den ekte målingen:**

| | simulert | målt |
|---|---|---|
| LRU, 32 slots | 19,9 % | **40,0 %** |
| pin 64, 32 slots | 27,8 % | **39,3 %** |

Den ekte treffraten er dobbelt så høy. Årsaken er at den ekte
tilgangssekvensen har **sterk tidskorrelasjon** — naboppler deler
eksperter — og LRU utnytter det.

**Konklusjon: pinning gir lite i praksis.** De låste ekspertene tar
plass fra LRU-delen, som gjør mer nytte, fordi LRU allerede fanger det
varme settet. Det er bare å heve `expert_cache_size` så langt RAM
tillater.

## Instrumenteringen

To nye session-options i audio.cpp:

| Option | Virkning |
|---|---|
| `fish_drama3.routing_stats_path=<fil>` | skriver `lag ekspert antall` per linje |
| `fish_drama3.pin_experts_file=<fil>` | låser eksperter mot LRU-eviction; filen har `lag ekspert` per linje |

Pinning endrer bare eviction-loopen i `disk_expert_weight_store.cpp`:
en ekspert som er låst, kastes ikke ut. Ekstra RAM: null — de låste
ekspertene ligger i de samme slotene.

Se [`EXPERTCACHE.md`](EXPERTCACHE.md) for cache-målingene og
[`RETTING.md`](RETTING.md) for målefeilen vi fant og rettet.
