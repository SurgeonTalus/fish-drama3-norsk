#!/usr/bin/env python3
"""
Bygg en modell med utvalgte lag, omnummerert fortløpende.

Runtime-en laster lag 0..num_hidden_layers-1 med navnet
  model_weights/model.language_model.layers.N....
Derfor: fjerner vi de lagene vi ikke vil ha, og skriver de gjenværende
lagene om til 0, 1, 2, ... Uten dette hadde vi trengt en runtime-endring.

Eksempel: behold lag 0,1,2,4,6,...,36,38,39 -> 22 lag, der det nye lag 3
er det gamle lag 4.

Dette er "layer dropping" i praksis: de overlevende lagene ligger spredt
i hele stabelen, saa hvert av dem gjoer jobben for to.

Bruk:
    python3 bygg_lagvalg.py --input kilder.gguf --output ut.gguf \\
        --behold 0,1,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,39
"""
import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prune_gguf import GGUFReader, GGUFWriter, ALIGN  # noqa: E402

PREFIX = "model_weights/model.language_model.layers."


def lag_av(logisk_navn):
    if not logisk_navn.startswith(PREFIX):
        return None
    rest = logisk_navn[len(PREFIX):]
    return int(rest.split(".")[0])


def nytt_navn(logisk_navn, ny_indeks):
    """Bytt ut .layers.<gammel>. med .layers.<ny>."""
    rest = logisk_navn[len(PREFIX):]
    _, _, halen = rest.partition(".")
    return f"{PREFIX}{ny_indeks}.{halen}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--behold", required=True,
                    help="kommaseparerte lagindekser, f.eks. 0,1,2,4,6")
    args = ap.parse_args()

    behold = [int(x) for x in args.behold.replace(" ", "").split(",") if x != ""]
    behold.sort()
    ny_indeks = {gammel: ny for ny, gammel in enumerate(behold)}
    n_lag = len(behold)
    print(f"Beholder {n_lag} lag: {behold}")

    r = GGUFReader(args.input)
    kv = dict(r.kv)
    navn = r.kv["audiocpp.tensor_names"]
    orig_ranks = list(kv.get("audiocpp.tensor_ranks", []))
    orig_shapes = list(kv.get("audiocpp.tensor_shapes", []))

    # ── Velg tensorer og nye logiske navn ───────────────────────
    behold_idx = []
    ny_navn = []
    for i, t in enumerate(r.tensors):
        logisk = navn[i] if i < len(navn) else t["name"]
        gammel_lag = lag_av(logisk)
        if gammel_lag is None or gammel_lag in ny_indeks:
            behold_idx.append(i)
            ny_navn.append(logisk if gammel_lag is None
                            else nytt_navn(logisk, ny_indeks[gammel_lag]))
    print(f"  {len(behold_idx)} av {len(r.tensors)} tensorer beholdt")

    # ── Patch embedded config.json: num_hidden_layers ────────────
    ef_names = kv.get("audiocpp.embedded_files.names")
    ef_offsets = kv.get("audiocpp.embedded_files.offsets")
    ef_data = kv.get("audiocpp.embedded_files.data")
    if not (ef_names and ef_offsets and ef_data):
        raise SystemExit("fant ikke embedded_files i GGUF")
    cfg_idx = ef_names.index("config.json")
    cfg_start = ef_offsets[cfg_idx]
    cfg_end = ef_offsets[cfg_idx + 1] if cfg_idx + 1 < len(ef_offsets) else len(ef_data)
    ef_blob = bytes(ef_data) if isinstance(ef_data, (bytes, bytearray)) \
        else bytes((v & 0xFF) for v in ef_data)
    cfg_bytes = bytearray(ef_blob[cfg_start:cfg_end])
    cfg = json.loads(cfg_bytes.decode("utf-8"))
    tc = cfg.get("text_config", {})
    gammel_lag = tc.get("num_hidden_layers")
    tc["num_hidden_layers"] = n_lag
    ny_cfg_text = json.dumps(cfg, separators=(",", ":"))
    if len(ny_cfg_text) > len(cfg_bytes):
        raise SystemExit(f"ny config.json ({len(ny_cfg_text)}) lengre enn "
                         f"originalen ({len(cfg_bytes)})")
    ny_data = bytearray()
    ny_offsets = [0]
    for i, name in enumerate(ef_names):
        start = ef_offsets[i]
        end = ef_offsets[i + 1] if i + 1 < len(ef_offsets) else len(ef_data)
        if i == cfg_idx:
            ny_data += ny_cfg_text.encode("utf-8")[:end - start].ljust(end - start, b" ")
        else:
            ny_data += ef_blob[start:end]
        ny_offsets.append(len(ny_data))
    kv["audiocpp.embedded_files.offsets"] = ny_offsets
    kv["audiocpp.embedded_files.data"] = list(ny_data)
    print(f"  config.json: num_hidden_layers {gammel_lag} -> {n_lag}")

    # ── Oppdater tensor_names / ranks / shapes ──────────────────
    cursor = 0
    ny_ranks = []
    ny_shapes = []
    for teller, i in enumerate(behold_idx):
        rk = orig_ranks[i] if i < len(orig_ranks) else 0
        ny_ranks.append(rk)
        ny_shapes.extend(orig_shapes[cursor:cursor + rk])
        cursor += rk
    for k in list(kv):
        if k.endswith("tensor_names"):
            kv[k] = ny_navn
        elif k.endswith("tensor_ranks"):
            kv[k] = ny_ranks
        elif k.endswith("tensor_shapes"):
            kv[k] = ny_shapes

    # ── Skriv filen ─────────────────────────────────────────────
    w = GGUFWriter(args.output)
    w.f.write(b"GGUF")
    w.f.write(struct.pack("<I", 3))
    w.f.write(struct.pack("<Q", len(behold_idx)))
    w.f.write(struct.pack("<Q", len(kv)))
    w.write_kv(kv, r.kv_types)

    tensor_info_start = w.f.tell()
    for i in behold_idx:
        t = r.tensors[i]
        w._wstr(t["name"])
        w.f.write(struct.pack("<I", len(t["dims"])))
        for d in t["dims"]:
            w.f.write(struct.pack("<Q", d))
        w.f.write(struct.pack("<I", t["type"]))
        w.f.write(struct.pack("<Q", 0))
    pos = w.f.tell()
    rem = pos % ALIGN
    if rem:
        w.f.write(b"\x00" * (ALIGN - rem))
    data_start = w.f.tell()

    offsets = {}
    cursor = data_start
    print(f"=== Skriver {args.output} ===", flush=True)
    for teller, i in enumerate(behold_idx):
        t = r.tensors[i]
        offsets[teller] = cursor - data_start
        data = r.read_tensor(t)
        w.f.write(data)
        cursor += len(data)
        # Paddingen er RELATIV til data_start, som ggml gjoer.
        rem = (cursor - data_start) % ALIGN
        if rem:
            w.f.write(b"\x00" * (ALIGN - rem))
            cursor += ALIGN - rem
        if teller % 200 == 0:
            print(f"  {teller}/{len(behold_idx)}  ({cursor / 2**30:.1f} GiB)", flush=True)

    # ── Skriv offsets tilbake ───────────────────────────────────
    with open(args.output, "r+b") as f:
        f.seek(tensor_info_start)
        for teller in range(len(behold_idx)):
            nb = struct.unpack("<Q", f.read(8))[0]
            f.read(nb)
            nd = struct.unpack("<I", f.read(4))[0]
            f.read(8 * nd)
            f.read(4)
            f.write(struct.pack("<Q", offsets[teller]))

    w.f.close()
    r.f.close()
    total = args.output.stat().st_size
    print(f"Ferdig: {args.output} ({total / 2**30:.2f} GiB, {n_lag} lag)")


if __name__ == "__main__":
    main()
