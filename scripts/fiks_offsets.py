#!/usr/bin/env python3
"""
Skriv riktige offsets inn i en GGUF uten å bygge den på nytt.

Bakgrunn: bland_prep.py skrev data-seksjonen riktig, men offsets-skrivingen
feilet (KV-parsingen kom ett felt foran). Vi trenger bare å regne ut hvor
hver tensor begynner og skrive det inn.

Offsets følger ggml-regelen:
    offset[i] = offset[i-1] + GGML_PAD(nbytes[i-1], alignment)
der nbytes kommer fra dims og type.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prune_gguf import GGUFReader, tensor_nbytes, ALIGN  # noqa: E402


def tensor_info_start(path):
    """Finn byte-posisjonen der tensor-infoen begynner."""
    f = open(path, "rb")
    f.read(4)   # magic
    f.read(4)   # version
    f.read(8)   # n_tensors
    n_kv = struct.unpack("<Q", f.read(8))[0]
    for _ in range(n_kv):
        n = struct.unpack("<Q", f.read(8))[0]
        f.read(n)                      # nøkkel
        t = struct.unpack("<I", f.read(4))[0]
        if t == 8:                    # string
            n = struct.unpack("<Q", f.read(8))[0]
            f.read(n)
        elif t == 9:                  # array
            et = struct.unpack("<I", f.read(4))[0]
            cnt = struct.unpack("<Q", f.read(8))[0]
            if et == 8:               # string-array
                for _ in range(cnt):
                    n = struct.unpack("<Q", f.read(8))[0]
                    f.read(n)
            elif et in (0, 1, 7):     # 1 byte
                f.seek(cnt, 1)
            elif et in (2, 3):        # 2 byte
                f.seek(2 * cnt, 1)
            elif et in (4, 5, 6):     # 4 byte
                f.seek(4 * cnt, 1)
            else:                     # 8 byte
                f.seek(8 * cnt, 1)
        elif t in (0, 1, 7):
            f.seek(1, 1)
        elif t in (2, 3):
            f.seek(2, 1)
        elif t in (4, 5, 6):
            f.seek(4, 1)
        else:
            f.seek(8, 1)
    pos = f.tell()
    f.close()
    return pos


def main():
    if len(sys.argv) < 2:
        print("bruk: fiks_offsets.py <fil.gguf>")
        raise SystemExit(1)
    path = Path(sys.argv[1])

    r = GGUFReader(path)
    print(f"{path.name}: {len(r.tensors)} tensors")

    start = tensor_info_start(path)
    print(f"tensor-info starter på byte {start}")

    # Regn ut offset for hver tensor
    offsets = []
    cursor = 0
    for t in r.tensors:
        offsets.append(cursor)
        nb = tensor_nbytes(t["dims"], t["type"])
        cursor += (nb + ALIGN - 1) // ALIGN * ALIGN

    with open(path, "r+b") as f:
        f.seek(start)
        for t, off in zip(r.tensors, offsets):
            nb = struct.unpack("<Q", f.read(8))[0]
            f.read(nb)
            nd = struct.unpack("<I", f.read(4))[0]
            f.read(8 * nd)
            f.read(4)
            f.write(struct.pack("<Q", off))

    print(f"Skrev {len(offsets)} offsets. Siste tensor slutter ved byte {cursor}.")
    total = path.stat().st_size
    print(f"Filstørrelse: {total / 2**30:.2f} GiB (data forventes å slutte ved ~{(start + cursor) / 2**30:.2f} GiB)")


if __name__ == "__main__":
    main()
