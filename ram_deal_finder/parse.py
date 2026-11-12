"""Reads what a listing title says about memory. Pure functions, no network."""
from __future__ import annotations

import re
from dataclasses import dataclass

# The order warnings appear in the feed.
WARNING_ORDER = [
    "ram-size-inferred",
    "ram-type-assumed",
    "ram-type-uncertain",
    "ram-type-unknown",
    "ram-price-approximate",
    "ram-may-be-soldered",
    "untested-or-faulty",
    "postage-unknown",
]

RAM_SIZES = frozenset({2, 4, 6, 8, 12, 16, 20, 24, 32, 40, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024})
# A size the title calls memory is believed up to here; a bare "64GB" only up to the lower figure,
# because above it a bare size is almost always storage.
STATED_CAP = {"laptop": 128, "desktop": 2048, "server": 4096}
INFERRED_CAP = {"laptop": 64, "desktop": 128, "server": 1024}

# "2x16GB" -> (2, 16); "32 GB" -> (None, 32).
_SIZE = re.compile(r"(?:(?<!\d)(\d{1,2})\s*[x×*]\s*)?(?<![\d.,])(\d{1,4})\s*gb(?=ram|ddr|mem|[^a-z]|$)")

_SKIP_BEFORE = re.compile(r"(?:up\s*to|max(?:imum)?|supports?|upgrad\w+\s+to|expand\w+\s+to)\s*$")
_RAM_AFTER = re.compile(r"^[\s)\-]*(?:of\s+)?(?:ddr|ram\b|memory|mem\b|so-?dimm|dimm|l?rdimm|ecc\b|pc[345])")
_STORAGE_AFTER = re.compile(r"^[\s)\-]*(?:ssd|hdd|nvme|emmc|m\.?2\b|sata|sas\b|sshd|hard|storage|flash|disk|drive|pcie|ufs|rom\b)")
_GPU_AFTER = re.compile(r"^[\s)\-]*(?:gpu|graphics|vram|gtx|rtx|nvidia|geforce|radeon|quadro|video|gddr)")
_RAM_BEFORE = re.compile(r"(?:ram|memory|mem|ddr[345]l?)\s*[:\-=(]?\s*$")
_STORAGE_BEFORE = re.compile(r"(?:ssd|hdd|nvme|emmc|hard\s*drive|storage|sata|sas|m\.2)\s*[:\-=(]?\s*$")
_GPU_BEFORE = re.compile(
    r"(?:(?:gtx|rtx|rx|gt|quadro|radeon|geforce|nvidia|arc|mx)\s*-?\s*[a-z]?\d{3,4}\s*(?:ti|super|xt|m)?"
    r"|graphics|gpu|vram|nvidia|geforce|radeon|quadro)\s*$"
)
_LIST_GAP = re.compile(r"^\s*(?:/|,|\||\bor\b)\s*$")

_NO_RAM = re.compile(
    r"\b(?:no|without|w/o|missing|minus)\s+"
    r"(?:(?:hdd|ssd|hard\s*drives?|storage|caddy|caddies|os|psu|charger|battery|cpu|disks?|drives?)\s*(?:/|,|&|\+|or|and|nor|no)*\s*)*"
    r"(?:ram|memory)\b"
    r"|\b(?:ram|memory)\s+(?:not\s+included|removed|missing)\b"
    r"|\b0\s*gb\s+ram\b"
)
_NOT_A_COMPUTER = re.compile(r"\b(?:box\s+only|empty\s+box|bare\s?bones?|chassis\s+only|case\s+only|no\s+motherboard)\b")
_CHOOSE = re.compile(r"\b(?:choose|select|pick)\b|\bconfigur|\b(?:various|multiple)\s+spec")
_SOLDERED_CERTAIN = re.compile(r"lpddr|\bmacbook\s+air\b|\bsurface\s+(?:pro|laptop|go|book|studio)\b")
_APPLE = re.compile(r"\b(?:apple|mac|macbook|imac)\b")
_APPLE_SILICON = re.compile(r"\bm[1-4]\b")
_SOLDERED_MAYBE = re.compile(
    r"\bmacbook\b|\bx1\s+(?:carbon|yoga|nano)\b|\byoga\b|\bxps\s*13\b|\bxps\s*9[23]\d\d\b|\bzenbook\b|\bspectre\b"
    r"|\benvy\s*13\b|\bgram\b|\bswift\b|\bultrabook\b|\b2[\s-]in[\s-]1\b|\bx360\b|\bdragonfly\b|\bt14s\b|\bt4[89]0s\b"
    r"|\bx13\b|\bx280\b|\bx39[05]\b|\bmatebook\b|\bgalaxy\s+book\b|\bchromebook\b|\brazer\s+blade\s+stealth\b"
    r"|\bultra\s+[579]\b"
)
_FAULTY = re.compile(
    r"\b(?:spares?|repairs?|faulty|untested|not\s+working|non[\s-]working|for\s+parts|broken|no\s+power|no\s+display"
    r"|no\s+post|bios\s+lock(?:ed)?|dead|as[\s-]is|cracked|damaged)\b"
)
_LOW_END = re.compile(r"\b(?:celeron|atom|pentium|stream|chromebook|tablet|n\d{4})\b")
_SODIMM_DESKTOP = re.compile(
    r"\b(?:mini|micro|tiny|usff|nuc|aio|imac|dm|mff|1l)\b|\ball[\s-]in[\s-]one\b|\bthin\s+client\b"
)
_RDIMM_DESKTOP = re.compile(r"\bxeon\s+(?:e5|gold|silver|bronze|platinum)\b|\be5-?\s*\d{4}\b|\bepyc\b|\bdual\s+xeon\b")


@dataclass(frozen=True)
class Memory:
    """What a computer's title says about its memory."""

    ram_gb: int
    generations: tuple[str, ...]  # () unknown, one entry known, two = could be either
    form: str  # SODIMM | DIMM | RDIMM
    confidence: str  # stated | inferred
    warnings: tuple[str, ...]


def sort_warnings(codes) -> list[str]:
    return sorted(set(codes), key=WARNING_ORDER.index)


def _sizes(low: str) -> list[dict]:
    """Every "<n>GB" in the title with what it looks like: ram, storage, gpu, skip or plain."""
    out = []
    for m in _SIZE.finditer(low):
        before, after = low[max(0, m.start() - 24):m.start()], low[m.end():m.end() + 24]
        if _SKIP_BEFORE.search(before):
            kind = "skip"
        elif _RAM_AFTER.search(after):
            kind = "ram"
        elif _STORAGE_AFTER.search(after):
            kind = "storage"
        elif _GPU_AFTER.search(after):
            kind = "gpu"
        elif _RAM_BEFORE.search(before):
            kind = "ram"
        elif _STORAGE_BEFORE.search(before):
            kind = "storage"
        elif _GPU_BEFORE.search(before):
            kind = "gpu"
        else:
            kind = "plain"
        out.append({"gb": int(m[2]) * int(m[1] or 1), "each": int(m[2]), "mult": int(m[1]) if m[1] else None,
                    "kind": kind, "start": m.start(), "end": m.end()})
    return out


def _ram_size(low: str, category: str) -> tuple[int, str] | None:
    """(GB, stated | inferred), or None when the title gives nothing usable."""
    sizes = [s for s in _sizes(low) if s["kind"] in ("ram", "plain")]
    # "8GB/16GB/32GB RAM" is a listing with options: its price is for the smallest.
    options = set()
    for a, b in zip(sizes, sizes[1:]):
        if a["gb"] != b["gb"] and max(a["gb"], b["gb"]) <= 128 and {a["gb"], b["gb"]} <= RAM_SIZES \
                and _LIST_GAP.match(low[a["end"]:b["start"]]):
            options |= {a["gb"], b["gb"]}
    if options:
        return min(options), "inferred"
    stated = [s["gb"] for s in sizes if s["kind"] == "ram"]
    if stated:
        gb = min(stated)
        return (gb, "stated") if 2 <= gb <= STATED_CAP[category] else None
    plain = [s["gb"] for s in sizes if s["kind"] == "plain" and s["gb"] in RAM_SIZES and s["gb"] <= INFERRED_CAP[category]]
    if not plain or _LOW_END.search(low):  # a bare "32GB" on a Celeron is its eMMC storage
        return None
    return min(plain), "inferred"


def _explicit_generations(low: str) -> set[str]:
    found = {f"DDR{n}" for n in re.findall(r"(?<![a-z])ddr\s*-?\s*([345])", low)}
    return found | {f"DDR{n}" for n in re.findall(r"\bpc([345])l?\s*-?\s*\d{4,5}", low)}


def _intel(gen: int, low: str, category: str) -> tuple[str, ...]:
    if gen <= 5:
        return ("DDR3",)
    if gen == 6 and category == "laptop" and re.search(r"\b(?:t460|t560|l460|l560|x260)\b", low):
        return ("DDR3",)
    return ("DDR4",) if gen <= 11 else ("DDR4", "DDR5")


def _cpu_generations(low: str, category: str) -> tuple[str, ...]:
    """The memory generation the processor (or server model) implies; () when it says nothing."""
    m = re.search(r"\bi[3579]\s*-?\s*(\d{4,5})(?:[a-z]{1,2}\d?)?\b", low)
    if m:
        n = m[1]
        return _intel(int(n[:2]) if len(n) == 5 or n[0] == "1" else int(n[0]), low, category)
    if re.search(r"\bi[357]\s*-?\s*\d{3}[a-z]?\b", low):
        return ("DDR3",)
    if re.search(r"\bultra\s+[579]\b", low):
        return ("DDR5",)
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\s+gen", low)
    if m and 2 <= int(m[1]) <= 14:
        return _intel(int(m[1]), low, category)
    m = re.search(r"\bryzen\s*(?:[3579]\s*)?(?:pro\s*)?(\d{4})([a-z]{0,2})", low)
    if m:
        series = int(m[1][0])
        if series <= 5:
            return ("DDR4",)
        if series == 7 and (category != "desktop" or m[2] in ("u", "h", "hs", "hx")):
            return ("DDR4", "DDR5")
        return ("DDR5",)
    m = re.search(r"\be5-?\s*\d{4}l?\s*(v\d)?", low)
    if m:
        return ("DDR4",) if m[1] in ("v3", "v4") else ("DDR3",)
    m = re.search(r"\be3-?\s*\d{4}l?\s*(v\d)?", low)
    if m:
        return ("DDR4",) if m[1] in ("v5", "v6") else ("DDR3",)
    if re.search(r"\b[xel](?:5[56]|3[456])\d\d\b", low):
        return ("DDR3",)
    m = re.search(r"\b(?:bronze|silver|gold|platinum)\s*\d(\d)\d\d", low)
    if m:
        return ("DDR4",) if m[1] in "123" else ("DDR5",)
    m = re.search(r"\bepyc\s*(\d)\d{3}", low)
    if m:
        return ("DDR5",) if m[1] == "9" else ("DDR4",)
    if category == "server":
        m = re.search(r"\br[2-9]([1-6])0\b", low)  # Dell PowerEdge R620, R730, R650...
        if m:
            return ("DDR3",) if m[1] in "12" else ("DDR5",) if m[1] == "6" else ("DDR4",)
        m = re.search(r"\bg(?:en)?\s*(\d{1,2})\b", low)  # HP ProLiant Gen8, G9...
        if m and 6 <= int(m[1]) <= 11:
            return ("DDR3",) if int(m[1]) <= 8 else ("DDR5",) if int(m[1]) == 11 else ("DDR4",)
    return ()


def _generations(low: str, category: str) -> tuple[tuple[str, ...], str | None]:
    """(generations, warning code or None)."""
    explicit = _explicit_generations(low)
    if len(explicit) == 1:
        return (explicit.pop(),), None
    if explicit == {"DDR4", "DDR5"}:
        return ("DDR4", "DDR5"), "ram-type-uncertain"
    if explicit:
        return (), "ram-type-unknown"
    implied = _cpu_generations(low, category)
    if not implied:
        return (), "ram-type-unknown"
    return implied, "ram-type-assumed" if len(implied) == 1 else "ram-type-uncertain"


def _form(low: str, category: str) -> str:
    if re.search(r"so-?dimm", low):
        return "SODIMM"
    if re.search(r"\b(?:l?rdimm|registered)\b|\becc\s+reg", low):
        return "RDIMM"
    if re.search(r"\bu?dimm\b", low):
        return "DIMM"
    if category == "laptop":
        return "SODIMM"
    if category == "server":
        return "RDIMM"
    if _SODIMM_DESKTOP.search(low):
        return "SODIMM"
    return "RDIMM" if _RDIMM_DESKTOP.search(low) else "DIMM"


def parse_computer(title: str, category: str, condition_id: str | None = None) -> Memory | None:
    """The memory a laptop, desktop or server listing claims, or None if it can't be a deal:
    no memory, memory that is certainly soldered, an accessory, or a pick-your-spec listing."""
    low = " ".join(title.lower().split())
    if _NO_RAM.search(low) or _NOT_A_COMPUTER.search(low) or _CHOOSE.search(low) or _SOLDERED_CERTAIN.search(low):
        return None
    if _APPLE.search(low) and _APPLE_SILICON.search(low):
        return None
    size = _ram_size(low, category)
    if size is None:
        return None
    gb, confidence = size
    generations, type_warning = _generations(low, category)
    warnings = [type_warning] if type_warning else []
    if confidence == "inferred":
        warnings.append("ram-size-inferred")
    if _SOLDERED_MAYBE.search(low) and (category == "laptop" or "macbook" in low):
        warnings.append("ram-may-be-soldered")
    if _FAULTY.search(low) or str(condition_id or "") == "7000":
        warnings.append("untested-or-faulty")
    return Memory(gb, generations, _form(low, category), confidence, tuple(sort_warnings(warnings)))


_MODULE_REJECT = re.compile(
    r"\b(?:xeon|epyc|poweredge|proliant|optiplex|thinkcentre|thinkpad|latitude|elitebook|motherboard|cpu|ssd|hdd"
    r"|job\s*lot|joblot|lot\s+of|bundle|bulk)\b"
    r"|\b\d+\s*x\b(?!\s*\d)|\bx\s*\d+\b(?!\s*gb)"
)


def parse_module(title: str) -> tuple[str, str, int] | None:
    """(generation, form, total GB) of a memory listing, or None unless all three are clear."""
    low = " ".join(title.lower().split())
    if _FAULTY.search(low) or _MODULE_REJECT.search(low):
        return None
    generations = _explicit_generations(low)
    if len(generations) != 1:
        return None
    low = re.sub(r"non[\s-]?ecc", "nonecc", low)
    laptop = re.search(r"so-?dimm|\b(?:laptop|notebook)\b", low)
    server = re.search(r"\b(?:l?rdimm|registered|reg|server|ecc)\b|\bpc[345]l?-?\d{4,5}r\b", low)
    unbuffered = re.search(r"\b(?:udimm|unbuffered)\b", low)
    desktop = unbuffered or re.search(r"\b(?:dimm|desktop|nonecc)\b", low)
    if laptop:
        if server:
            return None
        form = "SODIMM"
    elif server:
        if unbuffered:  # ECC unbuffered: neither ordinary desktop memory nor registered
            return None
        form = "RDIMM"
    elif desktop:
        form = "DIMM"
    else:
        return None
    sizes = _sizes(low)
    kits = {s["gb"] for s in sizes if s["mult"]}
    plain = {s["gb"] for s in sizes if not s["mult"]}
    if len(kits) == 1:
        total = next(iter(kits))
        each = {s["each"] for s in sizes if s["mult"]}
        if not plain <= {total} | each:
            return None
    elif not kits and len(plain) == 1:
        total = next(iter(plain))
    else:  # "8GB 16GB 32GB": a listing with options, so the price fits none of them for sure
        return None
    if not 4 <= total <= 512:
        return None
    return generations.pop(), form, total
