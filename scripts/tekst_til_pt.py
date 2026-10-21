#!/usr/bin/env python3
"""
Konverter routing-statistikk fra tekstfil til .pt-format.

Tekstformatet er "layer expert count mass" per linje, slik runtime-en skriver
det ut. Resultatet er {layer: {"mass": tensor(256), "freq": tensor(256)}},
samme form som prune_experts.py forventer.
"""
import sys
from collections import defaultdict

import torch


def main():
    if len(sys.argv) < 3:
        print("Bruk: tekst_til_pt.py <input.txt> <output.pt>", file=sys.stderr)
        raise SystemExit(1)
    src, dst = sys.argv[1], sys.argv[2]

    counts = defaultdict(lambda: defaultdict(int))
    mass = defaultdict(lambda: defaultdict(float))
    layers = set()

    with open(src) as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) != 4:
                continue
            layer, expert, count, m = int(parts[0]), int(parts[1]), int(parts[2]), float(parts[3])
            counts[layer][expert] += count
            mass[layer][expert] += m
            layers.add(layer)

    if not layers:
        raise SystemExit("ingen routing-data i " + src)

    n_experts = max(max(v) for v in counts.values()) + 1
    snapshot = {}
    for layer in sorted(layers):
        c = torch.zeros(n_experts, dtype=torch.float32)
        m = torch.zeros(n_experts, dtype=torch.float32)
        for expert, value in counts[layer].items():
            c[expert] = float(value)
        for expert, value in mass[layer].items():
            m[expert] = value
        total = m.sum()
        if total > 0:
            m = m / total
        snapshot[layer] = {"mass": m, "freq": c}

    torch.save(snapshot, dst)

    # Dekningsrapport
    print(f"Skrev {dst}: {len(snapshot)} lag, {n_experts} eksperter")
    for keep in (192, 160, 128, 100, 64):
        covs = []
        for layer in sorted(snapshot):
            sc = snapshot[layer]["mass"]
            k = min(keep, sc.numel())
            covs.append(float(sc.topk(k).values.sum()))
        print(f"  keep={keep:3d}: min={min(covs) * 100:5.1f}%  mean={sum(covs) / len(covs) * 100:5.1f}%")


if __name__ == "__main__":
    main()
