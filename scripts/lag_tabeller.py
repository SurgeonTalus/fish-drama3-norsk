#!/usr/bin/env python3
"""
Lag hastighetstabeller med eksplisitt RAM, treffrate og SSD-offloading.

Modellene måles med audio.cpp sin disk-expert-cache. Cache-størrelsen N
er antall eksperter per lag som holdes i GPU-RAM. Resten av ekspertene
ligger pa SSD og leses ved bruk.

  RAM_totalt  = fast del (alltid i RAM) + N x 40 lag x per_ekspert
  SSD_igjen   = ekspertdel_totalt - N x 40 lag x per_ekspert
"""
import json
from pathlib import Path

MOD = Path("/Users/sondre/fish_drama3_35b_exert_offloading/models")

# Målt fra filene: ekspertdel, fast del, per ekspert per lag
MODELLER = {
    "Q4_K_S": dict(fil="drama-3-backbone-4bit-experts-Q4_K_S.gguf", stor=21.78,
                   eksperter=16.88, fast=4.87, per_ekspert=1.69),
    "Q3_K_S": dict(fil="drama-3-backbone-8bit-experts-Q3_K_S.gguf", stor=18.93,
                   eksperter=12.89, fast=6.01, per_ekspert=1.29),
    "Q2_K":   dict(fil="drama-3-backbone-8bit-experts-Q2_K.gguf", stor=15.88,
                   eksperter=9.84, fast=6.01, per_ekspert=0.98),
    "Miksen": dict(fil=None, stor=18.94, eksperter=14.36, fast=4.58, per_ekspert=1.12),
}

# Målinger: modell -> cache -> (treffrate %, lest GB, RTF, sekunder)
RESULTATER = {
    ("Q4_K_S", 8):  (20.0, 111.6, 44.2, 476),
    ("Q4_K_S", 16): (30.0, 98.5, 27.4, 297),
    ("Q4_K_S", 32): (40.0, 82.1, 26.4, 287),
    ("Q4_K_S", 64): (50.0, 61.7, 21.3, 243),
    ("Q3_K_S", 32): (40.0, 62.9, 22.8, 231),
    ("Q3_K_S", 64): (50.0, 48.7, 21.5, 220),
    ("Q2_K", 32):   (38.0, 43.0, 22.2, None),
    ("Miksen", 32): (46.0, 61.3, 21.6, None),
}


def main():
    print("### Hva cache-størrelsen betyr\n")
    print("| Modell | Fil | `expert_cache_size` | Eksperter i RAM | RAM totalt | "
          "På SSD igjen | Treffrate | Lest fra SSD | **RTF** |")
    print("|---|---|---|---|---|---|---|---|---|")
    for (navn, cache), (treff, lest, rtf, _) in sorted(
            RESULTATER.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        m = MODELLER[navn]
        i_ram = cache * 40 * m["per_ekspert"] / 1024
        ram = m["fast"] + i_ram
        ssd = m["eksperter"] - i_ram
        print(f"| {navn} | {m['stor']:.2f} GiB | **{cache}** eksperter/lag | "
              f"{i_ram:.2f} GB | {ram:.1f} GB | {ssd:.2f} GiB | "
              f"{treff:.0f} % | {lest:.0f} GB | **{rtf}** |")

    print()
    print("### Modellene side om side (cache 32)\n")
    print("| Modell | Fil | RAM (eksperter) | RAM totalt | På SSD | Treffrate | "
          "Lest fra SSD | **RTF** |")
    print("|---|---|---|---|---|---|---|---|")
    for navn in ["Miksen", "Q2_K", "Q3_K_S", "Q4_K_S"]:
        m = MODELLER[navn]
        treff, lest, rtf, _ = RESULTATER[(navn, 32)]
        i_ram = 32 * 40 * m["per_ekspert"] / 1024
        ram = m["fast"] + i_ram
        ssd = m["eksperter"] - i_ram
        print(f"| {navn} | {m['stor']:.2f} GiB | {i_ram:.2f} GB | {ram:.1f} GB | "
              f"{ssd:.2f} GiB | {treff:.0f} % | {lest:.0f} GB | **{rtf}** |")


if __name__ == "__main__":
    main()
