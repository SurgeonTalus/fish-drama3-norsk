#!/bin/bash
#
#  Valider en Drama 3-variant: generer norsk, mål WER, auto-språk og RTF.
#
#  Bruk:
#      ./scripts/valider.sh <modell.gguf> [tag]
#
set -u
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

MODEL="${1:?bruk: valider.sh <modell.gguf> [tag]}"
TAG="${2:-$(basename "$MODEL" .gguf)}"

REF_TEXT="I dag skal vi lage et ukebladportrett med collage! Men hva er egentlig et ukebladportrett? Et portrett er et bilde av et menneske. Når vi lager et ukebladportrett, bruker vi bilder fra blader til å sette sammen et nytt ansikt."
TXT="Mal et A4-ark i grønne og gule nyanser. Mal en stor sirkel på 25,5 cm og fyll hele sirkel med farge."

mkdir -p output
OUT="output/${TAG}_norsk.wav"
LOG="output/${TAG}.log"

if [ ! -f "$MODEL" ]; then
    echo "ERROR: finner ikke modellen: $MODEL" >&2
    exit 1
fi

echo "=== Validerer $TAG ==="
echo "  modell: $MODEL"
echo "  størrelse: $(du -h "$MODEL" | cut -f1)"
echo

START=$(date +%s)
./bin/audiocpp_cli --task clon --family fish_drama3 --backend metal --mode offline \
    --model-spec-override "${SPEC_OVERRIDE:-spec_override}" \
    --model "$MODEL" \
    --voice-ref "${REF_WAV:-audio/referanse_stemme.wav}" \
    --request-option "reference_text=$REF_TEXT" \
    --text "$TXT" \
    --max-tokens 400 --seed 42 --threads 10 \
    --session-option fish_drama3.disk_experts=true \
    --session-option fish_drama3.expert_cache_size=8 \
    --session-option fish_drama3.cpu_expert_layers=0 \
    --session-option fish_drama3.context_length=2048 \
    --session-option fish_drama3.codec_backend=cpu \
    --session-option fish_drama3.codec_encoder_chunk_samples=65536 \
    --log --metrics --out "$OUT" > "$LOG" 2>&1
RC=$?
END=$(date +%s)

echo "  exit: $RC   wall: $((END - START)) s"
grep -E "metrics\.(rtf|wall_ms|audio_duration_ms|peak_)" "$LOG" | sed 's/^/  /'

if [ -f "$OUT" ]; then
    echo "  lyd: $OUT"
    echo
    echo "=== Kvalitet ==="
    python3 scripts/maal_wer.py "$OUT" "$TXT"
else
    echo "  INGEN LYD — modellen klarte ikke å generere"
    tail -5 "$LOG" | grep -vE "compiling|loaded kernel" | sed 's/^/    /'
fi
