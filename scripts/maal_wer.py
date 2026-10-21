#!/usr/bin/env python3
"""
Mål ordfeilrate (WER) og auto-detektert språk for en lydfil.

Bruk:
    python3 scripts/maal_wer.py output/tale.wav
    python3 scripts/maal_wer.py output/tale.wav "referanseteksten her"

Krever: pip install openai-whisper
"""
import re
import sys
import warnings

warnings.filterwarnings("ignore")
import whisper  # noqa: E402

DEFAULT_REF = (
    "Mal et A4-ark i grønne og gule nyanser. "
    "Mal en stor sirkel på 25,5 cm og fyll hele sirkel med farge."
)


def normalize(text):
    """Normaliser for sammenligning: lowercase, strip skilletegn, normaliser mellomrom."""
    text = text.lower().replace("–", "-").replace("—", "-")
    text = re.sub(r"[^a-z0-9æøå+\-.,% ]", " ", text)
    text = re.sub(r"([.,])", r" \1 ", text)
    return [w for w in text.split() if w not in {".", ","}]


def wer(reference_words, hypothesis_words):
    """Levenshtein-avstand på ordnivå, delt på referanselengde."""
    if not reference_words:
        return 0.0
    previous = list(range(len(hypothesis_words) + 1))
    for i, ref in enumerate(reference_words, 1):
        current = [i]
        for j, hyp in enumerate(hypothesis_words, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ref != hyp)))
        previous = current
    return previous[len(hypothesis_words)] / len(reference_words)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    path = sys.argv[1]
    reference = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_REF

    print(f"Laster Whisper small-modellen ...\n")
    model = whisper.load_model("small")

    forced = model.transcribe(path, language="no")
    auto = model.transcribe(path)

    w = wer(normalize(reference), normalize(forced["text"]))
    print(f"Fil            : {path}")
    print(f"Ordfeilrate    : {w * 100:.1f} %")
    print(f"Auto-språk     : {auto.get('language', '?')}")
    print(f"Transkripsjon  : {forced['text'].strip()}")
    print()
    print("Merk: auto-språk uten 'no' betyr at modellen har falt språket —")
    print("altså aksentdrift mot referansens språk.")


if __name__ == "__main__":
    main()
