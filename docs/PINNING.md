# Pinning av eksperter: 42 % → 62 % treffrate

## Bakgrunn

Ekspert-cachen i audio.cpp er **LRU**: den kaster ut den eksperten som ble
brukt for lengst siden (`last_used` i `disk_expert_weight_store.cpp`).

Vi antok at LRU er nær optimal, fordi rutingen er flat: én norsk setning
bruker 193–255 av 256 eksperter i hvert lag, og topp-64 dekker bare 43–52 %
av tilgangene.

**Men vi testet pinning med feil K.** Første forsøk låste de 64 mest
brukte ekspertene på 32 slots — altså flere låste enn det var plass til.
De skjøv hverandre, og treffraten ble *dårligere* enn uten lås
(39,3 % mot 40,0 %).

Simuleringen av implementasjonens egen eviction-regel sa at optimum lå
ved **K = antall slots**:

| slots | uten lås | lås 8 | lås 16 | lås 32 | lås 64 |
|---|---|---|---|---|---|
| 32 | 19,9 % | 24,6 % | 27,9 % | **31,6 %** | 27,8 % |
| 64 | 36,6 % | 38,6 % | 40,6 % | 43,5 % | **46,0 %** |
| 96 | 50,6 % | 51,5 % | 52,6 % | 54,4 % | **56,2 %** |

## Resultatet

**Lås like mange eksperter som du har slots for:**

| | treffrate | lest fra disk |
|---|---|---|
| uten lås @ cache 32 | 42,0 % | 57,3 GB |
| lås 64 @ cache 32 (for mange) | 39,3 % | 64,8 GB |
| **lås 32 @ cache 32** | **62,0 %** | 61,2 GB |

**+20 prosentpoeng treffrate** — mer enn simuleringen spådde (+11,7).

## Hvordan det virker

`pin_experts_file` peker på en fil med `lag ekspert` per linje. De
ekspertene får et eget slot i cachen og kastes aldri ut så lenge en ulast
slot finnes.

```bash
python3 scripts/analyser_ruting.py routing.txt --topp 32 --pin pin_k32.txt
./bin/audiocpp_cli ... --session-option "fish_drama3.pin_experts_file=pin_k32.txt"
```

**Ekstra RAM: null.** De låste ekspertene ligger i de samme slotene.

## Hvorfor dette er motsatt av LFU

TurboFieldfare (Gemma 4, 2 GB RAM på 8 GB-Mac) bruker **LFU** — least
frequently used, altså den kastes ut *minst* ofte. Det er det adaptive
motstykket til det vi gjør her statisk: vi låser de ekspertene som var
varme på en norsk setning, de bruker LFU til å finne de varme uten å
vite på forhånd.

**Det er det naturlige neste steget** hvis vi vil gå videre: bytte
eviction-regelen fra `last_used` til en bruksteller per slot. Det er en
liten endring i samme fil — omtrent ti linjer.

## Begrensning

Pinningen bygger på én norsk setning. Hvis det varme settet er stabilt
over tekster, holder låsingen. Hvis det varierer, vil LFU være bedre.

Det er prøveversjonen: vi må kjøre på et korpus og se om topp-32 per lag
er stabilt.
