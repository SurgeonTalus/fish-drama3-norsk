# SETUP — sett opp Drama 3 på en Mac

Dette er skriptet som setter opp alt. Det er ment å kjøres på en ny Mac,
eller på en annen maskin enn den vi målte på.

```bash
python3 scripts/oppsett.py --info      # hva anbefales på denne maskinen
python3 scripts/oppsett.py --modeller  # modellene, og hvilken som passer
python3 scripts/oppsett.py --test      # mål og finn beste innstilling
python3 scripts/oppsett.py --installer # skriv konfigurasjonen og kommandoene
python3 scripts/oppsett.py --status    # hva er satt opp nå
python3 scripts/oppsett.py --resultater # alle målingene
```

Krever bare Python 3. Ingen tredjepartsbiblioteker.

---

## Hvor ligger innstillingene?

**Ett sted: `scripts/innstillinger.json`.** Alle målede tall, modellene og
anbefalingene per RAM-klasse ligger der. Skriptet leser filen og regner ut
resten.

**Det betyr at oppdateringen senere er en filendring.** Når vi har målt mer
på andre maskiner, legges resultatene inn der, og skriptet tilpasser seg
automatisk. Ingen ny kode.

### Hva står i filen

| felt | betydning |
|---|---|
| `konstanter` | målt tall: MB per ekspert per lag, fast del, overhead |
| `modeller` | hver modell med størrelse, kvalitet og minst RAM |
| `anbefalinger` | anbefalt innstilling per RAM-klasse (8/12/16/24/32/64 GB) |
| `resultater` | alle målingene, med merknad |
| `installasjon` | repo-URL-er og session-options |

---

## Hvordan velger skriptet innstilling?

1. Finner RAM, kjerner, macOS-versjon og ledig disk
2. Plukker RAM-klasse: ≤8, ≤12, ≤16, ≤24, ≤32, ellers 64+
3. Henter anbefalingen for klassen fra `innstillinger.json`
4. Regner samtidig ut et teoretisk tak for cache-størrelsen:

   ```
   maks_cache = (RAM - 4 GB for OS og programmer - overhead) / peak_per_cache
   ```

5. **Markerer anbefalingen som «ekstrapolert»** hvis den ikke er målt på
   nøyaktig din RAM-størrelse

`--test` kjører faktiske målinger og lar målingen overstyre anbefalingen.

---

## Hva `--test` gjør

Kjører modellen med fire kombinasjoner av cache-størrelse og antall
parallelle lesninger, skriver ut en tabell, og lagrer den beste kombinasjonen i
`config/kjore.json`.

```
  cache  tråder      RTF     treff    disk s    wall s
  ──────────────────────────────────────────────────
    32       16     16.8     42.3%     98.3     154.9
```

Hver kjøring tar 3–5 minutter. Med `--hurtig` kjøres bare de to beste
kombinasjonene.

**Resultatet er bit-identisk uansett innstilling** — bare hastigheten
endres. Det er derfor trygt å kjøre testen.

---

## Hva de tre tallene betyr

| session-option | betydning |
|---|---|
| `fish_drama3.expert_cache_size` | hvor mange eksperter per lag som ligger i GPU-RAM samtidig |
| `fish_drama3.expert_read_threads` | hvor mange tråder som leser eksperter fra disken parallelt |
| `fish_drama3.cpu_expert_layers` | hvor mange lag som holdes i CPU-RAM i stedet for på disk |

**Cache-størrelsen bestemmer treffraten** — hvor ofte en ekspert allerede
er i RAM når den trengs. Større cache = færre disklesninger = raskere, men
mer RAM.

**Trådtallet bestemmer båndbredden mot disken.** Med én tråd fikk vi
327 MB/s. Med 16 tråder når vi ~1,9 GB/s. Det er den største enkeltstående
gevinsten i hele prosjektet: **RTF 25,5 → 16,8 (−34 %)**.

---

## Installasjon

### 1. Runtime

audio.cpp med Drama 3-støtte, bygget med Metal. Vi brukte
`0x9.2-drama3-base-small` plus to egne endringer:

- `routing_stats_path` og `pin_experts_file` (session-options)
- `expert_read_threads` (parallelle ekspertlesninger)

Se `docs/PARALLELLESNING.md` for detaljene rundt endringene.

### 2. Modellen

```bash
huggingface-cli download https://huggingface.co/Jmica/Drama-3-GGUF \
  --include 'drama-3-backbone-8bit-experts-Q3_K_S.gguf' --local-dir models
```

**Husk: 18,93 GiB.** Sjekk ledig disk først.

### 3. Referansestemme og -tekst

`audio/referanse_stemme.wav` (8 s, 44,1 kHz mono) og
`audio/referansetekst_8s.txt`.

**Teksten må matche klippen eksakt.** Vi brukte en for lang referansetekst
en stund, og det ødela både kvaliteten og aksenten. Se
[`docs/RETTING.md`](docs/RETTING.md).

### 4. Kjør

Se `--installer` for den fullstendige kommandoen.

---

## Bytter du Mac?

```bash
git pull
python3 scripts/oppsett.py --info      # se anbefalingen for ny maskin
python3 scripts/oppsett.py --test      # mål og tilpass
```

Ingen annet å gjøre. Modellen ligger i `models/`, runtime-en bygges på nytt
med de samme endringene.

---

## Hvis noe går galt

**«audiocpp_cli: unknown option expert_read_threads»** → runtime-en er
bygget uten endringen. Bygg på nytt.

**Prosessen blir drept (exit 137)** → for mye minne. Senk
`expert_cache_size`. Se `docs/EXPERTCACHE.md`.

**Modellen snakker engelsk** → sjekk at `reference_text` matcher klippen
nøyaktig.

**Modellen er treg** → kjør `--test`. Cache-størrelse og trådtall er de to
som betyr noe.
