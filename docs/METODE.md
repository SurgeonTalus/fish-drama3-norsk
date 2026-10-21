# Testopplegg

Slik ble målingene gjort, slik at resultatene kan reproduseres.

---

## Maskin

| | |
|---|---|
| Chip | Apple M1 Pro, 10 kjerner (10 logiske) |
| Minne | 16 GB unified memory |
| OS | macOS 27.0.1 (build 26A434) |
| Metal working set | 12 713 MB ( rapportert av `ggml_metal_init`) |

---

## Runtime

| | |
|---|---|
| Versjon | `audio.cpp 0.9.2-drama3-base-small` |
| Commit | `507495611b22dc4593e0e5609e05e8096384e33f` (2026-10-18) |
| Build | Release, `apple-clang 21.0.0.21000101`, Darwin arm64 |
| Backends | `cpu`, `metal` |
| Endringer | Pause-clamp + routing-statistikk (se `scripts/audio_cpp_endringer.patch`) |

---

## Modeller som ble testet

| Modell | Fil | Størrelse | Kilde |
|---|---|---|---|
| Drama 3 full | `drama-3-backbone-4bit-experts-Q4_K_S.gguf` | 21,78 GiB | [Jmica/Drama-3-GGUF](https://huggingface.co/Jmica/Drama-3-GGUF) |
| Drama 3 liten | `drama3-small-IQ3_XXS.gguf` | 9,74 GiB | [pentacoxian-dev/drama3-small-GGUF](https://huggingface.co/pentacoxian-dev/drama3-small-GGUF) |
| Drama 3 Q2_K | `drama-3-backbone-8bit-experts-Q2_K.gguf` | 15,88 GiB | [Jmica/Drama-3-GGUF](https://huggingface.co/Jmica/Drama-3-GGUF) |
| CosyVoice3 + norsk LoRA | `Fun-CosyVoice3-0.5B` + `cosy-norwegian` | 0,5 B | Lokal installasjon |
| Chatterbox v3 | `ChatterboxMultilingualTTS` (t3_model=v3) | ~1,5 GB | Lokal installasjon |

---

## Fast mellom alle kjøringer

| Variabel | Verdi |
|---|---|
| Referanse | 8,0 s norsk, 44,1 kHz, mono, PCM 16-bit |
| Referansetranskript | Identisk for alle modeller |
| Norsk tekst | «Mal et A4-ark i grønne og gule nyanser. Mal en stor sirkel på 25,5 cm og fyll hele sirkel med farge.» |
| Engelsk tekst | 67 ord, jevnt sammenlignbart |
| Seed | 42 |
| Tråder | 10 |
| Backend | `metal` |
| Modus | `offline` (kun `offline` støtter `--metrics`) |
| `context_length` | 2048 |
| `codec_backend` | `cpu` |
| `codec_encoder_chunk_samples` | 65536 |
| `disk_experts` | `true` for Drama 3 (påkrevd på 16 GB) |
| `expert_cache_size` | 8 |
| `cpu_expert_layers` | 0 |

---

## Målemetoder

### Ordfeilrate (WER)

**Norsk ASR:** `NbAiLab/nb-wav2vec2-1b-bokmaal` (Nasjonalbibliotekets AI-lab).
Modellen er spesialisert på norsk bokmål og har **6,33 % WER** på norsk
referansemateriale (NoDaLiDa 2023). Lyden resamples til 16 kHz mono, og
teksten normaliseres for skilletegn og store/små bokstaver før
Levenshtein-avstand på ordnivå beregnes og deles på referanselengde.

Skript: `scripts/maal_norsk.py` (én fil), `scripts/maal_sett.py` (hele settet).

> **Hvorfor ikke Whisper small?** Vi begynte med Whisper `small` med
> `language="no"` tvunget. Det viste seg å ha en mye høyere støyflyt enn
> modellene: den skrev norske ord i engelsk ortografi og bommet tall.
> Alle Drama 3-modellene fikk omtrent samme WER uansett kvalitet, og den
> *dårligere* referansen ga et *bedre* tall (18,2 % mot 36,4 % på samme
> modell). Et mål uten diskrimineringskraft kan ikke brukes til å skille
> modeller. Whisper `small` beholdes bare til auto-språkdeteksjon.

### Auto-språk

Whisper `small` uten at språket er tvunget. Modellen vurderer selv hvilket
språk lyden er. Dette avdekker aksentdrift: CosyVoice3s engelsk ble
klassifisert som svensk, Chatterbox sitt engelsk som norsk.

### Aksent — menneskelig vurdering

Aksent kan ikke måles med ett tall. WER forteller hvor mye av innholdet som
er forstått, ikke om stemmen *høres* norsk ut. Den siste dommen gir
mennesket: lyttepakken i `scripts/lyttepakke.sh` genererer samme norske
setning fra flere modeller, med spørsmål om språk, forståelighet og
naturlighet.

Se `docs/RETTING.md` for en målefeil vi fant og rettet.

### Grunnfrekvens (F0)

Median grunnfrekvens via autokorrelasjon over de første 3 sekundene.
Referansen ligger på 126 Hz.

### RTF

`metrics.rtf` fra audio.cpp: wall-sekunder ÷ lydsekunder. Genereringstiden
alene, uten modell-lasting.

### Swap-nivå

`sysctl vm.swapusage` før og etter hver kjøring. På 16 GB er dette
det viktigste signalet for OOM.

---

## Rekkefølge for å reprodusere

```bash
# 1. Hent runtime og modell
#    (se README.md)

# 2. Kjør Drama 3 full med norsk referanse
./bin/audiocpp_cli --task clon --family fish_drama3 --backend metal \
  --mode offline --model modeller/drama3-Q4_K_S.gguf \
  --voice-ref audio/referanse_stemme.wav \
  --request-option "reference_text=<transkript>" \
  --text "<norsk tekst>" --max-tokens 400 --seed 42 --threads 10 \
  --session-option fish_drama3.disk_experts=true \
  --session-option fish_drama3.expert_cache_size=8 \
  --session-option fish_drama3.cpu_expert_layers=0 \
  --session-option fish_drama3.context_length=2048 \
  --session-option fish_drama3.codec_backend=cpu \
  --session-option fish_drama3.codec_encoder_chunk_samples=65536 \
  --log --metrics --out output/tale.wav

# 3. Mål kvalitet
python3 scripts/maal_wer.py output/tale.wav

# 4. Sammenlign med de andre modellene
#    (CosyVoice3 og Chatterbox kjøres via sine egne verktøy)
```

---

## Viktige forbehold

- **Målingene er fra én maskin.** RTF varierer med CPU, disk og bakgrunnslast.
- **ASR er et aproksimasjonsverktøy.** En WER på 30 % betyr ikke «30 % av
  ordene er feil» — det betyr at måleverktøyet og modellen ikke er enige.
  Transkripsjonen leses derfor alltid med, ikke bare tallet.
- **Referansen er norsk.** Derfor ser vi aksentdrift hos modellene som er
  språkbundet til referansen.
- **Referanseteksten må matche referanselyden.** Vi brukte en lengre
  referansetekst enn det 8-sekundersklippen faktisk inneholdt. Alle
  Drama 3-målingene før dette ble tatt med den feilen.
- **Én kjøring per konfigurasjon.** For Drama 3 full ga to kjøringer
  18,2 % og 36,4 % WER med identisk oppsett — tallet varierer.
