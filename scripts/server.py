#!/usr/bin/env python3
"""Server for Drama 3 (Fish Audio) med norsk stemmekloning.

Hvorfor server og ikke CLI:

  * Modellen lastes én gang. CLI-en mapper filen på nytt for hver forespørsel,
    og det tette laget (6,06 GB) må leses fra disk hver gang.
  * Referansen bufres. Codec-kodingen og ryggrad-prefillen av referansen
    gjøres bare én gang, så etterfølgende forespørsler gjenbruker prefixen.
  * RAM-livssyklus. `frigi` frigjør modellen fra minnet med én kommando, og
    `idle_unload_ms` gjør det automatisk når serveren har vært i ro.

Bruk:

  python3 scripts/server.py start          # start serveren
  python3 scripts/server.py status         # status
  python3 scripts/server.py snak "Hei ..."  # lag lyd
  python3 scripts/server.py frigi          # frigjor RAM (modellen loseres)
  python3 scripts/server.py stop           # stopp serveren
  python3 scripts/server.py test           # mal referansecache-effekten
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INNSTILLINGER = os.path.join(ROT, "scripts", "innstillinger.json")
SERVER_KATALOG = os.path.join(ROT, "server")
KONFIG = os.path.join(SERVER_KATALOG, "drama3-server.json")
PIDFIL = os.path.join(SERVER_KATALOG, "server.pid")
LOGFIL = os.path.join(SERVER_KATALOG, "server.log")


def last_inn():
    with open(INNSTILLINGER, encoding="utf-8") as f:
        return json.load(f)


def sti(s):
    return os.path.expanduser(s)


def bygg_konfig():
    """Skriver server-konfigurasjonen fra innstillinger.json."""
    d = last_inn()
    s = d["server"]
    modell = s["modell"]
    modellfil = os.path.join(sti(s["modell_katalog"]), modell)
    if not os.path.exists(modellfil):
        raise SystemExit(f"  Modellfilen mangler: {modellfil}")
    referanse = os.path.join(ROT, "audio", "referanse_stemme.wav")
    referansetekst = open(
        os.path.join(ROT, "audio", "referansetekst_8s.txt"), encoding="utf-8"
    ).read().strip()

    cfg = {
        "host": s["host"],
        "port": s["port"],
        "backend": s["backend"],
        "threads": s["threads"],
        "lazy_load": True,
        "max_loaded_models": 1,
        # Modellen loseres fra minnet etter X ms i ro, slik at en LLM
        # kan fa minnet tilbake uten at man maa stoppe serveren.
        "idle_unload_ms": s["idle_unload_ms"],
        # Ikke last modellen hvis systemet har for lite ledig minne.
        "min_free_memory_mb": s["min_free_memory_mb"],
        "model_spec_override": sti(s["spec_override"]),
        "default_session_options": {
            "fish_drama3.disk_experts": "true",
            "fish_drama3.expert_cache_size": str(s["expert_cache_size"]),
            "fish_drama3.expert_read_threads": str(s["expert_read_threads"]),
            "fish_drama3.drop_expert_cache": str(bool(s.get("drop_expert_cache", False))).lower(),
            "fish_drama3.cpu_expert_layers": "0",
            "fish_drama3.context_length": "2048",
            "fish_drama3.codec_backend": "cpu",
            "fish_drama3.codec_encoder_chunk_samples": "65536",
        },
        "models": [
            {
                "id": "drama3",
                "family": "fish_drama3",
                "path": modellfil,
                "task": "clon",
                "mode": "offline",
                "default_voice_preset": {
                    "voice_ref": referanse,
                    "reference_text": referansetekst,
                },
            }
        ],
    }
    os.makedirs(SERVER_KATALOG, exist_ok=True)
    with open(KONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg, s


def les_pid():
    try:
        return int(open(PIDFIL).read().strip())
    except (OSError, ValueError):
        return None


def kjoerer():
    pid = les_pid()
    if not pid:
        return None
    try:
        os.kill(pid, 0)
        return pid
    except OSError:
        return None


def base_url(s=None):
    if s is None:
        s = last_inn()["server"]
    return f"http://{s['host']}:{s['port']}"


def start():
    pid = kjoerer()
    if pid:
        print(f"  Serveren kjoerer allerede (pid {pid}).")
        return 0
    cfg, s = bygg_konfig()
    binsti = sti(s["bin"])
    if not os.path.exists(binsti):
        raise SystemExit(f"  audiocpp_server mangler: {binsti}")
    os.makedirs(SERVER_KATALOG, exist_ok=True)
    log = open(LOGFIL, "a", encoding="utf-8")
    p = subprocess.Popen(
        [binsti, "--config", KONFIG, "--log"],
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    with open(PIDFIL, "w") as f:
        f.write(str(p.pid))
    url = base_url(s)
    print(f"  Starter serveren (pid {p.pid}) ... {url}")
    for _ in range(120):
        time.sleep(1)
        try:
            with urllib.request.urlopen(url + "/health", timeout=2) as r:
                r.read()
            print(f"  Klar. Modell: {s['modell']}, cache {s['expert_cache_size']}")
            print(f"  Logg: {LOGFIL}")
            return 0
        except (urllib.error.URLError, OSError):
            if p.poll() is not None:
                print("  Serveren døde ved oppstart. Siste linjer fra loggen:")
                print("  " + "\n  ".join(open(LOGFIL).readlines()[-12:]))
                return 1
    print("  Tidsavbrudd under oppstart.")
    return 1


def stop():
    pid = kjoerer()
    if not pid:
        print("  Serveren kjører ikke.")
        return 0
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(30):
        time.sleep(0.2)
        if not kjoerer():
            break
    if os.path.exists(PIDFIL):
        os.remove(PIDFIL)
    print("  Stoppet.")
    return 0


def status():
    s = last_inn()["server"]
    pid = kjoerer()
    sys.path.insert(0, os.path.join(ROT, "scripts"))
    import mac_memory
    minne = mac_memory.system_minne()
    print("  System:")
    if "total_mb" in minne:
        print(f"    fysisk {minne['total_mb']} MB, ledig {minne.get('ledig_mb', '?')} MB")
    if "swap_brukt_mb" in minne:
        print(f"    swap {minne['swap_brukt_mb']} / {minne.get('swap_total_mb', '?')} MB")
    if not pid:
        print("  Serveren kjører ikke.")
        return 1
    fp = mac_memory.prosess_footprint(pid)
    print(f"  Server (pid {pid}) på {base_url(s)}")
    if fp:
        print(f"    fysisk footprint: {fp/1048576:.0f} MB")
    try:
        with urllib.request.urlopen(base_url(s) + "/v1/models", timeout=5) as r:
            data = json.loads(r.read())
        for m in data.get("data", []):
            print(f"    modell: {m.get('id')}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"    (svar ikke: {e})")
    return 0


def frigi():
    """Frigjor modellen fra RAM uten aa stoppe serveren."""
    s = last_inn()["server"]
    url = base_url(s) + "/v1/tasks/unload_all_models"
    req = urllib.request.Request(url, data=b"{}", method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("  " + r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError) as e:
        print(f"  Kunne ikke frigjore: {e}")
        return 1
    return 0


def snak(tekst, utfil, seed=42, max_tokens=700):
    s = last_inn()["server"]
    payload = {
        "model": "drama3",
        "input": tekst,
        "seed": seed,
        "max_tokens": max_tokens,
    }
    url = base_url(s) + "/v1/audio/speech"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST"
    )
    req.add_header("Content-Type", "application/json")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
            lyd = r.read()
    except (urllib.error.URLError, OSError) as e:
        print(f"  Feil: {e}")
        return 1
    dt = time.time() - t0
    with open(utfil, "wb") as f:
        f.write(lyd)
    print(f"  Skrev {utfil} ({len(lyd)/1024:.0f} KB) paa {dt:.1f} s")
    return 0


def test():
    """Maler referansecache-effekten: samme forespørsel to ganger."""
    s = last_inn()["server"]
    tekst = "Dette er en test av referansecache."
    payload = {
        "model": "drama3",
        "input": tekst,
        "seed": 42,
        "max_tokens": 200,
    }
    url = base_url(s) + "/v1/audio/speech"
    tider = []
    for i in (1, 2, 3):
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), method="POST"
        )
        req.add_header("Content-Type", "application/json")
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=1800) as r:
                lyd = r.read()
        except (urllib.error.URLError, OSError) as e:
            print(f"  Feil: {e}")
            return 1
        dt = time.time() - t0
        tider.append(dt)
        print(f"  forespørsel {i}: {dt:.1f} s  ({len(lyd)/1024:.0f} KB)")
    if len(tider) == 3:
        forste = tider[0]
        rest = sum(tider[1:]) / 2
        print()
        print(f"  foerste: {foerste:.1f} s   resten: {rest:.1f} s")
        print(f"  referansen spaar: {foerste-rest:.1f} s ({(foerste-rest)/foerste*100:.0f} %)")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Drama 3-server for norsk stemmekloning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "kommando",
        choices=["start", "stop", "status", "snak", "frigi", "test", "konfig"],
        help="start|stop|status|snak|frigi|test|konfig",
    )
    ap.add_argument("tekst", nargs="*", help="teksten som skal leses (snak)")
    ap.add_argument("-o", "--utfil", help="hvor lyden skal ligge (snak)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-tokens", type=int, default=700)
    args = ap.parse_args()

    if args.kommando == "start":
        return start()
    if args.kommando == "stop":
        return stop()
    if args.kommando == "status":
        return status()
    if args.kommando == "frigi":
        return frigi()
    if args.kommando == "test":
        return test()
    if args.kommando == "konfig":
        cfg, s = bygg_konfig()
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
        return 0
    if args.kommando == "snak":
        tekst = " ".join(args.tekst).strip()
        if not tekst:
            raise SystemExit("  Skriv teksten, for eksempel: server.py snak \"Hei hei\"")
        utfil = args.utfil or os.path.join(ROT, "output", "server", "ut.wav")
        os.makedirs(os.path.dirname(utfil), exist_ok=True)
        return snak(tekst, utfil, args.seed, args.max_tokens)
    return 0


if __name__ == "__main__":
    sys.exit(main())
