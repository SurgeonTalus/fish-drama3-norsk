#!/usr/bin/env python3
"""
Analyser eksperthistorikken: lag-fordeling, ekspert-dekning og simulert
cache-treffrate.

Vi har ekte tilgangstall per (lag, ekspert) fra en norsk kjøring. Det gir:

  1. LAG-FORDELING: er noen lag mye mer brukt enn andre?
  2. DEKNING: hvor stor andel av tilgangene ligger i de N mest brukte
     ekspertene i hvert lag?
  3. SIMULERING: hvilken treffrate får vi med en LRU-cache på N slots,
     med eller without å låse de K mest brukte ekspertene?

Simuleringen bygger en omtrentlig tilgangssekvens: for hvert lag er det
T tokens, og hvert token bruker 8 eksperter. Vi trekker de 8 uten
erstatning fra den empiriske fordelingen.

Bruk:
    python3 scripts/cache_simulering.py routing.txt
"""
import argparse
import random
from collections import defaultdict


def les(fil):
    per_lag = defaultdict(dict)
    for linje in open(fil):
        linje = linje.strip()
        if not linje or linje.startswith("#"):
            continue
        deler = linje.split()
        if len(deler) < 3:
            continue
        per_lag[int(deler[0])][int(deler[1])] = int(deler[2])
    return per_lag


def simuler(eksperter_per_lag, n_slots, n_pinned, tokens=400, seed=1):
    """Simuler LRU-cache paa en omtrentlig tilgangssekvens.

    Modellen foelger implementasjonen i disk_expert_weight_store:
    - En laast ekspert kan aldri kastes ut mens en ulast slot finnes.
    - Topp-K laaste eksperter prioriteres; naar de ikke alle faar plass,
      skjoever de hverandre i LRU-rekkefolge.
    - En laast ekspert som allerede er i cachen, treffer alltid.
    """
    rng = random.Random(seed)
    treff = 0
    totalt = 0
    for lag, tellinger in eksperter_per_lag.items():
        if not tellinger:
            continue
        eksperter = list(tellinger)
        vekter = [tellinger[e] for e in eksperter]
        topp = {e for e, _ in sorted(zip(eksperter, vekter), key=lambda kv: -kv[1])[:n_pinned]}
        # cache = liste med (ekspert, tidsstempel); None = tom slot
        cache = [None] * n_slots
        tid = [0] * n_slots
        klokke = 0
        for _ in range(tokens):
            k = min(8, len(eksperter))
            if k >= len(eksperter):
                valg = list(eksperter)
            else:
                p_ = [v / sum(vekter) for v in vekter]
                valg = list(rng.choices(eksperter, weights=p_, k=k))
            for e in valg:
                totalt += 1
                klokke += 1
                treff += 1 if e in cache else 0
                if e in cache:
                    i = cache.index(e)
                    tid[i] = klokke
                    continue
                # Velg offer: tomme foerst, saa ulaste, saaeldest laaste.
                valg_indeks = None
                for i in range(n_slots):
                    if cache[i] is None:
                        valg_indeks = i
                        break
                if valg_indeks is None:
                    ulaste = [i for i in range(n_slots) if cache[i] not in topp]
                    if ulaste:
                        valg_indeks = min(ulaste, key=lambda i: tid[i])
                    else:
                        valg_indeks = min(range(n_slots), key=lambda i: tid[i])
                cache[valg_indeks] = e
                tid[valg_indeks] = klokke
    return (treff / totalt if totalt else 0.0), treff, totalt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fil")
    ap.add_argument("--tokens", type=int, default=300)
    args = ap.parse_args()

    per_lag = les(args.fil)
    total = sum(sum(v.values()) for v in per_lag.values())

    print("=== 1. LAG-FORDELING ===")
    print(f"{'lag':>4} {'tilganger':>10} {'andel':>8} {'unike eksp':>12} "
          f"{'topp-8':>8} {'topp-32':>9} {'topp-64':>9} {'topp-128':>10}")
    print("-" * 80)
    lag_andeler = []
    for lag in sorted(per_lag):
        t = per_lag[lag]
        s = sum(t.values())
        andel = s / total
        lag_andeler.append((lag, s))
        sortert = sorted(t.values(), reverse=True)
        def dekn(k):
            return sum(sortert[:k]) / s if s else 0
        print(f"{lag:>4} {s:>10} {andel * 100:>7.2f}% {len(t):>12} "
              f"{dekn(8) * 100:>7.1f}% {dekn(32) * 100:>8.1f}% "
              f"{dekn(64) * 100:>8.1f}% {dekn(128) * 100:>9.1f}%")

    min_lag = min(lag_andeler, key=lambda x: x[1])
    maks_lag = max(lag_andeler, key=lambda x: x[1])
    print()
    print(f"Svakeste lag: {min_lag[0]} ({min_lag[1]} tilganger), "
          f"sterkeste: {maks_lag[0]} ({maks_lag[1]}). "
          f"Forhold {maks_lag[1] / max(1, min_lag[1]):.2f}x")

    print()
    print("=== 2. SIMULERT TREFFRATE (LRU) ===")
    print(f"{'slots':>6} {'uten laas':>11} " +
          " ".join(f"{'laas ' + str(k):>10}" for k in (8, 16, 32, 64)))
    for n in (8, 16, 32, 64, 96, 128):
        rad = []
        for k in (0, 8, 16, 32, 64):
            rate, _, _ = simuler(per_lag, n, k, tokens=args.tokens, seed=7)
            rad.append(rate)
        print(f"{n:>6} {rad[0] * 100:>10.1f}% " +
              " ".join(f"{r * 100:>9.1f}%" for r in rad[1:]))
    print()
    print("'laas K' = de K mest brukte ekspertene i hvert lag låses fast i cachen.")


if __name__ == "__main__":
    main()
