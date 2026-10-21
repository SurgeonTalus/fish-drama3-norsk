#!/usr/bin/env python3
"""
Prune Drama 3's MoE experts DIREKT I en eksisterende GGUF.

Nøkkelobservasjon: ekspertene ligger i Q4_K-tensorer med form
    gate_proj / up_proj:  (2048, 512, 256)   ne2 = 256 eksperter
    down_proj:            (512, 2048, 256)   ne2 = 256 eksperter
    router:               (2048, 256)        ne1 = 256 eksperter

GGML lagrer ne0 fastest-varying, og Q4_K har blokkstørrelse 256. Derfor
er hver ekspertens data et sett av uavhengige blokker langs ne0, og
slicing av eksperter er EN REN BYTE-KOPIERING — ingen dekvantisering,
ingen ny kvantisering, intet kvalitetstap utover selve pruningen.

Ingen 38,7 GB nedlasting, ingen 68 GiB intermediate, ingen GPU.
"""
import argparse
import json
import struct
from pathlib import Path

# GGML-type -> (block_size, bytes_per_block)
BLOCK = {
    0: (1, 4), 1: (1, 2), 2: (32, 18), 3: (32, 20), 6: (32, 22), 7: (32, 24),
    8: (32, 34), 9: (32, 36), 10: (256, 84), 11: (256, 110), 12: (256, 144),
    13: (256, 176), 14: (256, 210), 15: (256, 292), 16: (256, 66), 17: (256, 74),
    18: (256, 98), 19: (256, 50), 20: (256, 110), 21: (256, 82), 22: (256, 136),
    23: (256, 170), 24: (256, 210), 25: (256, 292),
}
ALIGN = 32
PREFIX = "model_weights/model.language_model.layers."


def tensor_nbytes(dims, typ):
    """
    ggml_nbytes for en tensor, etter ggml.c sin formel.

    GGUF leser dims som ne[0]=dims[0], ne[1]=dims[1], ... (ikke omvendt).
    For F16/F32 er nb[0] = ne[0]*elemsize og nb[i] = nb[i-1]*ne[i], og
    nbytes = elemsize + sum((ne[i]-1)*nb[i]).

    Merk at en rank-1 F16-tensor med ne0=1 gir 2 byte, mens rank-2
    [1, 96] gir 18242 byte — ikke 192. Det er denne detaljen som gjør
    at en naiv "produkt av dims" gir feil offset.
    """
    if typ in BLOCK:
        bs, pb = BLOCK[typ]
        n = 1
        for d in dims:
            n *= d
        return (n // bs) * pb
    if typ in (1, 0):
        elemsize = 2 if typ == 1 else 4
        ne = list(dims) + [1] * (4 - len(dims))
        nb = [ne[0] * elemsize]
        for i in range(1, 4):
            nb.append(nb[-1] * ne[i])
        total = elemsize
        for i in range(4):
            total += (ne[i] - 1) * nb[i]
        return total
    raise ValueError(f"ukjent tensor-type {typ}")


class GGUFReader:
    def __init__(self, path):
        self.f = open(path, "rb")
        assert self.f.read(4) == b"GGUF"
        self.ver = struct.unpack("<I", self.f.read(4))[0]
        n_tensors = struct.unpack("<Q", self.f.read(8))[0]
        n_kv = struct.unpack("<Q", self.f.read(8))[0]
        self.kv = {}
        self.kv_types = {}
        for _ in range(n_kv):
            k = self._rstr()
            t = struct.unpack("<I", self.f.read(4))[0]
            self.kv_types[k] = t
            self.kv[k] = self._rval(t)
            if t == 9:
                self.kv_types[k] = ("array", self._last_array_elem_type)
        self.tensors = []
        for _ in range(n_tensors):
            name = self._rstr()
            ndims = struct.unpack("<I", self.f.read(4))[0]
            dims = [struct.unpack("<Q", self.f.read(8))[0] for _ in range(ndims)]
            typ = struct.unpack("<I", self.f.read(4))[0]
            off = struct.unpack("<Q", self.f.read(8))[0]
            self.tensors.append({"name": name, "dims": dims, "type": typ, "offset": off})
        self.data_start = self._align(self.f.tell())
        # Tensor-indeks -> semantisk navn (fra audiocpp.tensor_names)
        self.index_to_name = {}
        names = self.kv.get("audiocpp.tensor_names")
        if isinstance(names, list) and len(names) == len(self.tensors):
            for i, nm in enumerate(names):
                self.index_to_name[i] = nm

    def _align(self, pos):
        return (pos + ALIGN - 1) // ALIGN * ALIGN

    def _rstr(self):
        n = struct.unpack("<Q", self.f.read(8))[0]
        return self.f.read(n).decode("utf-8", "replace")

    def _rval(self, t):
        f = self.f
        if t == 0:   # UINT8
            return struct.unpack("<B", f.read(1))[0]
        if t == 1:   # INT8
            return struct.unpack("<b", f.read(1))[0]
        if t == 2:   # INT16
            return struct.unpack("<h", f.read(2))[0]
        if t == 3:   # UINT16
            return struct.unpack("<H", f.read(2))[0]
        if t == 4:   # INT32
            return struct.unpack("<i", f.read(4))[0]
        if t == 5:   # UINT32
            return struct.unpack("<I", f.read(4))[0]
        if t == 6:   # FLOAT32
            return struct.unpack("<f", f.read(4))[0]
        if t == 7:   # BOOL
            return struct.unpack("<?", f.read(1))[0]
        if t == 8:   # STRING
            return self._rstr()
        if t == 9:   # ARRAY
            et = struct.unpack("<I", f.read(4))[0]
            n = struct.unpack("<Q", f.read(8))[0]
            self._last_array_elem_type = et
            if et == 8:
                return [self._rstr() for _ in range(n)]
            if et == 0:
                return list(f.read(n))
            if et == 1:
                return list(struct.unpack(f"<{n}b", f.read(n)))
            if et == 2:
                return list(struct.unpack(f"<{n}h", f.read(2 * n)))
            if et == 3:
                return list(struct.unpack(f"<{n}H", f.read(2 * n)))
            if et == 4:
                return list(struct.unpack(f"<{n}i", f.read(4 * n)))
            if et == 5:
                return list(struct.unpack(f"<{n}I", f.read(4 * n)))
            if et == 6:
                return list(struct.unpack(f"<{n}f", f.read(4 * n)))
            if et == 7:
                return list(struct.unpack(f"<{n}?", f.read(n)))
            if et == 10:
                return list(struct.unpack(f"<{n}Q", f.read(8 * n)))
            if et == 11:
                return list(struct.unpack(f"<{n}q", f.read(8 * n)))
            if et == 12:
                return list(struct.unpack(f"<{n}d", f.read(8 * n)))
            raise ValueError(f"ukjent array-elemtype {et}")
        if t == 10:  # INT64
            return struct.unpack("<q", f.read(8))[0]
        if t == 11:  # UINT64
            return struct.unpack("<Q", f.read(8))[0]
        if t == 12:  # FLOAT64
            return struct.unpack("<d", f.read(8))[0]
        raise ValueError(f"ukjent KV-type {t}")

    def read_tensor(self, t):
        self.f.seek(self.data_start + t["offset"])
        return self.f.read(tensor_nbytes(t["dims"], t["type"]))

    def semantic(self, t):
        """Navnet tensoren representerer (fra tensor_names, ellers _audiocpp.N)."""
        return self.index_to_name.get(t["_idx"], t["name"])


class GGUFWriter:
    def __init__(self, path):
        self.f = open(path, "wb")

    def _wstr(self, s):
        b = s.encode("utf-8")
        self.f.write(struct.pack("<Q", len(b)))
        self.f.write(b)

    def _wval(self, t, v):
        if t == 0:
            self.f.write(struct.pack("<B", v))
        elif t == 1:
            self.f.write(struct.pack("<b", v))
        elif t == 2:
            self.f.write(struct.pack("<h", v))
        elif t == 3:
            self.f.write(struct.pack("<H", v))
        elif t == 4:
            self.f.write(struct.pack("<i", v))
        elif t == 5:
            self.f.write(struct.pack("<I", v))
        elif t == 6:
            self.f.write(struct.pack("<f", v))
        elif t == 7:
            self.f.write(struct.pack("<?", v))
        elif t == 8:
            self._wstr(v)
        elif t == 9:
            self.f.write(struct.pack("<I", 11))
            self.f.write(struct.pack("<Q", len(v)))
            for e in v:
                self.f.write(struct.pack("<Q", int(e)))
        elif t == 10:
            self.f.write(struct.pack("<q", v))
        elif t == 11:
            self.f.write(struct.pack("<Q", v))
        elif t == 12:
            self.f.write(struct.pack("<d", v))
        else:
            raise ValueError(t)

    def write_kv(self, kv, kv_types=None):
        for k, v in kv.items():
            self._wstr(k)
            orig = (kv_types or {}).get(k)
            if isinstance(v, bool):
                self.f.write(struct.pack("<I", 8))
                self._wstr("true" if v else "false")
            elif isinstance(v, int):
                # Bevar den opprinnelige KV-typen (f.eks. INT32 for
                # model_spec.version). Type-størrelsen påvirker header-
                # størrelsen, og dermed hvor data-seksjonen begynner.
                t_int = orig if isinstance(orig, int) else (10 if v < 0 else 11)
                self.f.write(struct.pack("<I", t_int))
                self._wval(t_int, v)
            elif isinstance(v, float):
                self.f.write(struct.pack("<I", 12))
                self._wval(12, v)
            elif isinstance(v, str):
                self.f.write(struct.pack("<I", 8))
                self._wstr(v)
            elif isinstance(v, list):
                et = 11
                if isinstance(orig, tuple) and orig[0] == "array":
                    et = orig[1]
                self.f.write(struct.pack("<I", 9))
                self.f.write(struct.pack("<I", et))
                self.f.write(struct.pack("<Q", len(v)))
                if et == 8:
                    # string-array
                    for e in v:
                        b = e.encode("utf-8")
                        self.f.write(struct.pack("<Q", len(b)))
                        self.f.write(b)
                else:
                    # numeriske elementtyper: 0=uint8 1=int8 2=uint16 3=int16
                    # 4=uint32 5=int32 10=uint64 11=int64 12=float64
                    fmt = {0: "<B", 1: "<b", 2: "<H", 3: "<h",
                           4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q",
                           11: "<q", 12: "<d"}.get(et, "<Q")
                    for e in v:
                        self.f.write(struct.pack(fmt, int(e)))
            else:
                raise ValueError(f"ukjent KV-type for {k}: {type(v)}")

    def align(self):
        rem = self.f.tell() % ALIGN
        if rem:
            self.f.write(b"\x00" * (ALIGN - rem))


def is_expert_tensor(logical_name):
    """
    Er dette en tensor hvis form endres ved pruning?

    Både de ruted ekspertene (.mlp.experts.*) OG routeren
    (.mlp.gate.weight) endrer form, fordi antallet eksperter per lag
    går fra 256 til det nye tallet.
    """
    if not logical_name:
        return False
    if ".mlp.experts." in logical_name:
        return True
    # Routeren: "...layers.N.mlp.gate.weight"
    tail = logical_name.split(".mlp.")[-1] if ".mlp." in logical_name else ""
    return tail == "gate.weight"


def shape_segment(dims):
    """
    (rank, verdier) for én tensor, slik runtime-en forventer dem.

    Runtime-en (tensor_source.cpp) leser ranks[i] verdier fra tensor_shapes
    per tensor, og setter info.shape = de verdiene. For 1D- og 2D-tensorer
    med første dim == 1 bruker originalen én ekstra "1" (rank+1), ellers er
    verdiene de omvendte dims (ne0 først).

    Eksempel:
        dims [2048]        -> (1, [2048])
        dims [1, 2048]     -> (2, [1, 2048])
        dims [2048, 512, 256] -> (3, [256, 512, 2048])
    """
    d = list(dims)
    if d and d[0] == 1:
        # Originalen bruker én ekstra "1" på slutten for disse.
        return len(d) + 1, d + [1]
    return len(d), list(reversed(d))


def parse_semantic(name):
    """(lag, projeksjon) fra et semantisk tensor-navn."""
    if not name.startswith(PREFIX):
        return None
    parts = name[len(PREFIX):].split(".")
    if len(parts) < 4 or parts[1] != "mlp":
        return None
    layer = int(parts[0])
    if parts[2] == "experts":
        return layer, parts[3]          # gate_proj / up_proj / down_proj
    if parts[2] == "gate" and parts[3] == "weight":
        return layer, "router"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--stats", type=Path, required=True)
    ap.add_argument("--keep", type=int, default=100)
    ap.add_argument("--protected-layers", default="0,1,2,36")
    ap.add_argument("--protected-count", type=int, default=256)
    ap.add_argument("--criterion", default="mass", choices=["mass", "freq"])
    args = ap.parse_args()

    import torch
    snap = torch.load(args.stats, weights_only=False)
    crit = "mass" if args.criterion == "mass" else "freq"
    protected = {int(x) for x in args.protected_layers.split(",") if x.strip()}

    r = GGUFReader(args.input)
    for i, t in enumerate(r.tensors):
        t["_idx"] = i
    print(f"Input: {args.input}")
    print(f"  {len(r.tensors)} tensors, {len(r.kv)} KV-par", flush=True)

    # ── Klassifiser ─────────────────────────────────────────────
    expert_t, router_t = {}, {}
    for t in r.tensors:
        sem = r.semantic(t)
        parsed = parse_semantic(sem)
        if not parsed:
            continue
        layer, kind = parsed
        if kind == "router":
            router_t[layer] = t
        else:
            expert_t[(layer, kind)] = t

    layers = sorted({l for l, _ in expert_t})
    if len(layers) != 40:
        raise SystemExit(f"forventet 40 lag med eksperter, fant {len(layers)}")
    if len(router_t) != 40:
        raise SystemExit(f"forventet 40 routere, fant {len(router_t)}")
    print(f"  {len(expert_t)} eksperttensorer, {len(router_t)} routere", flush=True)

    s = expert_t[(layers[0], "gate_proj")]
    if len(s["dims"]) != 3 or s["dims"][2] != 256:
        raise SystemExit(f"uventet ekspertform {s['dims']}")
    rs = router_t[layers[0]]
    if len(rs["dims"]) != 2 or rs["dims"][1] != 256:
        raise SystemExit(f"uventet routerform {rs['dims']}")
    print(f"  ekspertform {s['dims']} type={s['type']}, router {rs['dims']} type={rs['type']} ✓", flush=True)

    # ── Velg eksperter per lag ──────────────────────────────────
    keep_map, per_layer, covs = {}, [], []
    for layer in layers:
        scores = snap[layer][crit]
        n_keep = args.protected_count if layer in protected else args.keep
        n_keep = min(n_keep, scores.numel())
        kept = sorted(int(i) for i in torch.topk(scores, n_keep).indices)
        keep_map[layer] = kept
        per_layer.append(len(kept))
        covs.append(float(scores[torch.tensor(kept)].sum() / scores.sum()))

    print(f"\n=== Valg: keep={args.keep}, beskyttet {sorted(protected)} -> {args.protected_count} ===")
    print(f"  ekspertspor: {sum(per_layer)} av {40 * 256} ({sum(per_layer) / (40 * 256) * 100:.1f} %)")
    print(f"  dekning: min={min(covs) * 100:.1f}%  mean={sum(covs) / len(covs) * 100:.1f}%")
    for layer in layers[:5]:
        print(f"    lag {layer:2d}: keep={per_layer[layer]:3d}  dekning={covs[layer] * 100:5.1f}%")

    # ── Beregn nye dims ─────────────────────────────────────────
    new_dims = {}
    for t in r.tensors:
        dims = list(t["dims"])
        parsed = parse_semantic(r.semantic(t))
        if parsed:
            layer, kind = parsed
            if kind == "router":
                dims[1] = per_layer[layer]
            else:
                dims[2] = per_layer[layer]
        new_dims[t["name"]] = dims

    # ── Oppdater embedded config.json (sidecar-blob) ────────────
    # VIKTIG: config.json skrives med SAMME byte-lengde som originalen,
    # slik at header-størrelsen (og dermed data_start) er identisk.
    # Vi patcher bare "num_experts" -> ny verdi, og lar resten være.
    kv = dict(r.kv)
    ef_names = kv.get("audiocpp.embedded_files.names")
    ef_offsets = kv.get("audiocpp.embedded_files.offsets")
    ef_data = kv.get("audiocpp.embedded_files.data")

    if not (ef_names and ef_offsets and ef_data):
        raise SystemExit("fant ikke embedded_files i GGUF")

    cfg_idx = ef_names.index("config.json")
    cfg_start = ef_offsets[cfg_idx]
    cfg_end = ef_offsets[cfg_idx + 1] if cfg_idx + 1 < len(ef_offsets) else len(ef_data)
    if isinstance(ef_data, (bytes, bytearray)):
        ef_blob = bytes(ef_data)
    else:
        ef_blob = bytes((v & 0xFF) for v in ef_data)
    cfg_bytes = bytearray(ef_blob[cfg_start:cfg_end])
    cfg = json.loads(cfg_bytes.decode("utf-8"))

    tc = cfg.get("text_config", {})
    if len(set(per_layer)) > 1:
        print("  NB: ulike eksperttall per lag krever num_experts_per_layer; "
              "denne builden støtter bare likt antall per lag.", flush=True)
    tc["num_experts"] = max(per_layer)
    # Per-lag-antall er bare nødvendig når lagene har ulike antall.
    if len(set(per_layer)) > 1:
        tc["num_experts_per_layer"] = per_layer
    # Kompakt JSON: vi må passe inn i originalens byte-lengde.
    new_cfg_text = json.dumps(cfg, separators=(",", ":"))
    if len(new_cfg_text) > len(cfg_bytes):
        raise SystemExit(
            f"ny config.json ({len(new_cfg_text)} byte) er lengre enn originalen "
            f"({len(cfg_bytes)} byte). Prøv kompakt JSON (uten indent).")
    new_cfg = new_cfg_text.encode("utf-8")

    # Vi bygger en ny sidecar-blob. Vi lar lengden på hver fil være
    # uendret, slik at embedded_files.offsets forblir gyldige uten
    # at vi må endre dem. config.json patcher vi på plass: den nye
    # teksten skrives, og resten av den gamle filen fylles med
    # mellomrom så lengden bevares.
    #
    # Dette betyr at total blob-størrelse er identisk med originalen,
    # og dermed at header-størrelsen (og data_start) er uendret.
    new_data = bytearray()
    new_offsets = [0]
    for i, name in enumerate(ef_names):
        start = ef_offsets[i]
        end = ef_offsets[i + 1] if i + 1 < len(ef_offsets) else len(ef_data)
        if i == cfg_idx:
            original_len = end - start
            patched = new_cfg[:original_len].ljust(original_len, b" ")
            new_data += patched
        else:
            new_data += ef_blob[start:end]
        new_offsets.append(len(new_data))

    kv["audiocpp.embedded_files.offsets"] = new_offsets
    kv["audiocpp.embedded_files.data"] = list(new_data)
    print(f"\n  config.json: num_experts={max(per_layer)} "
          f"({len(cfg_bytes)} -> {len(new_cfg)} byte)", flush=True)

    # tensor_names / tensor_ranks / tensor_shapes
    #
    # Runtime-en (src/framework/assets/tensor_source.cpp) forventer:
    #   tensor_ranks  = rank per tensor (ett tall hver)
    #   tensor_shapes = ALLE dims flatt, i tensor-rekkefølge, uten padding
    # Det betyr at summen av ranks må være lik lengden på tensor_shapes.
    # Vi skriver derfor de eksakte formene, basert på de nye dimsene.
    # tensor_names / tensor_ranks / tensor_shapes
    #
    # Runtime-en (src/framework/assets/tensor_source.cpp) leser:
    #   ranks[i]  = rang for tensor i
    #   shapes[]  = ALLE dimensjoner flatt, i tensor-rekkefølge,
    #               med dim-0 (ne0) FØRST for hver tensor.
    # Summen av ranks må være lik lengden på shapes.
    #
    # Merk: originalfilens ranks-array har rank=3 for 99 tensors som
    # faktisk har rank 2, og shapes har derfor 99 ekstra verdier.
    # Vi skriver de eksakte formene — det er det runtime-en vil ha.
    orig_ranks = list(kv.get("audiocpp.tensor_ranks", []))
    orig_shapes = list(kv.get("audiocpp.tensor_shapes", []))
    orig_shape_cursor = 0

    for k in list(kv):
        if k.endswith("tensor_names"):
            kv[k] = [r.semantic(t) for t in r.tensors]
        elif k.endswith("tensor_ranks"):
            # For ikke-eksperttensorer kopierer vi originalens rank
            # (originalen har en inkonsistent rank+1 for 99 tensors, bl.a.
            # shared_expert_gate, og runtime-en er bygget for akkurat den).
            # Eksperttensorene får rank = nytt ekspertantall + 1, siden
            # dims[0] er 1 for dem.
            out = []
            for i, t in enumerate(r.tensors):
                seg_rank, _ = shape_segment(new_dims[t["name"]])
                if is_expert_tensor(r.semantic(t)):
                    out.append(seg_rank)
                else:
                    out.append(orig_ranks[i] if i < len(orig_ranks) else seg_rank)
            kv[k] = out
        elif k.endswith("tensor_shapes"):
            flat = []
            for i, t in enumerate(r.tensors):
                seg_rank, seg = shape_segment(new_dims[t["name"]])
                # Cursoren MÅ flyttes for HVER tensor, ellers blir
                # segmentene for eksperttensorene forskyvet.
                start = orig_shape_cursor
                orig_shape_cursor += orig_ranks[i] if i < len(orig_ranks) else 0
                if not is_expert_tensor(r.semantic(t)) and i < len(orig_ranks):
                    # Behold originalens segment for uendrede tensorer
                    flat.extend(orig_shapes[start:start + orig_ranks[i]])
                else:
                    flat.extend(seg)
            kv[k] = flat

    # ── Skriv header ────────────────────────────────────────────
    # Vi bygger KV-seksjonen på nytt. Alle array-elementer skrives med
    # eksakt samme type som originalen, slik at header-størrelsen blir
    # riktig og data_start havner på riktig grense.
    w = GGUFWriter(args.output)
    w.f.write(b"GGUF")
    w.f.write(struct.pack("<I", 3))
    w.f.write(struct.pack("<Q", len(r.tensors)))
    w.f.write(struct.pack("<Q", len(kv)))
    w.write_kv(kv, r.kv_types)

    tensor_info_start = w.f.tell()
    for t in r.tensors:
        # Behold det opprinnelige navnet (f.eks. "_audiocpp.436"):
        # GGUF krever navn < 64 tegn, og runtime-en mapper dem via
        # audiocpp.tensor_names.
        w._wstr(t["name"])
        dims = new_dims[t["name"]]
        w.f.write(struct.pack("<I", len(dims)))
        for d in dims:
            w.f.write(struct.pack("<Q", d))
        w.f.write(struct.pack("<I", t["type"]))
        w.f.write(struct.pack("<Q", 0))
    # Data-seksjonen MÅ ligge på en alignment-grense
    pos = w.f.tell()
    rem = pos % ALIGN
    if rem:
        w.f.write(b"\x00" * (ALIGN - rem))
    data_start = w.f.tell()

    # ── Skriv data ──────────────────────────────────────────────
    # GGUF-regel: offset[i] = offset[i-1] + GGML_PAD(nbytes[i-1], alignment)
    offsets = {}
    cursor = data_start
    print(f"\n=== Skriver {args.output} ===", flush=True)
    for idx, t in enumerate(r.tensors):
        sem = r.semantic(t)
        dims = new_dims[t["name"]]
        offsets[t["name"]] = cursor - data_start
        if dims == t["dims"]:
            data = r.read_tensor(t)
        else:
            data = slice_tensor(r, t, dims, per_layer, keep_map, sem)
        w.f.write(data)
        cursor += len(data)
        # Paddingen er RELATIV til data_start (slik ggml gjør det), ikke
        # til absolutt filposisjon. Forskjellen viser seg når
        # data_start ikke selv er 32-justert.
        rem = (cursor - data_start) % ALIGN
        if rem:
            w.f.write(b"\x00" * (ALIGN - rem))
            cursor += ALIGN - rem
        if idx % 200 == 0:
            print(f"    {idx}/{len(r.tensors)}", flush=True)

    w.f.close()
    r.f.close()

    # ── Skriv offsets tilbake ───────────────────────────────────
    # Vi har huset byte-posisjonen der tensor-infoen begynner, så vi
    # slipper å parse KV-seksjonen på nytt.
    with open(args.output, "r+b") as f:
        f.seek(tensor_info_start)
        for t in r.tensors:
            nb = struct.unpack("<Q", f.read(8))[0]; f.read(nb)
            nd = struct.unpack("<I", f.read(4))[0]
            f.read(8 * nd)
            f.read(4)
            f.write(struct.pack("<Q", offsets[t["name"]]))

    print(f"\nFerdig: {args.output}")
    print(f"  størrelse: {args.output.stat().st_size / 2**30:.2f} GiB "
          f"(fra {args.input.stat().st_size / 2**30:.2f} GiB)")


def slice_tensor(r, t, new_dims, per_layer, keep_map, sem):
    """
    Slice en ekspert- eller router-tensor med ren byte-kopiering.

    Ekspert: (ne0, ne1, 256) -> (ne0, ne1, n_keep)
      GGML: ne0 fastest, blokk 256 langs ne0.
      Rader = ne1*ne2. Gammel rad (i1, e) = i1*ne2 + e.
      Ny tensor: ny rad (i1, k) = i1*n_keep + k.
    Router: (ne0, 256) -> (ne0, n_keep)
      Rader = ne1*ne2 = 256*1. Gammel rad (e) = e.
      Ny tensor (ne0, n_keep, 1): ny rad (k) = k.
    """
    parsed = parse_semantic(sem)
    layer, kind = parsed
    is_router = kind == "router"

    ne0 = t["dims"][0]
    ne1 = t["dims"][1]
    ne2 = t["dims"][2] if len(t["dims"]) > 2 else 1
    bs, pb = BLOCK[t["type"]]
    row_bytes = (ne0 // bs) * pb

    kept = keep_map[layer]
    n_keep = len(kept)

    if is_router:
        new_ne1, new_ne2 = n_keep, 1
    else:
        new_ne1, new_ne2 = ne1, n_keep

    out = bytearray()
    for i1 in range(new_ne1):
        for i2 in range(new_ne2):
            if is_router:
                old_row = kept[i2]
            else:
                old_row = i1 * ne2 + kept[i2]
            r.f.seek(r.data_start + t["offset"] + old_row * row_bytes)
            out += r.f.read(row_bytes)
    return bytes(out)


if __name__ == "__main__":
    main()
