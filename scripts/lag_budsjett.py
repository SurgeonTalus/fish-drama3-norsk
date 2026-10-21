#!/usr/bin/env python3
"""
Hvor mange lag kan vi komme ned til med restriksjonene:
  1. Alle 10 full-attention-lag maa beholdes (runtime-en krever at
     lagtypen foelger posisjonen: lag p er full_attention iff (p+1)%4==0).
  2. Aldri to kuttede lag paa rad (aldri hopp over mer enn ett lag).

I hver gruppe paa tre linear-lag (0-2, 4-6, ..., 36-38) kan vi bare
beholde det MIDDLE laget alene, fordi de to andre ellers ville blitt
kuttet paa rad. Det gir et unikt minimalt sett: de odde lagene.

Regnestykket: modellens faste del (embedding, hode, codec, normer) er
4,65 GiB. Hvert lag koster 0,034 GiB (attention + delt ekspert) + 0,322 GiB
(256 eksperter i Q3_K) = 0,356 GiB.
"""
FAST = 4.65
PER_LAG = 0.034 + 0.322
BUDsjett = 12.7

GRUPPER = [[0, 1, 2], [4, 5, 6], [8, 9, 10], [12, 13, 14], [16, 17, 18],
           [20, 21, 22], [24, 25, 26], [28, 29, 30], [32, 33, 34],
           [36, 37, 38]]
FULL = [3, 7, 11, 15, 19, 23, 27, 31, 35, 39]


def gyldig(behold):
    sett = set(behold)
    if not set(FULL).issubset(sett):
        return False
    return all(not (i not in sett and (i + 1) not in sett) for i in range(39))


def maks_hopp(behold):
    return max(b - a for a, b in zip(behold, behold[1:]))


def størrelse(n):
    return FAST + n * PER_LAG


def main():
    print("I hver gruppe paa tre linear-lag er det bare det MIDDLE laget som")
    print("kan beholdes alene - ellers blir de to andre kuttet paa rad.\n")
    print(f"{'lag':>4} {'0,1,2':>6} {'36':>4} {'maks hopp':>10} {'størrelse':>10} "
          f"{'i 12,7 GiB':>12}  lag")
    print("-" * 96)

    valg = [
        ("minimalt (odde lag)", {1}),
        ("+ 0,1,2", {0, 1, 2}),
        ("+ 36", {0, 2}),
        ("+ 0,1,2 og 36", {0, 1, 2}),
    ]
    for navn, ekstra0 in valg:
        ekstra9 = {36, 38} if 36 in ekstra0 or navn != "minimalt (odde lag)" else {37}
        # Bygg: full + ett middle-lag per gruppe, pluss ekstra i gruppe 0 og 9
        sett = set(FULL)
        for g in GRUPPER:
            midt = g[1]
            sett.add(midt)
        # Gruppe 0: vilkjaarlig
        sett -= {g[1] for g in [GRUPPER[0]]}
        sett |= ekstra0
        # Gruppe 9
        sett -= {GRUPPER[9][1]}
        if navn == "minimalt (odde lag)":
            sett |= {37}
        else:
            sett |= ekstra9
        sett = sorted(sett)
        if not gyldig(sett):
            print(f"  (ugyldig: {navn})")
            continue
        st = størrelse(len(sett))
        print(f"{len(sett):>4} {'ja' if {0,1,2} <= set(sett) else 'nei':>6} "
              f"{'ja' if 36 in sett else 'nei':>4} {maks_hopp(sett):>10} "
              f"{st:>9.2f}G {'OK' if st <= BUDsjett else 'for stort':>12}  "
              f"{sett}")

    print()
    print("Det minimale settet er unikt: lag 1, 3, 5, ..., 39 (20 lag).")
    print("Med 0, 1, 2 i tillegg: 22 lag, 12,49 GiB - det passer i budsjettet,")
    print("men lag 36 går tapt. Med 0, 1, 2 OG 36: 23 lag, 12,85 GiB.")


if __name__ == "__main__":
    main()
