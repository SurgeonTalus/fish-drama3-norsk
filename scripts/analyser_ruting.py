#!/usr/bin/env python3
"""
Analyser eksperthistorikken fra en norsk kjøring.

Input: filen fra --session-option fish_drama3.routing_stats_path
Format: "lag ekspert antall" per linje.

Lag 0 = første lag. For hvert lag viser vi hvor mange ulike eksperter
som ble brukt, og hvor stor andel av tilgangene topp-N dekker.

Bruk:
    python3 scripts/analyser_ruting.py routing.txt [--topp 64] [--pin pin.txt]
"""
import argparse
from collections import defaultdict
from pathlib import Path


def hoved():
    ap = argparse.ArgumentParser()
    ap.add_argument("fil")
    ap.add_argument("--topp", type=int, default=64,
                    help="hvor mange eksperter per lag som skal dekkes (og låses)")
    ap.add_argument("--pin", default=None,
                    help="skriv pin-liste til denne filen")
    ap.add_argument("--min-dekning", type=float, default=0.0,
                    help="krev minst denne andelen dekning per lag")
    args = ap.parse_args()

    per_lag = defaultdict(dict)
    for linje in Path(args.fil).read_text().splitlines():
        linje = linje.strip()
        if not linje or linje.startswith("#"):
            continue
        deler = linje.split()
        if len(deler) < 3:
            continue
        lag, ekspert, antall = int(deler[0]), int(deler[1]), int(deler[2])
        per_lag[lag][ekspert] = antall

    if not per_lag:
        print("Ingen data i filen.")
        return

    total_tilganger = sum(sum(v.values()) for v in per_lag.values())
    pin = []
    print(f"{'lag':>4} {'unike':>7} {'topp%':>7} {'topp-64 dekning':>16} {'topp-8':>7}")
    print("-" * 52)
    for lag in sorted(per_lag):
        tellinger = per_lag[lag]
        sortert = sorted(tellinger.items(), key=lambda kv: -kv[1])
        total = sum(tellinger.values())
        topp = sortert[:args.topp]
        dekning = sum(c for _, c in topp) / total if total else 0
        topp8 = sum(c for _, c in sortert[:8]) / total if total else 0
        print(f"{lag:>4} {len(tellinger):>7} {topp8 * 100:>6.1f}% "
              f"{dekning * 100:>15.1f}% {topp8 * 100:>6.1f}%")
        if dekning >= args.min_dekning:
            for ekspert, _ in topp:
                pin.append((lag, ekspert))

    unike = sum(len(v) for v in per_lag.values())
    print()
    print(f"Totalt {total_tilganger:,} eksperttilganger over {unike} "
          f"lag-ekspert-par ({unike / max(1, len(per_lag)):.0f} i snitt per lag)")
    print(f"Pin-liste: {len(pin)} eksperter "
          f"({len(pin) / max(1, len(per_lag)):.0f} per lag i snitt)")

    if args.pin:
        with open(args.pin, "w") as f:
            f.write("# lag ekspert\n")
            for lag, ekspert in pin:
                f.write(f"{lag} {ekspert}\n")
        print(f"Skrev pin-liste til {args.pin}")


if __name__ == "__main__":
    hoved()
