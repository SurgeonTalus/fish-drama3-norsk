#!/usr/bin/env python3
"""
Lag en Q4_K/Q2_K-blanding av Drama 3.

Trinn 1 (dette skriptet): dekvantiser eksperttensorene fra Q4_K til F16
   og skriv en mellom-GGUF.
Trinn 2: kjør audiocpp_gguf med --type q2_k og --keep-type for lagene
   som skal beholde Q4_K.

Hvorfor to trinn: Python-biblioteket gguf kan DEKVANTISERE K-quants, men
ikke kvantisere dem. audiocpp_gguf kan kvantisere, men bare fra F32/F16-kilder.
Så vi dekvantiserer først, og lar C++-verktøyet kvantisere.

Bruk:
    python3 bland_prep.py <input.gguf> <output_f16.gguf> <q4_layers.txt>
"""
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prune_gguf import GGUFReader, GGUFWriter, tensor_nbytes, BLOCK  # noqa: E402

import gguf.quants as quants  # noqa: E402

# GGUF-type -> numpy-kompatibel dequantize
DEQ = {12: 12, 10: 10, 11: 11, 13: 13, 14: 14, 8: 8, 1: 1, 0: 0}


def is_expert(logical_name):
    return ".mlp.experts." in (logical_name or "")


def layer_of(logical_name):
    if ".layers." not in logical_name:
        return -1
    tail = logical_name.split(".layers.")[1]
    return int(tail.split(".")[0])


def dequantize_expert(raw, dims, typ):
    """Dekvantiser en 3D-eksperttensor til F32 med riktig form."""
    arr = quants.dequantize(np.frombuffer(raw, dtype=np.uint8), typ)
    # ggml lagrer ne0 fastest; 3D-tensoren (d0, d1, d2) har ne0=d2
    # (ekspertdimensjonen), altså dims[2] -> ne0.
    # Antall "rader" = d0*d1, hver på ne0=d2 elementer.
    ne0 = dims[2]
    n_rows = dims[0] * dims[1]
    # gguf dequantize gir elementer i ne0-major rekkefølge per rad.
    return arr.reshape(n_rows, ne0)


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        raise SystemExit(1)
    in_path, out_path, layers_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])

    keep_q4 = set()
    with open(layers_path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                keep_q4.add(int(line))
    print(f"Behold Q4_K i lag: {sorted(keep_q4)}")

    r = GGUFReader(in_path)
    kv = dict(r.kv)
    names = r.kv["audiocpp.tensor_names"]

    new_dims = {}
    for i, t in enumerate(r.tensors):
        new_dims[t["name"]] = list(t["dims"])

    # Skriv ny header: de samme KV-ene, men tensor_shapes/rank oppdatert
    # (dims er uendrede, så shapes er uendrede).
    w = GGUFWriter(out_path)
    w.f.write(b"GGUF")
    w.f.write(struct.pack("<I", 3))
    w.f.write(struct.pack("<Q", len(r.tensors)))
    w.f.write(struct.pack("<Q", len(kv)))
    w.write_kv(kv, r.kv_types)

    for t in r.tensors:
        w._wstr(t["name"])
        dims = new_dims[t["name"]]
        w.f.write(struct.pack("<I", len(dims)))
        for d in dims:
            w.f.write(struct.pack("<Q", d))
        w.f.write(struct.pack("<I", t["type"]))
        w.f.write(struct.pack("<Q", 0))
    pos = w.f.tell()
    rem = pos % 32
    if rem:
        w.f.write(b"\x00" * (32 - rem))
    data_start = w.f.tell()

    offsets = {}
    cursor = data_start
    converted = 0
    for i, t in enumerate(r.tensors):
        logical = names[i] if i < len(names) else t["name"]
        offsets[t["name"]] = cursor - data_start
        raw = r.read_tensor(t)
        if is_expert(logical) and t["type"] in DEQ and t["type"] not in (1, 0):
            # dekvantiser til F32
            f32 = dequantize_expert(raw, t["dims"], t["type"])
            new_raw = f32.astype(np.float16).tobytes()
            w.f.write(new_raw)
            cursor += len(new_raw)
            converted += 1
        else:
            w.f.write(raw)
            cursor += len(raw)
        rem = cursor % 32
        if rem:
            w.f.write(b"\x00" * (32 - rem))
            cursor += rem
        if i % 200 == 0:
            print(f"  {i}/{len(r.tensors)}", flush=True)
    print(f"Dekvantiserte {converted} eksperttensorer til F16")

    w.f.close()
    r.f.close()

    # skriv offsets tilbake
    with open(out_path, "r+b") as f:
        # finn tensor-info-start
        f.seek(0)
        f.read(4); f.read(4); f.read(8); f.read(8)
        n_kv = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n_kv):
            n = struct.unpack("<Q", f.read(8))[0]; f.read(n)
            t = struct.unpack("<I", f.read(4))[0]
            if t == 8:
                n = struct.unpack("<Q", f.read(8))[0]; f.read(n)
            elif t == 9:
                et = struct.unpack("<I", f.read(4))[0]
                cnt = struct.unpack("<Q", f.read(8))[0]
                for _ in range(cnt):
                    if et == 8:
                        n = struct.unpack("<Q", f.read(8))[0]; f.read(n)
                    elif et in (0, 1, 7):
                        f.read(1)
                    elif et in (2, 3):
                        f.read(2)
                    elif et in (4, 5, 6):
                        f.read(4)
                    else:
                        f.read(8)
            elif t in (0, 1, 7):
                f.read(1)
            elif t in (2, 3):
                f.read(2)
            elif t in (4, 5, 6):
                f.read(4)
            else:
                f.read(8)
        tensor_info_start = f.tell()
        for t in r.tensors:
            nb = struct.unpack("<Q", f.read(8))[0]; f.read(nb)
            nd = struct.unpack("<I", f.read(4))[0]
            f.read(8 * nd)
            f.read(4)
            f.write(struct.pack("<Q", offsets[t["name"]]))
    print(f"Ferdig: {out_path} ({out_path.stat().st_size / 2**30:.2f} GiB)")


if __name__ == "__main__":
    main()
