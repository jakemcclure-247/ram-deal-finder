"""Turns API item summaries into the feed the page reads, checks its shape and writes it safely."""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .parse import WARNING_ORDER, parse_computer, sort_warnings
from .pricing import FORMS, GENERATIONS, RESALE_FACTOR, estimate, lookup, module_sample, reference_prices

# The page drops any link or picture that doesn't start with one of these.
LINK_STARTS = ("https://www.ebay.co.uk/", "https://ebay.us/", "https://www.ebay.com/")
IMAGE_START = "https://i.ebayimg.com/"
CATEGORIES = ("laptop", "desktop", "server")

DEAL_KEYS = ["id", "title", "url", "image", "category", "condition", "location", "listedAt", "price", "shipping",
             "totalCost", "ramGb", "ramGeneration", "ramForm", "ramConfidence", "estRamValue", "estMargin",
             "warnings", "firstSeenAt", "lastSeenAt"]
FEED_KEYS = ["generatedAt", "marketplace", "currency", "affiliateLinks", "stats", "referencePrices", "deals"]
STATS_KEYS = ["listingsScanned", "memoryListingsSampled", "newDealsThisRun"]
REFERENCE_KEYS = ["generation", "form", "pricePerGb", "medianPerGb", "sampleSize"]


def iso(moment: datetime) -> str:
    moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _tidy(amount: float) -> float | int:
    """120.0 -> 120, 6.990000001 -> 6.99."""
    rounded = round(amount, 2)
    return int(rounded) if rounded == int(rounded) else rounded


def _gbp(money) -> float | None:
    if not isinstance(money, dict) or money.get("currency") != "GBP":
        return None
    try:
        value = float(money.get("value"))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _text(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _url(item: dict, affiliate: bool) -> str | None:
    """The affiliate link when there is one; otherwise the plain listing address, without tracking."""
    if affiliate:
        link = _text(item.get("itemAffiliateWebUrl"))
        if link and link.startswith(LINK_STARTS):
            return link
    legacy = str(item.get("legacyItemId") or "")
    if not legacy.isdigit():
        parts = str(item.get("itemId") or "").split("|")
        legacy = parts[1] if len(parts) > 1 else ""
    if legacy.isdigit():
        return f"https://www.ebay.co.uk/itm/{legacy}"
    link = _text(item.get("itemWebUrl"))
    return link if link and link.startswith(LINK_STARTS) else None


def memory_samples(items: list[dict]) -> list[tuple[str, str, float]]:
    samples = []
    for item in items:
        title, price = _text(item.get("title")), _gbp(item.get("price"))
        sample = module_sample(title, price) if title and price else None
        if sample:
            samples.append(sample)
    return samples


def unique(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for item in items:
        item_id = _text(item.get("itemId")) if isinstance(item, dict) else None
        if item_id and item_id not in seen:
            seen.add(item_id)
            out.append(item)
    return out


def price_cap(refs: list[dict], ram_gb: int) -> int:
    """The most a computer with this much memory could cost and still be a deal."""
    return math.ceil(RESALE_FACTOR * ram_gb * max(r["pricePerGb"] for r in refs))


def _deal(item: dict, category: str, refs: list[dict], affiliate: bool) -> dict | None:
    title, price, url = _text(item.get("title")), _gbp(item.get("price")), _url(item, affiliate)
    if not title or price is None or price <= 0 or not url:
        return None
    memory = parse_computer(title, category, item.get("conditionId"))
    if memory is None:
        return None
    priced = lookup(refs, memory.generations, memory.form)
    if priced is None:
        return None
    generation, per_gb, approximate = priced
    costs = [_gbp(o.get("shippingCost")) for o in item.get("shippingOptions") or [] if isinstance(o, dict)]
    known = [c for c in costs if c is not None]
    shipping = min(known) if known else None
    total = round(price + (shipping or 0), 2)
    value, margin = estimate(memory.ram_gb, per_gb, total)
    if margin <= 0:
        return None
    warnings = list(memory.warnings)
    if approximate:
        warnings.append("ram-price-approximate")
    if shipping is None:
        warnings.append("postage-unknown")
    image = item.get("image", {}).get("imageUrl") if isinstance(item.get("image"), dict) else None
    place = item.get("itemLocation") if isinstance(item.get("itemLocation"), dict) else {}
    return {
        "id": item["itemId"],
        "title": title,
        "url": url,
        "image": image if isinstance(image, str) and image.startswith(IMAGE_START) else None,
        "category": category,
        "condition": _text(item.get("condition")),
        "location": _text(place.get("city")) or _text(place.get("postalCode")) or _text(place.get("country")),
        "listedAt": _text(item.get("itemCreationDate")),
        "price": _tidy(price),
        "shipping": None if shipping is None else _tidy(shipping),
        "totalCost": _tidy(total),
        "ramGb": memory.ram_gb,
        "ramGeneration": generation,
        "ramForm": memory.form,
        "ramConfidence": memory.confidence,
        "estRamValue": _tidy(value),
        "estMargin": _tidy(margin),
        "warnings": sort_warnings(warnings),
    }


def build_feed(computers: list[tuple[str, dict]], memory: list[dict], previous: dict | None,
               now: datetime, affiliate: bool = False) -> dict:
    """computers: (category, item summary) pairs; memory: item summaries of memory listings.
    A deal eBay no longer returns is dropped; one seen before keeps its firstSeenAt."""
    memory = unique(memory)
    refs = reference_prices(memory_samples(memory))
    stamp = iso(now)
    first_seen = {}
    for old in (previous or {}).get("deals") or []:
        if isinstance(old, dict) and isinstance(old.get("id"), str) and _text(old.get("firstSeenAt")):
            first_seen[old["id"]] = old["firstSeenAt"]
    deals, seen = [], set()
    for category, item in computers:
        item_id = _text(item.get("itemId")) if isinstance(item, dict) else None
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        deal = _deal(item, category, refs, affiliate)
        if deal:
            deal["firstSeenAt"] = first_seen.get(item_id, stamp)
            deal["lastSeenAt"] = stamp
            deals.append(deal)
    deals.sort(key=lambda d: d["id"])
    deals.sort(key=lambda d: d["listedAt"] or "", reverse=True)
    deals.sort(key=lambda d: d["estMargin"], reverse=True)
    feed = {
        "generatedAt": stamp,
        "marketplace": "EBAY_GB",
        "currency": "GBP",
        "affiliateLinks": bool(affiliate),
        "stats": {
            "listingsScanned": len(seen),
            "memoryListingsSampled": len(memory),
            "newDealsThisRun": sum(1 for d in deals if d["id"] not in first_seen),
        },
        "referencePrices": refs,
        "deals": deals,
    }
    validate_feed(feed)
    return feed


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _time(value) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z", value))


def validate_feed(feed: dict) -> None:
    """Raises ValueError unless the feed has exactly the shape the page reads."""
    def check(ok: bool, what: str) -> None:
        if not ok:
            raise ValueError(f"Feed is not valid: {what}")

    check(list(feed) == FEED_KEYS, "top-level keys")
    check(_time(feed["generatedAt"]), "generatedAt")
    check(feed["marketplace"] == "EBAY_GB" and feed["currency"] == "GBP", "marketplace or currency")
    check(isinstance(feed["affiliateLinks"], bool), "affiliateLinks")
    check(list(feed["stats"]) == STATS_KEYS and all(isinstance(v, int) and v >= 0 for v in feed["stats"].values()), "stats")
    for ref in feed["referencePrices"]:
        check(list(ref) == REFERENCE_KEYS, "reference price keys")
        check(ref["generation"] in GENERATIONS and ref["form"] in FORMS, "reference price kind")
        check(_number(ref["pricePerGb"]) and _number(ref["medianPerGb"]) and ref["pricePerGb"] > 0, "reference price")
        check(isinstance(ref["sampleSize"], int) and ref["sampleSize"] > 0, "sampleSize")
    margins = [d.get("estMargin") for d in feed["deals"]]
    for deal in feed["deals"]:
        check(list(deal) == DEAL_KEYS, f"deal keys of {deal.get('id')}")
        check(all(isinstance(deal[k], str) and deal[k] for k in ("id", "title")), "deal id or title")
        check(deal["url"].startswith(LINK_STARTS), f"deal url {deal['url']}")
        check(deal["image"] is None or deal["image"].startswith(IMAGE_START), "deal image")
        check(deal["category"] in CATEGORIES, "deal category")
        check(all(deal[k] is None or isinstance(deal[k], str) for k in ("condition", "location")), "condition or location")
        check(deal["listedAt"] is None or _time(deal["listedAt"]), "listedAt")
        check(_number(deal["price"]) and _number(deal["totalCost"]) and _number(deal["estRamValue"]), "deal money")
        check(deal["shipping"] is None or _number(deal["shipping"]), "shipping")
        check(isinstance(deal["ramGb"], int) and deal["ramGb"] > 0, "ramGb")
        check(deal["ramGeneration"] in (*GENERATIONS, None) and deal["ramForm"] in FORMS, "memory kind")
        check(deal["ramConfidence"] in ("stated", "inferred"), "ramConfidence")
        check(_number(deal["estMargin"]) and deal["estMargin"] > 0, "estMargin")
        check(abs(deal["estRamValue"] - deal["totalCost"] - deal["estMargin"]) < 0.011, "margin arithmetic")
        check(all(w in WARNING_ORDER for w in deal["warnings"]), "warning codes")
        check(_time(deal["firstSeenAt"]) and _time(deal["lastSeenAt"]), "seen times")
    check(margins == sorted(margins, reverse=True), "deals not sorted best first")
    check(len({d["id"] for d in feed["deals"]}) == len(feed["deals"]), "duplicate deals")


def load_previous(path) -> dict | None:
    """The last feed, or None if there isn't one or it can't be read."""
    try:
        with open(path, encoding="utf-8") as handle:
            previous = json.load(handle)
    except (OSError, ValueError):
        return None
    return previous if isinstance(previous, dict) else None


def write_feed(feed: dict, path) -> None:
    """Checked, then written beside the target and moved into place: a failure leaves the old file."""
    validate_feed(feed)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".deals-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
            json.dump(feed, out, ensure_ascii=False, indent=1)
            out.write("\n")
        os.replace(temp, path)
    except BaseException:
        if os.path.exists(temp):
            os.remove(temp)
        raise


def run(client, out_path, now: datetime | None = None, log=print) -> dict:
    """Memory searches, reference prices, computer searches, feed. Raises rather than write a bad feed."""
    memory: list[dict] = []
    for search in config.MEMORY:
        items = client.search(search["q"], search["category_id"], config.MEMORY_FILTER)
        log(f"memory    {search['q']!r}: {len(items)} listings")
        memory += items
    refs = reference_prices(memory_samples(unique(memory)))
    if not refs:
        raise RuntimeError("No reference prices: too few usable memory listings came back.")
    for ref in refs:
        log(f"reference {ref['generation']} {ref['form']}: £{ref['pricePerGb']}/GB from {ref['sampleSize']} listings")
    computers: list[tuple[str, dict]] = []
    for search in config.COMPUTERS:
        filters = f"price:[1..{price_cap(refs, search['ram_gb'])}],priceCurrency:GBP,itemLocationCountry:GB"
        items = client.search(search["q"], search["category_id"], filters, config.COMPUTER_SORT)
        log(f"{search['category']:9} {search['q']!r}: {len(items)} listings")
        computers += [(search["category"], item) for item in items]
    feed = build_feed(computers, memory, load_previous(out_path), now or datetime.now(timezone.utc),
                      affiliate=bool(client.campaign_id))
    write_feed(feed, out_path)
    log(f"{len(feed['deals'])} deals ({feed['stats']['newDealsThisRun']} new) from "
        f"{feed['stats']['listingsScanned']} listings, {client.calls} API calls -> {out_path}")
    return feed
