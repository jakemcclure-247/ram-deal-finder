"""Reads the other sellable parts a title names: drives, a desktop graphics card, socketed processors.
Pure functions, no network. Anything the title doesn't state plainly is left out, so the parts value
is a floor, not a guess."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .parse import _FAULTY, lot_quantity
from .pricing import DRIVE_KINDS  # nvme, ssd, hdd, sas (a SAS hard drive; a SAS SSD is priced as "ssd")

DRIVE_NAMES = {"nvme": "NVMe SSD", "ssd": "SSD", "hdd": "hard drive", "sas": "SAS hard drive"}
DRIVE_GB_RANGE = (100, 24000)  # smaller drives are worth nothing; larger is a typing error

_CAPACITY = re.compile(r"(?:(?<!\d)(\d{1,2})\s*[x×*]\s*)?(?<![\d.,])(\d{1,4}(?:\.\d{1,2})?)\s*(gb|tb)(?![a-z])")
# Groups in DRIVE_KINDS order, then the soldered kinds.
_DRIVE_WORD = re.compile(
    r"(nvme|pcie)|(ssd|solid\s+state|m\.?\s?2)|(hdd|hard\s*(?:drive|disk)s?|sata|sshd|(?:5\.4|7\.2|10|15)k\b|rpm)|(sas)"
    r"|(emmc|ufs|flash)"
)
_DRIVE_BEFORE = re.compile(r"(?:(nvme)|(ssd)|(hdd|hard\s*drive|sata)|(sas))\s*[:\-=(]?\s*$")
# "SATA SSD" is an SSD, "M.2 NVMe" is NVMe, "SAS 10K" is a SAS hard drive.
_PRECEDENCE = ["nvme", "ssd", "sas", "hdd"]
_NOT_DRIVE_AFTER = re.compile(r"^[\s)\-]*(?:of\s+)?(?:ddr|ram\b|memory|mem\b|so-?dimm|dimm|l?rdimm|ecc\b|vram|gddr|graphics|gpu)")

_MISSING = r"\b(?:no|without|w/o|missing|minus)\s+(?:(?:ram|memory|os|psu|charger|battery|cpu|cadd(?:y|ies)|%s)\s*(?:/|,|&|\+|or|and|nor|no)*\s*)*(?:%s)\b"
_HDD_WORDS = r"hdds?|hard\s*drives?|hard\s*disks?"
_SSD_WORDS = r"ssds?|nvme|m\.?\s?2"
_ANY_WORDS = r"storage|drives?|disks?"
_NO_HDD = re.compile(_MISSING % (f"{_SSD_WORDS}|{_ANY_WORDS}", _HDD_WORDS))
_NO_SSD = re.compile(_MISSING % (f"{_HDD_WORDS}|{_ANY_WORDS}", _SSD_WORDS))
_NO_DRIVES = re.compile(_MISSING % (f"{_HDD_WORDS}|{_SSD_WORDS}", _ANY_WORDS) + r"|\bcadd(?:y|ies)\s+only\b|\bdiskless\b")

_GPU = re.compile(
    r"\b(rtx|gtx|gt|rx|arc|quadro)\s*-?\s*([a-z]?\d{3,4})(?![\d])\s*(ti\s+super|ti|super|xtx|xt)?(?![a-z])"
)
_INTEL = re.compile(r"\bi([3579])\s*-?\s*(\d{4,5})([a-z]{0,2})\b")
_RYZEN = re.compile(r"\bryzen\s*([3579])\s*(?:pro\s*)?(\d{4})([a-z]{0,2}\d?[a-z]?)\b")
_XEON_E = re.compile(r"\be([357])-?\s*(\d{4})(l?)\s*(v\d)?\b")
_SCALABLE = re.compile(r"\b(bronze|silver|gold|platinum)\s*([3-9]\d{3})([a-z]?)\b")
_EPYC = re.compile(r"\bepyc\s*(\d{4}[a-z]?)\b")
_MOBILE_SUFFIX = re.compile(r"^(?:u|h|hq|hk|hs|hx|y|m|mq|mx|g\d|p|qm|xm)")
_SOLDERED_CPU = re.compile(r"\b(?:nuc|aio|imac|chromebox)\b|\ball[\s-]in[\s-]one\b|\bthin\s+client\b")
_COUNT_BEFORE = re.compile(r"(?:(?<!\d)(\d)\s*[x×]\s*|\b(dual|twin|two)\s+)(?:[\w-]+[\s-]cores?\s+)?(?:intel\s+)?(?:xeon\s+)?(?:r\s+)?$")
_COUNT_AFTER = re.compile(r"^\s*(?:cpus?\s*)?[x×]\s?(\d)\b")


@dataclass(frozen=True)
class Part:
    kind: str    # nvme | ssd | hdd | sas | gpu | cpu
    key: str     # what it is priced by: the drive kind, or the model ("RTX 3060 TI", "E5-2680 V4")
    count: int
    gb: float    # one drive's capacity; 0 for a model
    label: str


def _clean(title: str) -> str:
    return " ".join(title.lower().split())


def _size(gb: float) -> str:
    return f"{gb / 1000:g}TB" if gb >= 1000 else f"{gb:g}GB"


def drives(low: str) -> list[Part]:
    """The drives a title states with both a size and a kind. A size with no drive word is left out."""
    if _NO_DRIVES.search(low):
        return []
    found = []
    tokens = list(_CAPACITY.finditer(low))
    for index, m in enumerate(tokens):
        gb = float(m[2]) * (1000 if m[3] == "tb" else 1)
        if not DRIVE_GB_RANGE[0] <= gb <= DRIVE_GB_RANGE[1]:
            continue
        end = tokens[index + 1].start() if index + 1 < len(tokens) else len(low)
        after = low[m.end():min(end, m.end() + 28)]
        if _NOT_DRIVE_AFTER.search(after):
            continue
        word = _DRIVE_WORD.search(after) or _DRIVE_BEFORE.search(low[max(0, m.start() - 12):m.start()])
        if not word:
            continue
        groups = word.groups()
        if len(groups) == 5 and groups[4]:  # eMMC and the like are soldered
            continue
        # every drive word up to the next size, so "sata ssd" is an SSD and "m.2 nvme" is NVMe
        words = {name for g in _DRIVE_WORD.finditer(after) for name, hit in zip(DRIVE_KINDS, g.groups()) if hit}
        words |= {name for name, hit in zip(DRIVE_KINDS, groups) if hit}
        if not words:
            continue
        kind = next(k for k in _PRECEDENCE if k in words)
        found.append((kind, gb, int(m[1] or 1)))
    if _NO_HDD.search(low):
        found = [f for f in found if f[0] not in ("hdd", "sas")]
    if _NO_SSD.search(low):
        found = [f for f in found if f[0] not in ("ssd", "nvme")]
    return [Part(kind, kind, count, gb, f"{count} x {_size(gb)} {DRIVE_NAMES[kind]}" if count > 1
                 else f"{_size(gb)} {DRIVE_NAMES[kind]}") for kind, gb, count in found]


def gpu_model(low: str) -> str | None:
    """"RTX 3060 TI", "RX 6700 XT", "QUADRO P2000"... or None. Integrated graphics have no such name."""
    m = _GPU.search(low)
    if not m:
        return None
    brand, number, suffix = m[1], m[2], " ".join((m[3] or "").split())
    if brand == "rx" and not re.fullmatch(r"[4-9]\d{2,3}", number):
        return None
    if brand in ("rtx", "gtx", "gt") and not number.isdigit():
        return None
    return f"{brand} {number} {suffix}".strip().upper()


def cpu_model(low: str) -> tuple[str, int, int] | None:
    """(model, start, end) of a socketed processor: "I5-8500", "RYZEN 5 5600X", "E5-2680 V4",
    "GOLD 6248", "EPYC 7302". Laptop chips (U, H...) are soldered, so None."""
    m = _INTEL.search(low)
    if m:
        return None if _MOBILE_SUFFIX.match(m[3]) else (f"I{m[1]}-{m[2]}{m[3].upper()}", m.start(), m.end())
    m = _RYZEN.search(low)
    if m:
        return None if _MOBILE_SUFFIX.match(m[3]) else (f"RYZEN {m[1]} {m[2]}{m[3].upper()}", m.start(), m.end())
    m = _XEON_E.search(low)
    if m:
        return (f"E{m[1]}-{m[2]}{m[3].upper()}" + (f" {m[4].upper()}" if m[4] else ""), m.start(), m.end())
    m = _SCALABLE.search(low)
    if m:
        return (f"{m[1].upper()} {m[2]}{m[3].upper()}", m.start(), m.end())
    m = _EPYC.search(low)
    if m:
        return (f"EPYC {m[1].upper()}", m.start(), m.end())
    return None


def _cpu_count(low: str, start: int, end: int) -> int:
    m = _COUNT_BEFORE.search(low[max(0, start - 24):start])
    if m:
        return int(m[1]) if m[1] else 2
    m = _COUNT_AFTER.search(low[end:end + 10])
    return int(m[1]) if m else 1


def computer_parts(title: str, category: str) -> list[Part]:
    """Drives in any computer; a graphics card in a desktop; processors in a desktop or server.
    In a job lot every count is multiplied by the number of computers."""
    low = _clean(title)
    lot = lot_quantity(low)
    parts = [p if lot == 1 else Part(p.kind, p.key, p.count * lot, p.gb, f"{p.count * lot} x {_size(p.gb)} {DRIVE_NAMES[p.kind]}")
             for p in drives(low)]
    if category == "desktop":
        model = gpu_model(low)
        if model:
            parts.append(Part("gpu", model, lot, 0, model if lot == 1 else f"{lot} x {model}"))
    if category in ("desktop", "server") and not _SOLDERED_CPU.search(low):
        cpu = cpu_model(low)
        if cpu:
            count = min(_cpu_count(low, cpu[1], cpu[2]), 8) * lot
            parts.append(Part("cpu", cpu[0], count, 0, cpu[0] if count == 1 else f"{count} x {cpu[0]}"))
    return parts


def model_query(kind: str, key: str) -> str:
    """What to search eBay for to price a model."""
    return "Xeon " + key if kind == "cpu" and re.match(r"E[357]-|GOLD|SILVER|BRONZE|PLATINUM", key) else key


_LOT_WORDS = re.compile(r"\b\d+\s*[x×]\b|\b[x×]\s*\d+\b|\bjob\s?lot|\blot\s+of\b|\bbundle\b|\bcombo\b|\bpair\b|\bmatched\b|\btray\b")
_DRIVE_REJECT = re.compile(
    r"\b(?:external|portable|usb|enclosure|caddy\s+only|adapter|adaptor|cable|nas\b|laptop\s+with|pc\b|desktop\s+pc|server\s+with"
    r"|cloned?|windows|playstation|ps[345]|xbox|cctv|dvr)\b"
)
_CPU_REJECT = re.compile(
    r"\b(?:motherboard|mainboard|board|cooler|heatsink|fan|pc|server|workstation|laptop|tower|sff|optiplex|prodesk"
    r"|elitedesk|thinkcentre|poweredge|proliant|ram|ddr[345])\b"
)
_GPU_REJECT = re.compile(
    r"\b(?:pc|desktop|laptop|notebook|tower|water\s?block|backplate|cooler|fan|fans|shroud|heatsink|box\s+only|empty\s+box"
    r"|bracket|riser|mining\s+rig|egpu|i[3579]|ryzen|ssd|hdd)\b"
)


def drive_sample(title: str) -> tuple[str, float] | None:
    """(kind, GB) of a listing for one bare drive, or None unless both are clear."""
    low = _clean(title)
    if _FAULTY.search(low) or _LOT_WORDS.search(low) or _DRIVE_REJECT.search(low):
        return None
    sizes = {float(m[2]) * (1000 if m[3] == "tb" else 1) for m in _CAPACITY.finditer(low) if not m[1]}
    if len(sizes) != 1 or any(m[1] for m in _CAPACITY.finditer(low)):
        return None
    gb = sizes.pop()
    words = {name for g in _DRIVE_WORD.finditer(low) for name, hit in zip(DRIVE_KINDS, g.groups()) if hit}
    if not words or not DRIVE_GB_RANGE[0] <= gb <= DRIVE_GB_RANGE[1]:
        return None
    if "sas" in words and words & {"ssd", "nvme"}:  # SAS SSDs cost more than the SATA ones they'd be filed with
        return None
    return next(k for k in _PRECEDENCE if k in words), gb


def model_sample(title: str, kind: str, key: str) -> bool:
    """Whether a listing is for exactly one of this model and nothing else."""
    low = _clean(title)
    if _FAULTY.search(low) or _LOT_WORDS.search(low):
        return False
    if kind == "gpu":
        return gpu_model(low) == key and not _GPU_REJECT.search(low)
    cpu = cpu_model(low)
    return bool(cpu) and cpu[0] == key and not _CPU_REJECT.search(low)
