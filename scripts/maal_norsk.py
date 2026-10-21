#!/usr/bin/env python3
"""
Mål norsk taleforlarlighet med en norsk ASR-modell.

Hvorfor ikke Whisper small: Whisper smalls norsk er svakt. Den skriver
norske ord i engelsk ortografi og bommer tall, saa ordfeilraten (WER)
blir dominert av ASR-feil, ikke av modellens feil. Alle modellene vi maalte
fikk omtrent samme WER uansett kvalitet.

Derfor bruker vi NB AI Labs norske wav2vec2:
  NbAiLab/nb-wav2vec2-1b-bokmaal  ->  WER 6,33 % paa norsk (NoDaLiDa 2023)

To talegir hver for seg:
  1. FORSTAELELIGHET  = WER mot referanseteksten, med norsk ASR.
  2. AKSENT          = hvilket sprak Whisper auto-detekterer, pluss
                        et menneskelig oere (referanseteksten er norsk).

Bruk:
    python3 scripts/maal_norsk.py lyd.wav "referansetekst"
    python3 scripts/maal_norsk.py lyd.wav "referansetekst" --stille
"""
import argparse
import re
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

DEFAULT_REF = (
    "I går gikk jeg en tur langs elven sammen med min sønn. "
    "Vi snakket om sommerferien og om det nye huset vi skal flytte inn i."
)

ASR_MODEL = "NbAiLab/nb-wav2vec2-1b-bokmaal"


def normaliser(text):
    """Normaliser for sammenligning: lowercase, strip skilletegn, norsk bokstaver."""
    text = text.lower().replace("–", "-").replace("—", "-")
    text = re.sub(r"[^a-z0-9æøå+\-.,% ]", " ", text)
    text = re.sub(r"([.,])", r" \1 ", text)
    return [w for w in text.split() if w not in {".", ","}]


def wer(referanse, hypotese):
    """Levenshtein-avstand paa ordnivaa, delt paa referanselengde."""
    if not referanse:
        return 0.0
    forr = list(range(len(hypotese) + 1))
    for i, ref in enumerate(referanse, 1):
        naa = [i]
        for j, hyp in enumerate(hypotese, 1):
            naa.append(min(forr[j] + 1, naa[j - 1] + 1,
                           forr[j - 1] + (ref != hyp)))
        forr = naa
    return forr[len(hypotese)] / len(referanse)


def les16k(path):
    """Les WAV og resample til 16 kHz mono (det wav2vec2-modellen vil ha)."""
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    data = data.mean(axis=1)
    if sr != 16000:
        import librosa
        data = librosa.resample(data, orig_sr=sr, target_sr=16000)
    return data.astype(np.float32)


def last_asr():
    """Last den norske ASR-modellen (cachees av Hugging Face)."""
    from transformers import pipeline
    return pipeline("automatic-speech-recognition", model=ASR_MODEL,
                    device="cpu")


def mal(lyd, referanse, asr=None, med_whisper=True):
    if asr is None:
        asr = last_asr()

    lyd16 = les16k(lyd)
    res = asr({"raw": lyd16, "sampling_rate": 16000})
    trans = res["text"].strip()

    w = wer(normaliser(referanse), normaliser(trans))

    auto_sprak = "?"
    auto_tekst = ""
    if med_whisper:
        import whisper
        wm = whisper.load_model("small")
        a = wm.transcribe(lyd)
        auto_sprak = a.get("language", "?")
        auto_tekst = a["text"].strip()

    return {
        "fil": lyd,
        "wer": w,
        "transkripsjon": trans,
        "auto_sprak": auto_sprak,
        "auto_tekst": auto_tekst,
    }


def hoved():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("lyd")
    ap.add_argument("referanse", nargs="?", default=DEFAULT_REF)
    ap.add_argument("--stille", action="store_true",
                    help="bare skriv ut tallene")
    ap.add_argument("--ingen-whisper", action="store_true")
    args = ap.parse_args()

    r = mal(args.lyd, args.referanse, med_whisper=not args.ingen_whisper)

    if args.stille:
        print(f"{r['wer'] * 100:.1f}\t{r['auto_sprak']}")
        return

    print(f"Fil            : {r['fil']}")
    print(f"Ordfeilrate    : {r['wer'] * 100:.1f} %   (norsk ASR: {ASR_MODEL})")
    print(f"Auto-sprak     : {r['auto_sprak']}   (Whisper small, auto)")
    print(f"Transkripsjon  : {r['transkripsjon']}")
    if r["auto_tekst"]:
        print(f"Whisper auto   : {r['auto_tekst']}")
    print()
    print("Aksent vurderes av et menneske, ikke av et tall. Se docs/ for metoden.")


if __name__ == "__main__":
    hoved()
