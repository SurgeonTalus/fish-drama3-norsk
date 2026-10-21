#!/usr/bin/env python3
"""
oppsett.py - sett opp og konfigurer Drama 3 for din Mac.

Alt i en fil: scripts/innstillinger.json. Det er den ene stedet vi
oppdaterer naar nye resultater kommer, saa dette skriptet tar seg av
resten. Bytter du Mac, kjorer du bare:

    python3 scripts/oppsett.py --info      # hva anbefales her
    python3 scripts/oppsett.py --modeller  # modellene og hvilken passer
    python3 scripts/oppsett.py --test      # mal og finn beste innstilling
    python3 scripts/oppsett.py --installer # skriv konfigurasjonen

Krever bare Python 3 (ingen tredjepartsbiblioteker).
"""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
INNSTILLINGER = Path(__file__).resolve().parent / "innstillinger.json"
MODELLKATALOGER = [ROT / "models",
                   Path.home() / "fish_drama3_35b_exert_offloading" / "models"]


def finn_modellfil(filnavn):
    """Modellen kan ligge i modellkatalogen eller i runtime-katalogen."""
    for katalog in MODELLKATALOGER:
        kandidat = katalog / filnavn
        if kandidat.exists():
            return kandidat
    return MODELLKATALOGER[0] / filnavn
UT = ROT / "output"


# ── maskinen ───────────────────────────────────────────────────
def maskin():
    m = {}
    # RAM i byte (macOS: sysctl; Linux: /proc/meminfo)
    try:
        out = subprocess.run(["sysctl", "-n", "hw.memsize"],
                             capture_output=True, text=True, timeout=5)
        m["ram_mb"] = int(out.stdout.strip()) // (1024 * 1024)
    except Exception:
        try:
            for linje in Path("/proc/meminfo").read_text().splitlines():
                if linje.startswith("MemTotal:"):
                    m["ram_mb"] = int(linje.split()[1]) // 1024
                    break
        except Exception:
            m["ram_mb"] = 8192
    m["ram_gb"] = round(m["ram_mb"] / 1024)
    m["kjerner"] = os.cpu_count() or 4
    m["cpu"] = platform.processor() or platform.machine()
    try:
        out = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                             capture_output=True, text=True, timeout=5)
        if out.stdout.strip():
            m["cpu"] = out.stdout.strip()
    except Exception:
        pass
    m["macos"] = platform.mac_ver()[0] or platform.release()
    try:
        out = subprocess.run(["df", "-k", str(ROT)], capture_output=True,
                             text=True, timeout=5)
        linje = out.stdout.strip().splitlines()[-1].split()
        m["disk_free_gb"] = int(linje[3]) // (1024 * 1024)
    except Exception:
        m["disk_free_gb"] = 0
    return m


def last_inn():
    d = json.loads(INNSTILLINGER.read_text())
    return d


def tier(ram_gb):
    """Velg RAM-klasse. 8/12/16/24/32/64+"""
    for grense in (8, 12, 16, 24, 32, 64):
        if ram_gb <= grense:
            return str(grense)
    return "64"


def anbefaling(m, d):
    t = tier(m["ram_gb"])
    a = dict(d["anbefalinger"][t])
    a["tier"] = t
    # Plugg inn det beregnede taket for cache-størrelse
    k = d["konstanter"]
    tilgjengelig = m["ram_mb"] - 4000          # OS og programmer
    maks = int((tilgjengelig - k["overhead_mb"]) / k["peak_per_cache_mb"])
    a["beregnet_maks_cache"] = max(8, maks)
    a["malt_pa"] = d["maskin"]["ram_gb"] == m["ram_gb"]
    return a


# ── utskrift ───────────────────────────────────────────────────
def tittel(t):
    print()
    print("═" * 74)
    print(f"  {t}")
    print("═" * 74)


def vis_info(m, d):
    tittel("Drama 3 - maskinen din")
    print(f"  RAM            {m['ram_gb']} GB")
    print(f"  CPU            {m['cpu']} ({m['kjerner']} kjerner)")
    print(f"  macOS          {m['macos']}")
    print(f"  Disk (gratis)  {m['disk_free_gb']} GB")
    print(f"  Arkitektur     {platform.machine()}")
    if platform.machine() != "arm64":
        print("  ⚠  Ikke Apple Silicon. Metal-backenden krever arm64.")

    a = anbefaling(m, d)
    tittel(f"Anbefaling for {m['ram_gb']} GB (klasse {a['tier']})")
    modell = finn_modell(a["modell"], d)
    print(f"  Modell         {modell['navn']}  ({modell['størrelse_gib']} GiB)")
    print(f"                 {modell['anm']}")
    print(f"  Cache          expert_cache_size = {a['expert_cache_size']}")
    print(f"  Parallelle     expert_read_threads = {a['expert_read_threads']}")
    print(f"  Begrunnelse    {a['begrunnelse']}")
    if not a["malt_pa"]:
        print("  ⚠  Anbefalingen er ekstrapolert fra en annen maskin. "
              "Bruk --test for å måle på din egen.")
    print()
    print("  Neste steg:")
    print("     python3 scripts/oppsett.py --modeller   # se modellene")
    print("     python3 scripts/oppsett.py --test       # mål på din maskin")
    print("     python3 scripts/oppsett.py --installer  # skriv konfigurasjonen")


def finn_modell(navn, d):
    for m in d["modeller"]:
        if m["navn"] == navn:
            return m
    return d["modeller"][0]


def vis_modeller(m, d):
    tittel("Modellene")
    a = anbefaling(m, d)
    print(f"  {'modell':<14} {'fil':>7} {'kvalitet':<28} {'passer':<8} anm")
    print("  " + "─" * 96)
    for mod in d["modeller"]:
        fil = finn_modellfil(mod["fil"])
        tilstede = "ja" if fil.exists() else "nej"
        passer = "✓ anbefalt" if mod["navn"] == a["modell"] else (
            "kan" if m["ram_gb"] >= mod["min_ram_gb"] else "for liten")
        print(f"  {mod['navn']:<14} {mod['størrelse_gib']:>6.2f}G "
              f"{mod['kvalitet']:<28} {passer:<8} {mod['anm'][:44]}")
    print()
    print(f"  Anbefalt for {m['ram_gb']} GB: {a['modell']}")
    print()
    print("  Hent en modell med:")
    print(f"     huggingface-cli download {d['installasjon']['modell_repo']} \\")
    print(f"       --include '{finn_modell(a['modell'], d)['fil']}' --local-dir models")


# ── måling ─────────────────────────────────────────────────────
def kjor_modell(fil, tekst, ref_lyd, ref_tekst, cache, traader, utfil):
    bin = ROT / "bin" / "audiocpp_cli"
    if not bin.exists():
        raise SystemExit(f"Fant ikke {bin}. Se SETUP.md.")
    args = [str(bin), "--task", "clon", "--family", "fish_drama3",
            "--backend", "metal", "--mode", "offline",
            "--model-spec-override", str(ROT / "spec_override"),
            "--model", str(fil),
            "--voice-ref", str(ref_lyd),
            "--request-option", f"reference_text={ref_tekst}",
            "--text", tekst, "--max-tokens", "400", "--seed", "42",
            "--threads", "8",
            "--session-option", "fish_drama3.disk_experts=true",
            "--session-option", f"fish_drama3.expert_cache_size={cache}",
            "--session-option", f"fish_drama3.expert_read_threads={traader}",
            "--session-option", "fish_drama3.cpu_expert_layers=0",
            "--session-option", "fish_drama3.context_length=2048",
            "--session-option", "fish_drama3.codec_backend=cpu",
            "--session-option", "fish_drama3.codec_encoder_chunk_samples=65536",
            "--log", "--metrics", "--out", str(utfil)]
    utfil.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(args, capture_output=True, text=True, timeout=3600)
    tall = {}
    try:
        for linje in utfil.with_suffix(".log").read_text().splitlines():
            if "=" in linje and "metrics." in linje or "disk_experts." in linje:
                nøkkel, _, verdi = linje.partition("=")
                nøkkel = nøkkel.strip().split()[-1] if "disk_experts" in linje else nøkkel.strip()
                if nøkkel.startswith("metrics."):
                    nøkkel = nøkkel.split(".", 1)[1]
                try:
                    tall[nøkkel] = float(verdi.strip())
                except ValueError:
                    pass
    except Exception:
        pass
    return tall


def vis_test(m, d, hurtig=False):
    tittel("Bygger innstilling - maler på din maskin")
    a = anbefaling(m, d)
    modell = finn_modell(a["modell"], d)
    fil = finn_modellfil(modell["fil"])
    if not fil.exists():
        print(f"  ✗ Fant ikke modellen: {fil}")
        print(f"    Hent den med:  huggingface-cli download "
              f"{d['installasjon']['modell_repo']} --include '{modell['fil']}' "
              f"--local-dir models")
        return
    tekst = (ROT / "audio" / "testtekster.txt").read_text().splitlines()[0]
    ref_lyd = ROT / "audio" / "referanse_stemme.wav"
    ref_tekst = (ROT / "audio" / "referansetekst_8s.txt").read_text().strip()
    if not ref_lyd.exists():
        print(f"  ✗ Fant ikke referansestemmen: {ref_lyd}")
        return

    kombinasjoner = [(32, 16), (32, 8), (64, 16), (96, 16)]
    if hurtig:
        kombinasjoner = kombinasjoner[:2]
    print(f"  Modell: {modell['navn']}")
    print(f"  Tester {len(kombinasjoner)} kombinasjoner av cache og parallelle lesninger.")
    print(f"  (hver kjøring tar 3-5 minutter)")
    print()
    print(f"  {'cache':>6} {'traader':>8} {'RTF':>8} {'treff':>8} {'disk s':>9} {'wall s':>9}")
    print("  " + "─" * 54)
    resultater = []
    for cache, traader in kombinasjoner:
        print(f"  {cache:>6} {traader:>8} ...", end="\r", flush=True)
        t0 = time.time()
        tall = kjor_modell(fil, tekst, ref_lyd, ref_tekst, cache, traader,
                            UT / "test" / f"cache{cache}_tr{traader}.wav")
        rtf = tall.get("rtf", 0.0)
        treff = tall.get("cache_hits", 0) / max(1, tall.get("cache_hits", 0)
                                                   + tall.get("expert_loads", 1))
        disk = tall.get("read_ms", 0) / 1000
        wall = tall.get("wall_ms", 0) / 1000
        print(f"  {cache:>6} {traader:>8} {rtf:>8.1f} {treff * 100:>7.1f}% "
              f"{disk:>8.1f} {wall:>8.1f}")
        resultater.append({"cache": cache, "traader": traader, "rtf": rtf,
                           "treff": treff, "disk_s": disk, "wall_s": wall})
    print()
    if not resultater:
        print("  Ingen resultater.")
        return
    beste = min(resultater, key=lambda r: r["rtf"] or 1e9)
    tittel("Resultat")
    print(f"  Beste: expert_cache_size = {beste['cache']}, "
          f"expert_read_threads = {beste['traader']}")
    print(f"  RTF {beste['rtf']:.1f}")
    print()
    print("  Skriver konfigurasjonen ...")
    skriv_konfig(beste, modell, d)
    print(f"  Ferdig. Se {ROT / 'config' / 'kjore.json'}")
    print()
    print("  Neste: python3 scripts/oppsett.py --installer")


def skriv_konfig(beste, modell, d):
    cfg_dir = ROT / "config"
    cfg_dir.mkdir(exist_ok=True)
    valg = {
        "modell": modell["fil"],
        "modell_navn": modell["navn"],
        "expert_cache_size": beste["cache"],
        "expert_read_threads": beste["traader"],
        "cpu_expert_layers": 0,
        "context_length": 2048,
        "codec_backend": "cpu",
        "codec_encoder_chunk_samples": 65536,
        "rtf_malt": beste["rtf"],
        "malt_pa": platform.machine(),
        "tidspunkt": time.strftime("%Y-%m-%d %H:%M"),
        "kjent": d["installasjon"]["session_options"],
    }
    (cfg_dir / "kjore.json").write_text(json.dumps(valg, indent=2, ensure_ascii=False))
    return valg


def vis_installer(m, d):
    tittel("Installasjon og kjørekommando")
    valg = None
    kj = ROT / "config" / "kjore.json"
    if kj.exists():
        valg = json.loads(kj.read_text())
    if valg is None:
        a = anbefaling(m, d)
        modell = finn_modell(a["modell"], d)
        valg = {"modell": modell["fil"], "modell_navn": modell["navn"],
                "expert_cache_size": a["expert_cache_size"],
                "expert_read_threads": a["expert_read_threads"],
                "cpu_expert_layers": a["cpu_expert_layers"],
                "context_length": 2048,
                "codec_backend": "cpu",
                "codec_encoder_chunk_samples": 65536}

    print("  1. Hent modellen")
    print(f"     huggingface-cli download {d['installasjon']['modell_repo']} \\")
    print(f"       --include '{valg['modell']}' --local-dir models")
    print()
    print("  2. Sjekk at runtime-en er bygget med vår utvidelse")
    print(f"     bin/audiocpp_cli   (skal kjenne igjen: expert_read_threads)")
    print()
    print("  3. Kjør")
    print(f"     ./bin/audiocpp_cli --task clon --family fish_drama3 --backend metal \\")
    print(f"       --mode offline --model-spec-override ./spec_override \\")
    print(f"       --model models/{valg['modell']} \\")
    print(f"       --voice-ref audio/referanse_stemme.wav \\")
    print(f"       --request-option \"reference_text=$(cat audio/referansetekst_8s.txt)\" \\")
    print(f"       --text \"I går gikk jeg en tur langs elven.\" \\")
    print(f"       --max-tokens 400 --seed 42 --threads 8 \\")
    print(f"       --session-option fish_drama3.disk_experts=true \\")
    print(f"       --session-option fish_drama3.expert_cache_size={valg['expert_cache_size']} \\")
    print(f"       --session-option fish_drama3.expert_read_threads={valg['expert_read_threads']} \\")
    print(f"       --session-option fish_drama3.cpu_expert_layers={valg['cpu_expert_layers']} \\")
    print(f"       --session-option fish_drama3.context_length={valg['context_length']} \\")
    print(f"       --session-option fish_drama3.codec_backend={valg['codec_backend']} \\")
    print(f"       --session-option fish_drama3.codec_encoder_chunk_samples={valg['codec_encoder_chunk_samples']} \\")
    print(f"       --log --metrics --out output/tale.wav")
    print()
    print("  4. Se hva som skjedde")
    print("     grep -E 'metrics\\.(rtf|wall_ms)|disk_experts\\.(cache_hits|expert_loads|read_ms)' loggen")
    print()
    print(f"  Forventet på 16 GB: RTF rundt 17-20 med cache 96 og 16 tråder.")


def vis_status(m, d):
    tittel("Status")
    kj = ROT / "config" / "kjore.json"
    if not kj.exists():
        print("  Ingen konfigurasjon skrevet ennå. Kjør --test eller --installer.")
        return
    valg = json.loads(kj.read_text())
    for k, v in valg.items():
        print(f"  {k:<30} {v}")
    fil = finn_modellfil(valg["modell"])
    print(f"  {'modell paa disk':<30} {'ja' if fil.exists() else 'NEI'}")
    print(f"  {'runtime':<30} "
          f"{'ja' if (ROT / 'bin' / 'audiocpp_cli').exists() else 'NEI'}")


def vis_resultater(m, d):
    tittel("Alle malte resultater")
    print(f"  {'kjøring':<42} {'RTF':>7} {'treff':>7} {'disk s':>8}")
    print("  " + "─" * 68)
    for r in d["resultater"]:
        rtf = f"{r['rtf']:.1f}" if r.get("rtf") else "—"
        treff = f"{r['treff'] * 100:.1f}%" if r.get("treff") else "—"
        disk = f"{r['disk_ms'] / 1000:.1f}" if r.get("disk_ms") else "—"
        merknad = ("  " + r["merknad"]) if r.get("merknad") else ""
        print(f"  {r['kjøring']:<42} {rtf:>7} {treff:>7} {disk:>8}{merknad}")
    print()
    print(f"  Malt på: {d['maskin']['cpu']}, {d['maskin']['ram_gb']} GB, "
          f"{d['maskin']['kjerner']} kjerner, {d['maskin']['macos']}")
    print(f"  Innstillinger versjon {d['versjon']}. Oppdater "
          f"scripts/innstillinger.json naar nye resultater kommer.")


def hoved():
    ap = argparse.ArgumentParser(
        description="Sett opp Drama 3 for din Mac.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Eksempler:\n"
               "  python3 scripts/oppsett.py --info\n"
               "  python3 scripts/oppsett.py --modeller\n"
               "  python3 scripts/oppsett.py --test --hurtig\n"
               "  python3 scripts/oppsett.py --installer\n")
    ap.add_argument("--info", action="store_true", help="maskin og anbefaling")
    ap.add_argument("--modeller", action="store_true", help="modellene og anbefaling")
    ap.add_argument("--test", action="store_true", help="mal og finn beste innstilling")
    ap.add_argument("--hurtig", action="store_true", help="bare noen kombinasjoner")
    ap.add_argument("--installer", action="store_true", help="skriv konfig og kommandoer")
    ap.add_argument("--status", action="store_true", help="nvaer status")
    ap.add_argument("--resultater", action="store_true", help="alle malte resultater")
    args = ap.parse_args()

    d = last_inn()
    m = maskin()

    if args.info:
        vis_info(m, d)
    if args.modeller:
        vis_modeller(m, d)
    if args.test:
        vis_test(m, d, args.hurtig)
    if args.installer:
        vis_installer(m, d)
    if args.status:
        vis_status(m, d)
    if args.resultater:
        vis_resultater(m, d)
    if not any([args.info, args.modeller, args.test, args.installer,
                args.status, args.resultater]):
        vis_info(m, d)


if __name__ == "__main__":
    hoved()
