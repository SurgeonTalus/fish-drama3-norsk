#!/usr/bin/env python3
"""Nøyaktig minnemåling på macOS.

`ru_maxrss` er feil signal på macOS: under minnetrykk swapper og komprimerer
kjernen sidene, så RSS faller mens prosessen fortsatt vokser. En måling som
motiverte dette viste 4,2 GB RSS mot 41 GB fysisk footprint.

`phys_footprint` er tallet Activity Monitor viser og tallet som
OOM-killeren bruker. Det leses her via `task_info(TASK_VM_INFO)` — samme
kilde som `/usr/bin/footprint` bruker.

På ikke-Darwin faller alt tilbake til RSS, som er riktig der.
"""

import ctypes
import ctypes.util
import os
import platform
import resource

IS_DARWIN = platform.system() == "Darwin"
_TASK_VM_INFO = 22


class _TaskVMInfo(ctypes.Structure):
    """struct task_vm_info fra <mach/task_info.h> (rev5)."""

    _fields_ = [
        ("virtual_size", ctypes.c_uint64),
        ("region_count", ctypes.c_int32),
        ("page_size", ctypes.c_int32),
        ("resident_size", ctypes.c_uint64),
        ("resident_size_peak", ctypes.c_uint64),
        ("device", ctypes.c_uint64),
        ("device_peak", ctypes.c_uint64),
        ("internal", ctypes.c_uint64),
        ("internal_peak", ctypes.c_uint64),
        ("external", ctypes.c_uint64),
        ("external_peak", ctypes.c_uint64),
        ("reusable", ctypes.c_uint64),
        ("reusable_peak", ctypes.c_uint64),
        ("purgeable_volatile_pmap", ctypes.c_uint64),
        ("purgeable_volatile_resident", ctypes.c_uint64),
        ("purgeable_volatile_virtual", ctypes.c_uint64),
        ("compressed", ctypes.c_uint64),
        ("compressed_peak", ctypes.c_uint64),
        ("compressed_lifetime", ctypes.c_uint64),
        ("phys_footprint", ctypes.c_uint64),
        ("min_address", ctypes.c_uint64),
        ("max_address", ctypes.c_uint64),
    ]


_COUNT = ctypes.sizeof(_TaskVMInfo) // ctypes.sizeof(ctypes.c_uint32)

_libc = None
if IS_DARWIN:
    try:
        _libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        _libc.mach_task_self.restype = ctypes.c_uint32
        _libc.mach_task_self.argtypes = []
        _libc.task_info.restype = ctypes.c_int
        _libc.task_info.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        ]
    except (OSError, AttributeError):
        _libc = None


def _rss_bytes():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if IS_DARWIN else peak * 1024)


def self_vm_info():
    if _libc is None:
        return None
    info = _TaskVMInfo()
    count = ctypes.c_uint32(_COUNT)
    status = _libc.task_info(
        _libc.mach_task_self(), ctypes.c_uint32(_TASK_VM_INFO),
        ctypes.byref(info), ctypes.byref(count))
    if status != 0:
        return None
    return {
        "physFootprintBytes": int(info.phys_footprint),
        "residentBytes": int(info.resident_size),
        "compressedBytes": int(info.compressed),
        "regionCount": int(info.region_count),
    }


def self_footprint_bytes():
    info = self_vm_info()
    return info["physFootprintBytes"] if info else _rss_bytes()


class _ProcRusage(ctypes.Structure):
    """struct rusage_info_v2 fra <sys/resource.h> - hele structen.

    `ri_phys_footprint` er det samme tallet som Activity Monitor viser for
    «Minne» og det OOM-killeren bruker. Det er den dokumenterte, offentlige
    API-en for akkurat dette tallet.

    MERK: hele structen maa vaere med. Kernelen skriver sizeof(rusage_info_v2)
    = 160 byte inn i bufferen, saa en for kort struct gir stack-korrupsjon og
    en segfault ved exit. (rusage_info_v2 har ingen ri_phys_footprint_peak -
    den finnes i v4.)
    """

    _fields_ = [
        ("ri_uuid", ctypes.c_uint8 * 16),
        ("ri_user_time", ctypes.c_uint64),
        ("ri_system_time", ctypes.c_uint64),
        ("ri_pkg_idle_wkups", ctypes.c_uint64),
        ("ri_interrupt_wkups", ctypes.c_uint64),
        ("ri_pageins", ctypes.c_uint64),
        ("ri_wired_size", ctypes.c_uint64),
        ("ri_resident_size", ctypes.c_uint64),
        ("ri_phys_footprint", ctypes.c_uint64),
        ("ri_proc_start_abstime", ctypes.c_uint64),
        ("ri_proc_exit_abstime", ctypes.c_uint64),
        ("ri_child_user_time", ctypes.c_uint64),
        ("ri_child_system_time", ctypes.c_uint64),
        ("ri_child_pkg_idle_wkups", ctypes.c_uint64),
        ("ri_child_interrupt_wkups", ctypes.c_uint64),
        ("ri_child_pageins", ctypes.c_uint64),
        ("ri_child_elapsed_abstime", ctypes.c_uint64),
        ("ri_diskio_bytesread", ctypes.c_uint64),
        ("ri_diskio_byteswritten", ctypes.c_uint64),
    ]


_libproc = None
if IS_DARWIN:
    try:
        _libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        _libproc.proc_pid_rusage.restype = ctypes.c_int
        _libproc.proc_pid_rusage.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
        ]
    except (OSError, AttributeError):
        _libproc = None


def prosess_footprint(pid):
    """Fysisk footprint for en annen prosess, i byte.

    Bruker proc_pid_rusage (RUSAGE_INFO_V2), som er den offentlige API-en for
    phys_footprint. Den eldre task_info(TASK_VM_INFO)-veien ga
    KERN_INVALID_ARGUMENT paa denne macOS-versjonen.
    """
    if _libproc is None:
        return None
    try:
        rusage = _ProcRusage()
        if _libproc.proc_pid_rusage(int(pid), 2, ctypes.byref(rusage)) != 0:
            return None
        return int(rusage.ri_phys_footprint)
    except (OSError, AttributeError, ValueError):
        return None


def prosess_sideinnlastinger(pid):
    """Antall sider prosessen har hentet inn fra swap (pageins)."""
    if _libproc is None:
        return None
    try:
        rusage = _ProcRusage()
        if _libproc.proc_pid_rusage(int(pid), 2, ctypes.byref(rusage)) != 0:
            return None
        return int(rusage.ri_pageins)
    except (OSError, AttributeError, ValueError):
        return None


def system_minne():
    """Systemets minnetilstand: fysisk, ledig, swap og swap brukt."""
    ut = {}
    side = 4096
    try:
        side = int(os.sysconf("SC_PAGE_SIZE"))
        ut["total_mb"] = int(side * os.sysconf("SC_PHYS_PAGES") / 1048576)
    except (ValueError, OSError):
        pass
    if IS_DARWIN:
        import subprocess

        def sysctl_int(navn):
            try:
                r = subprocess.run(["/usr/sbin/sysctl", "-n", navn],
                                   capture_output=True, text=True, timeout=5)
                return int(r.stdout.strip())
            except (OSError, ValueError, subprocess.SubprocessError):
                return None

        # macOS har ikke SC_AVPHYS_PAGES. Ledig minne = fri + spekulativ +
        # purgeable: de siste to kan rekvireres uten swap.
        # Husk at RSS/RU_MAXRSS er misvisende paa macOS (se modulens docstring).
        sider = 0
        for navn in ("vm.page_free_count", "vm.page_speculative_count",
                     "vm.page_purgeable_count"):
            n = sysctl_int(navn)
            if n is not None:
                sider += n
        if sider and "total_mb" in ut:
            ut["ledig_mb"] = int(sider * side / 1048576)
        # Swap.
        try:
            r = subprocess.run(["/usr/sbin/sysctl", "-n", "vm.swapusage"],
                               capture_output=True, text=True, timeout=5)
            for delte in r.stdout.split(","):
                if "total" in delte:
                    ut["swap_total_mb"] = int(delte.split("=")[1].strip().split()[0])
                elif "used" in delte:
                    ut["swap_brukt_mb"] = int(delte.split("=")[1].strip().split()[0])
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    else:
        try:
            ut["ledig_mb"] = int(side * os.sysconf("SC_AVPHYS_PAGES") / 1048576)
        except (ValueError, OSError):
            pass
    return ut
