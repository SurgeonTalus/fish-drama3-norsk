#!/usr/bin/env python3
"""
Rangere Drama 3-lag etter hvor viktige de er for norsk.

Metode: for hvert lag ser vi på routing-fordelingen over de eksperter
som faktisk ble brukt på norsk. Et lag der all norsk-rutingen går til
noen få eksperter, er et lag der de ekspertene bærer mye av
språkspesifikk informasjon — og derfor et lag som bør beholde høy
presisjon.

Vi ser på to ting per lag:
  - "konsentrasjon": hvor stor andel av routing-massen de mest brukte
    ekspertene står for. Høy = språket er spesifikt for dette laget.
  - "entropi": spredningen av routingen. Lav = konsentrert.

Lag med høy konsentrasjon og lav entropi beholdes på Q4_K.
Resten kan gå til Q2_K.
"""
import argparse
import json
import math
from pathlib import Path

import torch


def analyse(stats_path: Path, keep_threshold: float = 0.80):
    snapshot = torch.load(stats_path, weights_only=False)
    layers = sorted(snapshot)
    rows = []
    for layer in layers:
        mass = snapshot[layer]["mass"].double()
        total = float(mass.sum())
        if total <= 0:
            continue
        p = mass / total
        # Hvor mange eksperter trengs for å dekke keep_threshold av massen?
        srt = torch.sort(p, descending=True).values
        cum = torch.cumsum(srt, 0)
        n_needed = int((cum < keep_threshold).sum().item()) + 1
        coverage = float(srt[:n_needed].sum())
        # Entropi (nats), normalisert mot log(256)
        nz = p[p > 0]
        entropy = float(-(nz * nz.log()).sum())
        max_entropy = math.log(len(p))
        norm_entropy = entropy / max_entropy if max_entropy else 0.0
        # Hvor mange eksperter ble faktisk brukt i praksis?
        used = int((snapshot[layer]["freq"] > 0).sum().item())
        rows.append({
            "layer": layer,
            "n_needed": n_needed,
            "coverage": coverage,
            "norm_entropy": norm_entropy,
            "used": used,
            "top1_mass": float(srt[0]),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", type=Path, required=True)
    ap.add_argument("--keep-threshold", type=float, default=0.80)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    rows = analyse(args.stats, args.keep_threshold)
    rows.sort(key=lambda r: r["n_needed"])

    print(f"{'lag':>4} {'eksp. nok':>10} {'dekning':>9} {'entropi':>9} "
          f"{'brukt':>7} {'top1':>7}  vurdering")
    print("-" * 68)
    for r in rows:
        # Færre nødvendige eksperter = mer konsentrert = mer språkspesifikt
        mark = "→ behold Q4" if r["n_needed"] <= 48 else ("  kan gå Q2" if r["n_needed"] > 64 else "  middels")
        print(f"{r['layer']:>4} {r['n_needed']:>10} {r['coverage'] * 100:>8.1f}% "
              f"{r['norm_entropy']:>9.3f} {r['used']:>7} {r['top1_mass'] * 100:>6.1f}%  {mark}")

    keep = [r["layer"] for r in rows if r["n_needed"] <= 48]
    maybe = [r["layer"] for r in rows if 48 < r["n_needed"] <= 64]
    q2 = [r["layer"] for r in rows if r["n_needed"] > 64]

    print()
    print(f"Behold Q4_K  ({len(keep)} lag): {keep}")
    print(f"Middels      ({len(maybe)} lag): {maybe}")
    print(f"Bruk Q2_K    ({len(q2)} lag): {q2}")

    # Størrelseberegning
    # Q4_K_S: eksperter 19,89 GiB + tettt 1,89 GiB = 21,78 GiB
    # Q2_K  : eksperter 13,51 GiB + tettt 2,37 GiB = 15,88 GiB
    expert_q4 = 19.89
    expert_q2 = 13.51
    dense_q4 = 21.78 - expert_q4
    dense_q2 = 15.88 - expert_q2
    n = len(rows)
    for label, count in (("alle lag Q4", n), ("blandet (48/40)", len(keep)),
                         ("blandet (24/40)", len(keep) + len(maybe) // 2)):
        size = expert_q4 * (count / n) + expert_q2 * ((n - count) / n) + dense_q4
        print(f"  {label:20s} -> ~{size:.1f} GiB")

    if args.json_out:
        args.json_out.write_text(json.dumps({
            "keep_q4_layers": keep,
            "maybe_layers": maybe,
            "q2_layers": q2,
            "detail": rows,
        }, indent=2))
        print(f"\nSkrev {args.json_out}")


if __name__ == "__main__":
    main()
