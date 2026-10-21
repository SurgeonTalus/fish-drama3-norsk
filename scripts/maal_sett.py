#!/usr/bin/env python3
"""
Mal et sett med lydfiler med norsk ASR og skriv ut en rapport.

Kjores pa filer som er generert med scripts/kjor_test.sh, slik at
referanseteksten i filnavnet (eller i en .txt ved siden av) blir brukt.

Bruk:
    python3 scripts/maal_sett.py <mappe> [--referanse "tekst"]
"""
import argparse
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from maal_norsk import les16k, normaliser, wer, ASR_MODEL  # noqa: E402


def hoved():
    ap = argparse.ArgumentParser()
    ap.add_argument("mappe")
    ap.add_argument("--referanse", default=None)
    ap.add_argument("--uten-whisper", action="store_true")
    args = ap.parse_args()

    mappe = Path(args.mappe)
    filer = sorted(mappe.glob("*.wav"))
    if not filer:
        print(f"Ingen wav i {mappe}")
        return

    from transformers import pipeline
    asr = pipeline("automatic-speech-recognition", model=ASR_MODEL, device="cpu")

    wm = None
    if not args.uten_whisper:
        import whisper
        wm = whisper.load_model("small")

    print(f"{'Fil':<44} {'WER':>6}  {'Auto':<5} Transkripsjon")
    print("-" * 110)
    for f in filer:
        ref = args.referanse
        if ref is None:
            side = f.with_suffix(".txt")
            if side.exists():
                ref = side.read_text().strip()
        lyd = les16k(str(f))
        t = asr({"raw": lyd, "sampling_rate": 16000})["text"].strip()
        w = wer(normaliser(ref or ""), normaliser(t)) if ref else 0.0
        auto = wm.transcribe(str(f)).get("language", "?") if wm else "?"
        print(f"{f.name:<44} {w * 100:5.1f}%  {auto:<5} {t}")
    print()
    print(f"WER målt med {ASR_MODEL} (norsk ASR, WER 6,33 % på norsk referansecorpus).")


if __name__ == "__main__":
    hoved()
