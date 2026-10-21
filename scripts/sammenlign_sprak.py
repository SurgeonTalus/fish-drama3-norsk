#!/usr/bin/env python3
"""
Sammenlign eksperthistorikk for to sprak: norsk mot engelsk.

Spørsmålet er om språkspesialiseringen finnes i *hvilke* eksperter
ruten bruker, selv om rutingen er bred (nesten alle 256 eksperter
i hvert lag blir brukt).

For hvert lag sammenligner vi:
  - de N mest brukte ekspertene i hvert sprak
  - hvor mye de overlapper
  - om topp-ekspertene for det ene spraket faktisk er varme i det andre

Bruk:
    python3 scripts/sammenlign_sprak.py norsk.txt engelsk.txt [--topp 64]
"""
import argparse
from collections import defaultdict
from pathlib import Path


def les(fil):
    per_lag = defaultdict(dict)
    for linje in Path(fil).read_text().splitlines():
        linje = linje.strip()
        if not linje or linje.startswith("#"):
            continue
        deler = linje.split()
        if len(deler) < 3:
            continue
        per_lag[int(deler[0])][int(deler[1])] = int(deler[2])
    return per_lag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("norsk")
    ap.add_argument("engelsk")
    ap.add_argument("--topp", type=int, default=64)
    args = ap.parse_args()

    a = les(args.norsk)
    b = les(args.engelsk)

    lag_re = sorted(set(a) | set(b))
    print(f"{'lag':>4} {'A unike':>8} {'B unike':>8} {'topp-{n} felles':>14} "
          f"{'A-dekning':>10} {'B-dekning':>10} {'overlapp':>9}")
    print("-" * 78)

    felles = []
    for lag in lag_re:
        ta = sorted(a.get(lag, {}).items(), key=lambda kv: -kv[1])[:args.topp]
        tb = sorted(b.get(lag, {}).items(), key=lambda kv: -kv[1])[:args.topp]
        sa = {e for e, _ in ta}
        sb = {e for e, _ in tb}
        snitt = sa & sb
        total_a = sum(a.get(lag, {}).values()) or 1
        total_b = sum(b.get(lag, {}).values()) or 1
        dek_a = sum(c for e, c in ta if e in snitt) / total_a
        dek_b = sum(c for e, c in tb if e in snitt) / total_b
        overlapp = len(snitt) / max(1, len(sa | sb))
        felles.append(len(snitt) / max(1, len(sa)))
        print(f"{lag:>4} {len(a.get(lag, {})):>8} {len(b.get(lag, {})):>8} "
              f"{len(snitt):>14} {dek_a * 100:>9.1f}% {dek_b * 100:>9.1}% "
              f"{overlapp * 100:>8.1f}%")

    print()
    print(f"Topp-{args.topp} overlapper i snitt: {sum(felles) / max(1, len(felles)) * 100:.1f} %")
    print("Til sammenligning: 100 % = de to språkene bruker nøyaktig samme eksperter.")
    print("~39 % = tilfeldig overlapp (256 eksperter, topp-64 av hvert).")


if __name__ == "__main__":
    main()
