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
from .ebay import PAGE_SIZE
from .parse import WARNING_ORDER, parse_computer, sort_warnings
from .parts import computer_parts, drive_sample, model_query, model_sample
from .pricing import (DRIVE_KINDS, FORMS, GENERATIONS, RESALE_FACTOR, drive_prices, estimate, lookup, model_price,
                      module_sample, part_value, reference_prices)

# The page drops any link or picture that doesn't start with one of these.
LINK_STARTS = ("https://www.ebay.co.uk/", "https://ebay.us/", "https://www.ebay.com/")
IMAGE_START = "https://i.ebayimg.com/"
CATEGORIES = ("laptop", "desktop", "server")

DEAL_KEYS = ["id", "title", "url", "image", "category", "condition", "location", "listedAt", "price", "shipping",
             "totalCost", "ramGb", "ramGeneration", "ramForm", "ramConfidence", "estRamValue", "estMargin",
             "warnings", "parts", "estPartsValue", "estTotalValue", "estTotalMargin", "firstSeenAt", "lastSeenAt"]
# "deals" pay on their memory alone, which is what the page shows. "partsDeals" only pay once the other
# parts are counted. "partPrices" are the prices those parts were valued at.
FEED_KEYS = ["generatedAt", "marketplace", "currency", "affiliateLinks", "stats", "referencePrices", "deals",
             "partPrices", "partsDeals"]
PART_KINDS = (*DRIVE_KINDS, "gpu", "cpu")
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
        sample = module_sample(title, price) if title and price and not has_variations(item) else None
        if sample:
            samples.append(sample)
    return samples


def has_variations(item: dict) -> bool:
    """A listing with a spec picker: its price is the cheapest option, not the spec in its title."""
    return bool(item.get("itemGroupType"))


def unique(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for item in items:
        item_id = _text(item.get("itemId")) if isinstance(item, dict) else None
        if item_id and item_id not in seen:
            seen.add(item_id)
            out.append(item)
    return out


def price_cap(refs: list[dict], ram_gb: int, ddr5: bool = False) -> int:
    """The most a computer with this much memory could cost and still be a deal. DDR5 costs several
    times more, so it only sets the cap for the searches that ask for it."""
    wanted = [r["pricePerGb"] for r in refs if (r["generation"] == "DDR5") == ddr5]
    return math.ceil(RESALE_FACTOR * ram_gb * max(wanted or [r["pricePerGb"] for r in refs]))


def price_band(refs: list[dict], search: dict) -> tuple[int, int]:
    """(lowest, highest) price a search asks eBay for."""
    if "max_price" in search:
        return config.MIN_PRICE, search["max_price"]
    cap = price_cap(refs, search["ram_gb"], search.get("ddr5", False))
    return min(cap, max(config.MIN_PRICE, int(cap * config.FLOOR_FRACTION))), cap


def part_prices(drives: list[dict], models: dict[tuple[str, str], list[dict]]) -> dict:
    """drives: item summaries of used drives; models: (kind, model) -> the listings its lookup returned."""
    samples = []
    for item in unique(drives):
        title, price = _text(item.get("title")), _gbp(item.get("price"))
        sample = drive_sample(title) if title and price and not has_variations(item) else None
        if sample:
            samples.append((*sample, price))
    priced = []
    for (kind, model), items in models.items():
        prices = [_gbp(i.get("price")) for i in unique(items)
                  if _text(i.get("title")) and not has_variations(i) and model_sample(i["title"], kind, model)]
        found = model_price(kind, model, [p for p in prices if p])
        if found:
            priced.append(found)
    return {"drives": drive_prices(samples), "models": sorted(priced, key=lambda m: (m["kind"], m["model"]))}


def wanted_models(computers: list[tuple[str, dict]], refs: list[dict], drive_refs: list[dict], limit: int,
                  near: float) -> list[tuple[str, str]]:
    """The graphics card and processor models worth a lookup: those in the listings that fall least
    short of paying for themselves on memory and drives, nearest first."""
    short = []
    for category, item in computers:
        listing = _listing(item, category, refs, False, {"drives": drive_refs, "models": []}) if isinstance(item, dict) else None
        if listing and -listing["estTotalMargin"] <= near:
            models = [(p.kind, p.key) for p in computer_parts(listing["title"], category) if p.kind in ("gpu", "cpu")]
            if models:
                short.append((-listing["estTotalMargin"], listing["id"], models))
    wanted: list[tuple[str, str]] = []
    for _, _, models in sorted(short):
        wanted += [m for m in models if m not in wanted]
    return wanted[:limit]


NO_PARTS = {"drives": [], "models": []}


def _listing(item: dict, category: str, refs: list[dict], affiliate: bool, prices: dict = NO_PARTS) -> dict | None:
    """A computer with its memory and parts valued, whatever the margin; None if it can't be valued."""
    title, price, url = _text(item.get("title")), _gbp(item.get("price")), _url(item, affiliate)
    if not title or price is None or price <= 0 or not url or has_variations(item):
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
    parts = []
    for part in computer_parts(title, category):
        worth = part_value(part.kind, part.key, part.count, part.gb, prices["drives"], prices["models"])
        if worth:
            parts.append({"kind": part.kind, "label": part.label, "count": part.count, "estValue": _tidy(worth)})
    parts_value = round(sum(p["estValue"] for p in parts), 2)
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
        "parts": parts,
        "estPartsValue": _tidy(parts_value),
        "estTotalValue": _tidy(round(value + parts_value, 2)),
        "estTotalMargin": _tidy(round(value + parts_value - total, 2)),
    }


def build_feed(computers: list[tuple[str, dict]], memory: list[dict], previous: dict | None,
               now: datetime, affiliate: bool = False, drives: list[dict] | None = None,
               models: dict[tuple[str, str], list[dict]] | None = None) -> dict:
    """computers: (category, item summary) pairs; memory: item summaries of memory listings; drives and
    models: the listings the other parts are priced from (see part_prices).
    A deal eBay no longer returns is dropped; one seen before keeps its firstSeenAt."""
    memory = unique(memory)
    refs = reference_prices(memory_samples(memory))
    prices = part_prices(drives or [], models or {})
    stamp = iso(now)
    first_seen = {}
    for old in [*((previous or {}).get("deals") or []), *((previous or {}).get("partsDeals") or [])]:
        if isinstance(old, dict) and isinstance(old.get("id"), str) and _text(old.get("firstSeenAt")):
            first_seen[old["id"]] = old["firstSeenAt"]
    deals, parts_deals, seen = [], [], set()
    for category, item in computers:
        item_id = _text(item.get("itemId")) if isinstance(item, dict) else None
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        deal = _listing(item, category, refs, affiliate, prices)
        if deal and (deal["estMargin"] > 0 or deal["estTotalMargin"] > 0):
            deal["firstSeenAt"] = first_seen.get(item_id, stamp)
            deal["lastSeenAt"] = stamp
            (deals if deal["estMargin"] > 0 else parts_deals).append(deal)
    for found, by in ((deals, "estMargin"), (parts_deals, "estTotalMargin")):
        found.sort(key=lambda d: d["id"])
        found.sort(key=lambda d: d["listedAt"] or "", reverse=True)
        found.sort(key=lambda d: d[by], reverse=True)
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
        "partPrices": prices,
        "partsDeals": parts_deals,
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
    check(list(feed["partPrices"]) == ["drives", "models"], "partPrices keys")
    for ref in feed["partPrices"]["drives"]:
        check(list(ref) == ["kind", "pricePerGb", "medianPerGb", "sampleSize"] and ref["kind"] in DRIVE_KINDS, "drive price")
        check(_number(ref["pricePerGb"]) and ref["pricePerGb"] > 0 and isinstance(ref["sampleSize"], int), "drive price")
    for ref in feed["partPrices"]["models"]:
        check(list(ref) == ["kind", "model", "price", "median", "sampleSize"] and ref["kind"] in ("gpu", "cpu"), "model price")
        check(_number(ref["price"]) and ref["price"] > 0 and isinstance(ref["sampleSize"], int), "model price")
    margins = [d.get("estMargin") for d in feed["deals"]]
    totals = [d.get("estTotalMargin") for d in feed["partsDeals"]]
    for deal in [*feed["deals"], *feed["partsDeals"]]:
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
        check(_number(deal["estMargin"]), "estMargin")
        check(abs(deal["estRamValue"] - deal["totalCost"] - deal["estMargin"]) < 0.011, "margin arithmetic")
        check(all(w in WARNING_ORDER for w in deal["warnings"]), "warning codes")
        for part in deal["parts"]:
            check(list(part) == ["kind", "label", "count", "estValue"] and part["kind"] in PART_KINDS, "part keys")
            check(isinstance(part["label"], str) and isinstance(part["count"], int) and part["count"] > 0, "part")
            check(_number(part["estValue"]) and part["estValue"] > 0, "part value")
        check(abs(sum(p["estValue"] for p in deal["parts"]) - deal["estPartsValue"]) < 0.011, "parts arithmetic")
        check(abs(deal["estRamValue"] + deal["estPartsValue"] - deal["estTotalValue"]) < 0.011, "total value arithmetic")
        check(abs(deal["estTotalValue"] - deal["totalCost"] - deal["estTotalMargin"]) < 0.011, "total margin arithmetic")
        check(_time(deal["firstSeenAt"]) and _time(deal["lastSeenAt"]), "seen times")
    check(all(d["estMargin"] > 0 for d in feed["deals"]), "a deal must pay on its memory alone")
    check(all(d["estMargin"] <= 0 < d["estTotalMargin"] for d in feed["partsDeals"]), "a parts deal pays only with its parts")
    check(margins == sorted(margins, reverse=True), "deals not sorted best first")
    check(totals == sorted(totals, reverse=True), "parts deals not sorted best first")
    ids = [d["id"] for d in [*feed["deals"], *feed["partsDeals"]]]
    check(len(set(ids)) == len(ids), "duplicate deals")


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
        low, high = price_band(refs, search)
        filters = f"price:[{low}..{high}],priceCurrency:GBP,itemLocationCountry:GB"
        items: list[dict] = []
        for page in range(search.get("pages", 1)):
            found = client.search(search["q"], search["category_id"], filters, search.get("sort", config.COMPUTER_SORT),
                                  PAGE_SIZE, page * PAGE_SIZE)
            items += found
            if len(found) < PAGE_SIZE:  # that was the last page
                break
        log(f"{search['category']:9} {search['q']!r} £{low}-{high}: {len(items)} listings")
        computers += [(search["category"], item) for item in items]
    drives: list[dict] = []
    for search in config.DRIVES:
        items = client.search(search["q"], search["category_id"], config.MEMORY_FILTER)
        log(f"drives    {search['q']!r}: {len(items)} listings")
        drives += items
    drive_refs = part_prices(drives, {})["drives"]
    for ref in drive_refs:
        log(f"reference {ref['kind']}: £{ref['pricePerGb']}/GB from {ref['sampleSize']} listings")
    models: dict[tuple[str, str], list[dict]] = {}
    for kind, model in wanted_models(computers, refs, drive_refs, config.MAX_MODEL_LOOKUPS, config.MODEL_NEAR):
        models[(kind, model)] = client.search(model_query(kind, model), config.MODEL_CATS[kind], config.MEMORY_FILTER)
        log(f"{kind:9} {model!r}: {len(models[(kind, model)])} listings")
    feed = build_feed(computers, memory, load_previous(out_path), now or datetime.now(timezone.utc),
                      affiliate=bool(client.campaign_id), drives=drives, models=models)
    for ref in feed["partPrices"]["models"]:
        log(f"reference {ref['kind']} {ref['model']}: £{ref['price']} from {ref['sampleSize']} listings")
    write_feed(feed, out_path)
    log(f"{len(feed['deals'])} deals ({feed['stats']['newDealsThisRun']} new) and {len(feed['partsDeals'])} more counting "
        f"other parts, from "
        f"{feed['stats']['listingsScanned']} listings, {client.calls} API calls -> {out_path}")
    return feed
