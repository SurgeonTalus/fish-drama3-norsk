#!/bin/bash
#
#  Generer norsk tale fra en Drama 3-variant med KORREKT referansetekst.
#
#  Viktig: referanselyden (8 s) inneholder bare de tre første setningene
#  av referanseteksten. Å gi modellen en lengre tekst enn det faktisk
#  står i lyden er en målefeil: modellen får en transkripsjon som ikke
#  passer, og det kan ødelegge kloningen og skyve aksenten.
#
#  Bruk:
#      ./scripts/kjor_test.sh <modell.gguf> <tag> [utmappe]
#
set -u
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# Runtime (audio.cpp) ligger i en egen katalog. Sett RUNTIME=... for aa
# peke pa en annen installasjon.
RUNTIME="${RUNTIME:-$HOME/fish_drama3_35b_exert_offloading}"
BIN="$RUNTIME/bin/audiocpp_cli"
SPEC="${SPEC_OVERRIDE:-$RUNTIME/spec_override}"

MODELL="${1:?bruk: kjor_test.sh <modell.gguf> <tag> [utmappe]}"
TAG="${2:?bruk: kjor_test.sh <modell.gguf> <tag> [utmappe]}"
UT="${3:-$ROOT/output/$TAG}"
mkdir -p "$UT"

REF_LYD="${REF_LYD:-$ROOT/audio/referanse_stemme.wav}"
REF_TXT="${REF_TXT:-$ROOT/audio/referansetekst_8s.txt}"
KORPUS="${KORPUS:-$ROOT/audio/testtekster.txt}"

echo "=== $TAG ==="
echo "  modell : $(basename "$MODELL") ($(du -h "$MODELL" | cut -f1))"
echo "  ref-lyd: $(basename "$REF_LYD")"
echo "  ref-txt: $REF_TXT"
echo ""

n=0
while IFS= read -r TEKST; do
    [ -z "$TEKST" ] && continue
    n=$((n + 1))
    WAV="$UT/${TAG}_s${n}.wav"
    START=$(date +%s)
    "$BIN" --task clon --family fish_drama3 --backend metal --mode offline \
        --model-spec-override "$SPEC" \
        --model "$MODELL" \
        --voice-ref "$REF_LYD" \
        --request-option "reference_text=$(cat "$REF_TXT")" \
        --text "$TEKST" \
        --max-tokens 700 --seed 42 --threads 8 \
        --session-option fish_drama3.disk_experts=true \
        --session-option fish_drama3.expert_cache_size=8 \
        --session-option fish_drama3.cpu_expert_layers=0 \
        --session-option fish_drama3.context_length=2048 \
        --session-option fish_drama3.codec_backend=cpu \
        --session-option fish_drama3.codec_encoder_chunk_samples=65536 \
        --log --metrics --out "$WAV" > "$UT/${TAG}_s${n}.log" 2>&1
    RC=$?
    END=$(date +%s)

    # Referanseteksten ved siden av, saa maal_sett.py vet hva den skal sammenligne mot
    printf '%s' "$TEKST" > "$UT/${TAG}_s${n}.txt"

    if [ -f "$WAV" ]; then
        DUR=$(~/drama3-prune/.venv/bin/python -c "
import soundfile as sf
d,sr=sf.read('$WAV'); print(f'{len(d)/sr:.1f}')" 2>/dev/null || echo "?")
        RTF=$(grep -oE "metrics\.rtf[^0-9]*[0-9.]+" "$UT/${TAG}_s${n}.log" 2>/dev/null | head -1 | grep -oE "[0-9.]+$")
        echo "  s${n}: ${DUR}s lyd, ${RTF:-?} RTF, $((END - START))s wall"
    else
        echo "  s${n}: FEILET (exit $RC)"
        tail -3 "$UT/${TAG}_s${n}.log" | grep -vE "compiling|loaded kernel" | sed 's/^/     /'
    fi
done < "$KORPUS"

echo ""
echo "Ferdig i $UT"
