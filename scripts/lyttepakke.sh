#!/bin/bash
#
#  Lag en lyttepakke: samme norske setning fra flere modeller.
#
#  Aksent kan ikke males med et tall. Du er nororsk, saa du er
#  dommeren: hoist serien av filer i rekkefolge og svar pa:
#     1) Hvilket sprak hoeres det?
#     2) Forstaar du hva det sier?
#     3) Hvor naturlig er det?
#
#  Bruk:
#      ./scripts/lyttepakke.sh <mappe> <modell1.gguf> [modell2.gguf ...]
#
set -u
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

UT="$1"; shift
mkdir -p "$UT"

# Vanlig norsk bokmaal, ingen vanskelige ord, ingen tall.
# (Tall og sjarvord var nettopp der Whisper small bommet, uansett modell.)
TXT="I går gikk jeg en tur langs elven sammen med min sønn. Vi snakket om sommerferien og om det nye huset vi skal flytte inn i. Det skal bli fint, sa synes jeg."
REF="I dag skal vi lage et ukebladportrett med collage! Men hva er egentlig et ukebladportrett? Et portrett er et bilde av et menneske. Når vi lager et ukebladportrett, bruker vi bilder fra blader til å sette sammen et nytt ansikt."

i=0
for M in "$@"; do
    i=$((i + 1))
    NAVN=$(basename "$M" .gguf)
    UTG="$UT/$(printf '%02d' $i)_${NAVN}.wav"
    echo "=== $i: $NAVN ==="
    echo "    størrelse: $(du -h "$M" | cut -f1)"

    START=$(date +%s)
    ./bin/audiocpp_cli --task clon --family fish_drama3 --backend metal --mode offline \
        --model-spec-override "${SPEC_OVERRIDE:-spec_override}" \
        --model "$M" \
        --voice-ref "${REF_WAV:-audio/referanse_stemme.wav}" \
        --request-option "reference_text=$REF" \
        --text "$TXT" \
        --max-tokens 700 --seed 42 --threads 8 \
        --session-option fish_drama3.disk_experts=true \
        --session-option fish_drama3.expert_cache_size=8 \
        --session-option fish_drama3.cpu_expert_layers=0 \
        --session-option fish_drama3.context_length=2048 \
        --session-option fish_drama3.codec_backend=cpu \
        --session-option fish_drama3.codec_encoder_chunk_samples=65536 \
        --log --metrics --out "$UTG" > "$UT/$(printf '%02d' $i)_${NAVN}.log" 2>&1
    RC=$?
    END=$(date +%s)

    if [ -f "$UTG" ]; then
        DUR=$(~/drama3-prune/.venv/bin/python -c "
import soundfile as sf
d,sr=sf.read('$UTG'); print(f'{len(d)/sr:.1f}')" 2>/dev/null || echo "?")
        echo "    OK  ${DUR}s lyd  ($((END - START)) s wall)"
        grep -oE "metrics\.rtf[^ ]* [0-9.]+" "$UT/$(printf '%02d' $i)_${NAVN}.log" 2>/dev/null | head -2 | sed 's/^/    /'
    else
        echo "    FEILET (exit $RC)"
        tail -3 "$UT/$(printf '%02d' $i)_${NAVN}.log" | grep -vE "compiling|loaded kernel" | sed 's/^/      /'
    fi
done

cat > "$UT/SVAR.txt" << 'EOF'
Svar pa dette for hver fil (i rekkefolge):

  1) Hvilket sprak hoeres det?          norsk / norsk-med-engelsk-aksent / engelsk / annet
  2) Forstaar du alt som blir sagt?    ja / nesten / nei
  3) Er noe av det snakkest?            hva?
  4) Foeler du at det er en norsk stemme?  ja / litt / nei

Referanseteksten (skal vaere det du hoerer):
  "I går gikk jeg en tur langs elven sammen med min sønn. Vi snakket om
   sommerferien og om det nye huset vi skal flytte inn i. Det skal bli fint,
   sa synes jeg."
EOF

echo ""
echo "Lyttepakke ferdig i $UT"
ls -1 "$UT"/*.wav 2>/dev/null | sed 's/^/  /'
