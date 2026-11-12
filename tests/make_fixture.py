"""Writes tests/fixtures/ebay.json: invented listings in the shape of Browse API item summaries,
keyed "<category id>|<q>" as FixtureClient expects. Run: py -m tests.make_fixture"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent / "fixtures" / "ebay.json"
_next = [900000000000]


def module(title: str, price: float) -> dict:
    _next[0] += 1
    return {"itemId": f"v1|{_next[0]}|0", "title": title, "price": {"value": f"{price:.2f}", "currency": "GBP"},
            "condition": "Used", "conditionId": "3000"}


def computer(number: int, title: str, price: float, shipping: float | None, city: str, listed: str,
             condition: tuple[str, str] = ("Used", "3000")) -> dict:
    item = {
        "itemId": f"v1|{number}|0", "legacyItemId": str(number), "title": title,
        "itemWebUrl": f"https://www.ebay.co.uk/itm/{number}?hash=item0",
        "price": {"value": f"{price:.2f}", "currency": "GBP"},
        "condition": condition[0], "conditionId": condition[1],
        "itemLocation": {"city": city, "country": "GB"},
        "itemCreationDate": f"2026-11-12T{listed}:00.000Z",
    }
    if shipping is not None:
        item["shippingOptions"] = [{"shippingCostType": "FIXED", "shippingCost": {"value": f"{shipping:.2f}", "currency": "GBP"}}]
    return item


def build() -> dict:
    _next[0] = 900000000000
    optiplex = computer(800000000011, "Dell OptiPlex 7050 SFF i5-6500 32GB DDR4 500GB HDD", 60, None, "Manchester", "08:01")
    return {
        # 6 usable, per GB: 4.00 4.25 4.375 4.50 4.75 5.00 -> lower quartile 4.28, median 4.44
        "170083|DDR4 SODIMM": [
            module("Samsung 16GB DDR4 SODIMM PC4-2666V Laptop Memory", 64),
            module("Crucial 8GB DDR4 2400MHz SODIMM Laptop RAM", 34),
            module("Kingston 16GB (2x8GB) DDR4 SO-DIMM Kit", 70),
            module("SK Hynix 32GB DDR4 3200 SODIMM", 144),
            module("Micron 16GB DDR4 SODIMM 2666MHz notebook memory", 76),
            module("Corsair Vengeance 8GB DDR4 SODIMM", 40),
            module("Job lot 10 x 4GB DDR4 SODIMM laptop RAM", 60),
            module("DDR4 SODIMM 8GB 16GB 32GB laptop memory - choose size", 25),
        ],
        # 6 usable, per GB: 3.50 3.75 3.875 4.00 4.25 4.50 -> lower quartile 3.78, median 3.94
        "170083|DDR4 desktop memory": [
            module("Corsair Vengeance LPX 16GB (2x8GB) DDR4 3200 Desktop Memory", 56),
            module("Crucial 8GB DDR4 2666 UDIMM Desktop RAM", 30),
            module("Kingston Fury 32GB DDR4 3200MHz DIMM", 124),
            module("Samsung 16GB DDR4 PC4-2400T Desktop Memory", 64),
            module("HyperX 8GB DDR4 DIMM 2400MHz", 34),
            module("G.Skill Ripjaws V 16GB DDR4 3600 Desktop RAM", 72),
            module("Faulty Corsair 16GB DDR4 desktop memory untested", 10),
            module("16GB DDR4 RAM 2666MHz", 50),
        ],
        # Usable, but fewer than 5 of a kind: no reference price.
        "170083|DDR3 SODIMM": [
            module("Samsung 8GB DDR3L SODIMM PC3L-12800S", 10),
            module("Hynix 4GB DDR3 SODIMM laptop", 4),
            module("Crucial 16GB (2x8GB) DDR3L SODIMM", 18),
        ],
        "170083|DDR5 SODIMM": [
            module("Crucial 16GB DDR5 4800 SODIMM", 48),
            module("Samsung 32GB DDR5 5600 SODIMM Laptop", 110),
        ],
        "|DDR4 RDIMM": [
            module("Samsung 32GB DDR4 PC4-2400T-R ECC Registered RDIMM Server Memory", 40),
            module("Dell PowerEdge R730 2x Xeon E5-2680 v4 64GB DDR4 RDIMM", 180),
        ],
        "177|32GB": [
            computer(800000000001, "Dell Latitude 5490 i5-8350U 32GB RAM 256GB SSD - cracked screen, spares or repairs",
                     55, 6.99, "Leeds", "08:14", ("For parts or not working", "7000")),
            computer(800000000002, "Lenovo ThinkPad T480 i5-8250U 32GB RAM 512GB SSD", 260, 0, "Bristol", "07:30"),
            computer(800000000003, "HP Stream 11 Celeron N4020 4GB RAM 32GB eMMC", 45, 3.5, "Hull", "07:10"),
            computer(800000000004, "Apple MacBook Pro 14 M1 Pro 32GB 1TB spares or repairs", 90, 10, "London", "06:55"),
            computer(800000000005, "Dell Latitude 5590 i7-8650U No RAM No HDD (supports 32GB)", 40, 8, "Derby", "06:40"),
        ],
        "179|32GB": [
            optiplex,
            computer(800000000012, "Custom Gaming PC Ryzen 5 5600X 32GB RAM RTX 3060 12GB 1TB NVMe", 520, 25, "Cardiff", "07:50"),
            computer(800000000014, "Dell OptiPlex 3080 Micro i5-10500T 8GB/16GB/32GB RAM - choose your spec", 95, 0, "Luton", "07:20"),
        ],
        "179|64GB": [
            computer(800000000013, "HP EliteDesk 800 G4 Mini i5-8500T 64GB RAM 256GB NVMe", 120, 8, "Reading", "07:45"),
            optiplex,  # the same listing found by a second search is counted once
        ],
        "11211|64GB": [
            computer(800000000022, "HP ProLiant DL380 Gen9 2x E5-2680 v4 64GB DDR4 no HDD", 230, 20, "Slough", "06:30"),
        ],
        "11211|128GB": [
            computer(800000000021, "Dell PowerEdge R720 2x E5-2650 v2 128GB DDR3 8x 600GB SAS", 150, None, "Crewe", "06:20"),
        ],
    }


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
