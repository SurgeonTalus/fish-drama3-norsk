#!/usr/bin/env python3
"""
Hvor mange eksperter per lag får plass i et gitt minnebudsjett?

Modellene bygges av tre deler:
  1. ekspertene       - per lag, per ekspert, avhenger av kvantiseringen
  2. per-lag-delen    - attention + delt ekspert, skalerer med antall lag
  3. fast del         - embedding, hodet, codec, normer: uavhengig av lag

Vi måler 1-3 fra de faktiske filene, og regner ut hvor mange eksperter per
lag som får plass.
"""
from pathlib import Path

# ── Målt fra filene ────────────────────────────────────────────
# Q3_K_S: 40 lag, eksperter 12,89 GiB, rest 6,01 GiB
# Q3_K_S lag-droputing: 22 lag, eksperter 7,09 GiB, rest 5,40 GiB
Q3 = dict(
    navn="Q3_K_S (Q3_K eksperter, 8-bit dense)",
    eks_40=12.89, rest_40=6.01, eks_22=7.09, rest_22=5.40,
)
# MLX 3-bit: modell 16,91 GiB + codec 1,46 GiB. Ekspertene er 3 bit med
# group 64 (3,5 bit/element), resten er 8-bit dense med kompakt hode.
MLX = dict(
    navn="MLX 3-bit (3-bit eksperter, 8-bit dense, kompakt hode)",
    eks_40=13.12, rest_40=3.79, eks_22=10.35, rest_22=2.35,
)

BUDsjett = 12.7   # GiB


def eks_per_lag(d, lag):
    """Returnerer (GiB per ekspert per lag, fast del, GiB per-lag-dense)."""
    eks = d["eks_40"] if lag == 40 else d["eks_22"]      # GiB for ALLE lag
    rest = d["rest_40"] if lag == 40 else d["rest_22"]
    per_lag_dense = (d["rest_40"] - d["rest_22"]) / (40 - 22)
    fast = d["rest_22"] - 22 * per_lag_dense
    per_ekspert = d["eks_40"] / (40 * 256)                 # GiB per ekspert per lag
    return per_ekspert, fast, per_lag_dense


def main():
    print(f"Budsjett: {BUDsjett} GiB\n")
    for d in (Q3, MLX):
        print(f"### {d['navn']}\n")
        for lag in (40, 22):
            per_ekspert, fast, per_lag_dense = eks_per_lag(d, lag)
            fast_totalt = fast + lag * per_lag_dense
            tilgjengelig = BUDsjett - fast_totalt
            maks = int(tilgjengelig / per_ekspert / lag)
            print(f"  {lag} lag: fast del {fast:.2f} + per-lag {per_lag_dense:.3f} "
                  f"x {lag} = {fast_totalt:.2f} GiB")
            print(f"     -> eksperter tilgjengelig: {tilgjengelig:.2f} GiB "
                  f"-> **{maks} eksperter per lag** av 256 "
                  f"({maks / 256 * 100:.0f} %)")
            # Hva koster a beholde 200?
            for n in (100, 128, 200, 256):
                st = fast_totalt + n * per_ekspert * lag
                merke = "OK" if st <= BUDsjett else "for stort"
                print(f"        {n:>3} eksperter/lag -> {st:5.2f} GiB  {merke}")
        print()


if __name__ == "__main__":
    main()
