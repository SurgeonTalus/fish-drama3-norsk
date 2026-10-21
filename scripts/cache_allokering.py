#!/usr/bin/env python3
"""
Simuler cache-allokering: uniformt mot ujevnt, og ulik laas-straategi.

Sporsmaalet: er de flate tidlige lagene (som bruker ~alle 256 eksperter)
viktigere aa loese, eller er de saa flate at LRU er ubrukelig der?

Vi simulerer med implementasjonens eviction-regel:
  - laaste eksperter kan ikke kastes ut saa lenge en ulast slot finnes
  - naar de laaste ikke faar plass, skjoever de hverandre i LRU-rekkefolge
  - treff = eksperten ligger i cachen

Bruk:
    python3 scripts/cache_allokering.py routing.txt
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
        d = linje.split()
        if len(d) < 3:
            continue
        per_lag[int(d[0])][int(d[1])] = int(d[2])
    return per_lag


def simuler_lag(tellinger, n_slots, n_pinned, tokens, rng):
    """Simuler ett lag. Returnerer (treff, totalt)."""
    eksperter = list(tellinger)
    vekter = [tellinger[e] for e in eksperter]
    topp = {e for e, _ in sorted(zip(eksperter, vekter), key=lambda kv: -kv[1])[:n_pinned]}
    cache = [None] * n_slots
    tid = [0] * n_slots
    klokke = 0
    treff = 0
    totalt = 0
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
            if e in cache:
                treff += 1
                tid[cache.index(e)] = klokke
                continue
            valg_indeks = None
            for i in range(n_slots):
                if cache[i] is None:
                    valg_indeks = i
                    break
            if valg_indeks is None:
                ulaste = [i for i in range(n_slots) if cache[i] not in topp]
                valg_indeks = (min(ulaste, key=lambda i: tid[i]) if ulaste
                               else min(range(n_slots), key=lambda i: tid[i]))
            cache[valg_indeks] = e
            tid[valg_indeks] = klokke
    return treff, totalt


def kjoer(per_lag, slots_per_lag, pinned_per_lag, tokens, seed=11):
    rng = random.Random(seed)
    treff = 0
    totalt = 0
    for lag, t in per_lag.items():
        if not t:
            continue
        a, b = simuler_lag(t, slots_per_lag.get(lag, 32), pinned_per_lag.get(lag, 0), tokens, rng)
        treff += a
        totalt += b
    return treff / totalt if totalt else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fil")
    ap.add_argument("--tokens", type=int, default=250)
    ap.add_argument("--budsjett", type=int, default=32,
                    help="gjennomsnittlige slots per lag")
    args = ap.parse_args()

    per_lag = les(args.fil)
    lagene = sorted(per_lag)
    n = len(lagene)
    budsjett = args.budsjett * n

    def flat(lag):
        """Hvor flat er laget: andel av tilgangene i de 32 varmeste."""
        t = per_lag[lag]
        s = sorted(t.values(), reverse=True)
        return sum(s[:32]) / sum(s)

    # ── 1. Uniform fordeling, ulik laas-strategi ──────────────────
    print("=== 1. LÅS-STRATEGI (uniformt antall slots) ===")
    print(f"{'slots/lag':>10} {'uten laas':>11} {'laas kun 0-19':>15} "
          f"{'laas kun 20-39':>16} {'laas alle':>11}")
    for slots in (16, 32, 64, 96):
        u = {l: slots for l in lagene}
        bare_tidlig = {l: (slots if l < 20 else 0) for l in lagene}
        bare_sen = {l: (slots if l >= 20 else 0) for l in lagene}
        alle = {l: slots for l in lagene}
        print(f"{slots:>10} {kjoer(per_lag, u, {l: 0 for l in lagene}, args.tokens) * 100:>10.1f}% "
              f"{kjoer(per_lag, u, bare_tidlig, args.tokens) * 100:>14.1f}% "
              f"{kjoer(per_lag, u, bare_sen, args.tokens) * 100:>15.1f}% "
              f"{kjoer(per_lag, u, alle, args.tokens) * 100:>10.1f}%")

    # ── 2. Ujevn allokering: flere slots til konsentrerte lag ─────
    print()
    print("=== 2. UJEVN ALLOKERING (samme RAM, flere slots til sene lag) ===")
    print("Strategi: lag 0-9 faar halvparten sa mange slots som lag 30-39,")
    print("           lag 10-29 faar det gjennomsnittlige.")
    print(f"{'budsjett/lag':>12} {'uniformt':>10} {'ujevnt':>9} {'forbedring':>11}")
    for b in (16, 32, 64):
        total_ram = b * n
        uniformt = {l: b for l in lagene}
        # Beholder totalt antall slots, men flytter noen fra flate til konsentrerte lag
        ujevnt = {}
        for l in lagene:
            if l < 10:
                ujevnt[l] = max(8, b - b // 2)
            elif l < 30:
                ujevnt[l] = b
            else:
                ujevnt[l] = b + b // 2
        # Korriger til samme total
        diff = sum(ujevnt.values()) - total_ram
        ujevnt[0] = max(8, ujevnt[0] - diff)
        r1 = kjoer(per_lag, uniformt, {l: 0 for l in lagene}, args.tokens)
        r2 = kjoer(per_lag, ujevnt, {l: 0 for l in lagene}, args.tokens)
        print(f"{b:>12} {r1 * 100:>9.1f}% {r2 * 100:>8.1f}% {(r2 - r1) * 100:>+10.1f}")

    # ── 3. Hvor flat er hvert lag? ────────────────────────────────
    print()
    print("=== 3. FLATNESS PER LAG (topp-32 andel) ===")
    for l in lagene:
        t = per_lag[lag] if False else per_lag[l]
        s = sorted(t.values(), reverse=True)
        print(f"  lag {l:>2}: {sum(s[:32]) / sum(s) * 100:>5.1f}%  "
              f"({len(t)} unike eksperter)", end="   " if l % 3 == 2 else "\n")
    print()


if __name__ == "__main__":
    main()
