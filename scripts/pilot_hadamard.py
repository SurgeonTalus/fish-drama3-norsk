#!/usr/bin/env python3
"""
PILOT: reduserer en Hadamard-rotasjon kvantiseringsfeilen?

Spoersmaalet: vi vil vite om en modell der ekspertene er rotert foer
kvantisering (QuIP#/SpinQuant-stil incoherence processing) gir mindre
stoei enn uten rotasjon.

Vi tar ekte ekspertveikter fra Q4_K_S-modellen (dekvantisert til F32),
roterer dem med en Walsh-Hadamard-matrise, kvantiserer begge varianter
til 2 bit, og sammenligner feilen i LAGENS UTGANG for en testvektor.

Matematikken: er R = (1/sqrt(n)) * H_sylvester * S, der S er en diagonal
med tilfeldige +/-1, saa er R R^T = I. Da er

    (W R)(R^T x) = W R R^T x = W x

saa den roterede modellen er matematisk identisk, men vektene er
Gaussiske naar de kvantiseres.

Bruk:
    python3 pilot_hadamard.py modell.gguf [--lag 0,12,25,39] [--eksperter 3]
"""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prune_gguf import GGUFReader  # noqa: E402

import gguf.quants as quants  # noqa: E402
from gguf.constants import GGMLQuantizationType as QT  # noqa: E402

# gguf.quants kan bare kvantisere noen typer fra Python. Vi bruker de som
# dekker 2 bit, pluss Q4_0 som referanse paa 4,5 bit.
TYPER = [("TQ2_0", QT.TQ2_0), ("TQ1_0", QT.TQ1_0), ("Q4_0", QT.Q4_0)]


def hadamard(n, seed=0):
    """Symmetrisk Walsh-Hadamard (Sylvester) normalisert, med tilfeldige tegn."""
    assert n & (n - 1) == 0, "n maa vaere et potens av 2"
    h = np.ones((1, 1), dtype=np.float64)
    while h.shape[0] < n:
        h = np.block([[h, h], [h, -h]])
    h /= np.sqrt(n)
    rng = np.random.default_rng(seed)
    s = rng.choice([-1.0, 1.0], size=n)
    return h * s[None, :]        # R = H S ;  R R^T = I


def feil(w, wq, x, rot=None):
    """Relativ feil i lagets utgang: ||W x - Wq (x')|| / ||W x||."""
    ref = w @ x
    if rot is None:
        ut = wq @ x
    else:
        ut = wq @ (rot.T @ x)
    return np.linalg.norm(ut - ref) / (np.linalg.norm(ref) + 1e-12)


def hoved():
    ap = argparse.ArgumentParser()
    ap.add_argument("modell", type=Path)
    ap.add_argument("--lag", default="0,12,25,39")
    ap.add_argument("--eksperter", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    r = GGUFReader(args.modell)
    navn = r.kv["audiocpp.tensor_names"]
    index = {}
    for i, t in enumerate(r.tensors):
        index[navn[i]] = i

    lag = [int(x) for x in args.lag.split(",")]
    print(f"{'lag':>4} {'eks':>4} {'type':>8} {'rotert feil':>13} {'vanlig feil':>13} "
          f"{'forbedring':>12}")
    print("-" * 62)

    samlet = {}
    for L in lag:
        n = 0
        for proj in ("gate_proj", "up_proj", "down_proj"):
            nøkkel = (f"model_weights/model.language_model.layers.{L}"
                      f".mlp.experts.{proj}.weight")
            if nøkkel not in index:
                continue
            t = r.tensors[index[nøkkel]]
            dims = t["dims"]                 # [in, out, eksperter] i ggml-rekkefolge
            rå = r.read_tensor(t)
            w_q4 = quants.dequantize(np.frombuffer(rå, dtype=np.uint8), QT.Q4_K)
            # ggml: ne0 = dims[0] = in-dimensjonen (hidden for gate/up)
            in_dim = dims[0]
            ant = w_q4.size // in_dim
            W = w_q4.reshape(ant, in_dim)    # (rader=out, kolonner=in)
            R = hadamard(in_dim, seed=args.seed + L)

            # Testvektorer: Gaussisk (tung hale) og Laplace (ekstremt tung hale)
            rng = np.random.default_rng(1234 + L)
            x_gauss = rng.standard_normal(in_dim).astype(np.float32)
            x_lap = rng.laplace(0, 1, in_dim).astype(np.float32)

            for x, xnavn in ((x_gauss, "gauss"), (x_lap, "laplace")):
                WR = (W.astype(np.float64) @ R).astype(np.float32)
                for tnavn, ttype in TYPER:
                    try:
                        q_rot = quants.quantize(WR, ttype)
                        q_var = quants.quantize(W, ttype)
                    except Exception as e:
                        print(f"{L:>4} {n:>4} {tnavn:>8}  kunne ikke: {str(e)[:40]}")
                        continue
                    d_rot = quants.dequantize(q_rot, ttype)
                    d_var = quants.dequantize(q_var, ttype)
                    e_rot = feil(W.astype(np.float32), d_rot, x, rot=R)
                    e_var = feil(W.astype(np.float32), d_var, x)
                    nøkkel2 = (tnavn, xnavn)
                    samlet.setdefault(nøkkel2, []).append((e_rot, e_var))
                    print(f"{L:>4} {n:>4} {tnavn:>8} {e_rot:>13.5f} {e_var:>13.5f} "
                          f"{(e_var/e_rot if e_rot else 0):>11.2f}x  ({xnavn})")
            n += 1
            if n >= args.eksperter:
                break

    print()
    print("SAMLET over alle lag og eksperter:")
    for (tnavn, xnavn), v in sorted(samlet.items()):
        rot = np.mean([a for a, _ in v])
        var = np.mean([b for _, b in v])
        print(f"  {tnavn:>8} ({xnavn:>8}): rotert {rot:.5f}  vanlig {var:.5f}  "
              f"-> {var/rot:.2f}x bedre med rotasjon")
    r.f.close()


if __name__ == "__main__":
    hoved()
