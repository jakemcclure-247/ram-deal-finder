"""Reference prices per GB and the margin maths. Pure functions, no network."""
from __future__ import annotations

from collections import defaultdict

from .parse import parse_module

# Share of the reference price a seller keeps after fees, postage and the odd dud module.
RESALE_FACTOR = 0.8
# Fewer usable listings than this and there is no reference price for that kind of memory.
MIN_SAMPLE = 5
# Per-GB prices outside this range are mislabelled listings, not memory prices.
PER_GB_RANGE = (0.3, 30.0)

GENERATIONS = ["DDR3", "DDR4", "DDR5"]
FORMS = ["SODIMM", "DIMM", "RDIMM"]


def quantile(values: list[float], q: float) -> float:
    """Linear interpolation between the two nearest sorted values (position (n - 1) * q)."""
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (pos - lower)


def module_sample(title: str, price: float) -> tuple[str, str, float] | None:
    """(generation, form, price per GB) for one memory listing; postage is left out."""
    parsed = parse_module(title)
    if parsed is None or price <= 0:
        return None
    generation, form, gb = parsed
    per_gb = price / gb
    if not PER_GB_RANGE[0] <= per_gb <= PER_GB_RANGE[1]:
        return None
    return generation, form, per_gb


def reference_prices(samples) -> list[dict]:
    """pricePerGb is the lower quartile: what memory sells for when priced to go, not the hopeful end."""
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for generation, form, per_gb in samples:
        groups[(generation, form)].append(per_gb)
    refs = [
        {
            "generation": generation,
            "form": form,
            "pricePerGb": round(quantile(values, 0.25), 2),
            "medianPerGb": round(quantile(values, 0.5), 2),
            "sampleSize": len(values),
        }
        for (generation, form), values in groups.items()
        if len(values) >= MIN_SAMPLE
    ]
    return sorted(refs, key=lambda r: (GENERATIONS.index(r["generation"]), FORMS.index(r["form"])))


def lookup(refs: list[dict], generations: tuple[str, ...], form: str) -> tuple[str | None, float, bool] | None:
    """(generation, price per GB, approximate) for a computer's memory. Always the cheapest reading:
    two possible generations -> the cheaper; no price for this form -> the cheapest form of the same
    generation; generation unknown -> the cheapest generation. None if nothing fits."""
    if not generations:
        pool = [r for r in refs if r["form"] == form] or refs
        return (None, min(r["pricePerGb"] for r in pool), True) if pool else None
    found = []
    for generation in generations:
        same = [r for r in refs if r["generation"] == generation]
        exact = [r for r in same if r["form"] == form]
        if exact:
            found.append((exact[0]["pricePerGb"], generation, False))
        elif same:
            found.append((min(r["pricePerGb"] for r in same), generation, True))
    if not found:
        return None
    price, generation, approximate = min(found)
    return generation, price, approximate


def estimate(ram_gb: int, price_per_gb: float, total_cost: float) -> tuple[float, float]:
    """(estRamValue, estMargin)."""
    value = round(RESALE_FACTOR * ram_gb * price_per_gb, 2)
    return value, round(value - total_cost, 2)
