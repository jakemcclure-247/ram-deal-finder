"""The other parts a title names, and what they are priced at. Expectations worked out by hand."""
from __future__ import annotations

import pytest

from ram_deal_finder.parts import computer_parts, drive_sample, model_query, model_sample
from ram_deal_finder.pricing import drive_prices, model_price, part_value


def found(title, category):
    return [(p.kind, p.key, p.count, p.gb, p.label) for p in computer_parts(title, category)]


@pytest.mark.parametrize("title,category,expected", [
    # eight SAS hard drives and two processors
    ("Dell PowerEdge R730 2x E5-2680 v4 256GB RAM 8x 1.2TB SAS 10K", "server",
     [("sas", "sas", 8, 1200, "8 x 1.2TB SAS hard drive"), ("cpu", "E5-2680 V4", 2, 0, "2 x Xeon E5-2680 v4")]),
    # "no HDD" leaves the SSDs alone
    ("HP ProLiant DL380 Gen9 2x Xeon E5-2690v3 128GB DDR4 2x 480GB SSD no HDD", "server",
     [("ssd", "ssd", 2, 480, "2 x 480GB SSD"), ("cpu", "E5-2690 V3", 2, 0, "2 x Xeon E5-2690 v3")]),
    ("HPE DL380 Gen10 Server | Dual Gold 6230 | 512GB RAM | 4TB NVMe", "server",
     [("nvme", "nvme", 1, 4000, "4TB NVMe SSD"), ("cpu", "GOLD 6230", 2, 0, "2 x Xeon Gold 6230")]),
    # the graphics card's own 8GB is not a drive; M.2 NVMe is NVMe; a bare "2TB SATA" is a hard drive
    ("HP Z440 E5-1620 v4 32GB RAM 512GB M.2 NVMe 2TB SATA GTX 1070 8GB", "desktop",
     [("nvme", "nvme", 1, 512, "512GB NVMe SSD"), ("hdd", "hdd", 1, 2000, "2TB hard drive"),
      ("gpu", "GTX 1070", 1, 0, "GTX 1070"), ("cpu", "E5-1620 V4", 1, 0, "Xeon E5-1620 v4")]),
    ("Gaming PC Ryzen 5 5600X 32GB RAM RTX 3060 Ti 8GB 1TB NVMe", "desktop",
     [("nvme", "nvme", 1, 1000, "1TB NVMe SSD"), ("gpu", "RTX 3060 TI", 1, 0, "RTX 3060 Ti"),
      ("cpu", "RYZEN 5 5600X", 1, 0, "Ryzen 5 5600X")]),
    # a laptop's processor and graphics are soldered: only the drive counts
    ("Dell Latitude 5490 i5-8350U 32GB RAM 256GB SSD GTX 1050", "laptop", [("ssd", "ssd", 1, 256, "256GB SSD")]),
    # a size with no drive word beside it is not counted
    ("Lenovo ThinkPad T480 i5-8250U 16GB 512GB", "laptop", []),
    # a NUC's processor is soldered; a laptop chip in a desktop title likewise
    ("Intel NUC i5-8259U 16GB RAM 500GB SSD", "desktop", [("ssd", "ssd", 1, 500, "500GB SSD")]),
    ("Dell PowerEdge R640 E5-2650 v4 x2 64GB No Drives", "server", [("cpu", "E5-2650 V4", 2, 0, "2 x Xeon E5-2650 v4")]),
    ("Dell OptiPlex 7050 SFF i5-6500 16GB RAM no SSD", "desktop", [("cpu", "I5-6500", 1, 0, "i5-6500")]),
    ("Intel S2600TP Compute Node 2x Eight-Core E5-2630v3 64GB Memory", "server", [("cpu", "E5-2630 V3", 2, 0, "2 x Xeon E5-2630 v3")]),
    # a job lot: six of everything
    ("Job Lot x 6 HP ProDesk 600 G3 SFF i5-6500 8GB RAM 256GB SSD", "desktop",
     [("ssd", "ssd", 6, 256, "6 x 256GB SSD"), ("cpu", "I5-6500", 6, 0, "6 x i5-6500")]),
    # eMMC is soldered
    ("HP Stream 11 Celeron N4020 4GB RAM 64GB eMMC", "laptop", []),
])
def test_parts_in_a_title(title, category, expected):
    assert found(title, category) == expected


@pytest.mark.parametrize("title,expected", [
    ("Samsung 860 EVO 500GB 2.5 SATA SSD", ("ssd", 500)),
    ("WD Blue 1TB SATA SSD 2.5", ("ssd", 1000)),
    ("Samsung PM981 256GB M.2 NVMe SSD", ("nvme", 256)),
    ("Seagate Barracuda 2TB 3.5 SATA Hard Drive", ("hdd", 2000)),
    ("HP 600GB 10K SAS 2.5 Hard Drive", ("sas", 600)),
    ("Dell 1.92TB SAS 12Gb/s 2.5 SSD", None),             # SAS SSDs would lift the SATA SSD price
    ("Job lot 10x 120GB SATA SSD", None),
    ("Seagate 2TB external USB hard drive", None),
    ("SATA SSD 120GB 240GB 480GB", None),                 # a listing with options
    ("Faulty 1TB SATA hard drive", None),
    ("Kingston 32GB SATA SSD", None),                     # too small to be worth anything
])
def test_drive_listings(title, expected):
    assert drive_sample(title) == expected


def test_model_listings_must_be_exactly_one_of_the_model():
    assert model_sample("Intel Core i5-6500 3.2GHz SR2L6 CPU", "cpu", "I5-6500")
    assert not model_sample("Intel Core i5-6600 3.3GHz CPU", "cpu", "I5-6500")
    assert not model_sample("Intel Core i5-6500 with motherboard and 8GB RAM", "cpu", "I5-6500")
    assert not model_sample("2x Intel Xeon E5-2680 v4 matched pair", "cpu", "E5-2680 V4")
    assert model_sample("MSI GeForce RTX 3060 Ventus 12GB", "gpu", "RTX 3060")
    assert not model_sample("Zotac GeForce RTX 3060 Ti 8GB", "gpu", "RTX 3060")       # a different card
    assert not model_sample("Gaming PC i5 RTX 3060 16GB", "gpu", "RTX 3060")          # a whole computer
    assert not model_sample("RTX 3060 faulty no display", "gpu", "RTX 3060")
    assert model_query("cpu", "E5-2680 V4") == "Xeon E5-2680 V4" and model_query("cpu", "I5-6500") == "I5-6500"
    assert model_query("gpu", "RTX 3060 TI") == "RTX 3060 TI"


def test_part_prices_and_values():
    # per GB: 0.05 0.05 0.06 0.0625 0.07 -> lower quartile 0.05, median 0.06; four hard drives are too few
    samples = [("ssd", 240, 12), ("ssd", 500, 25), ("ssd", 480, 28.8), ("ssd", 256, 16), ("ssd", 1000, 70),
               ("hdd", 1000, 15), ("hdd", 2000, 30), ("hdd", 500, 8), ("hdd", 4000, 50),
               ("ssd", 500, 400)]   # 0.80 a GB: mislabelled, left out
    drives = drive_prices(samples)
    assert drives == [{"kind": "ssd", "pricePerGb": 0.05, "medianPerGb": 0.06, "sampleSize": 5}]
    assert model_price("cpu", "I5-6500", [10, 12, 12, 14]) is None
    model = model_price("gpu", "RTX 3060", [150, 160, 170, 180, 200])   # lower quartile 160, median 170
    assert model == {"kind": "gpu", "model": "RTX 3060", "price": 160, "median": 170, "sampleSize": 5}
    assert part_value("ssd", "ssd", 2, 480, drives, [model]) == 38.4       # 0.8 x 2 x 480 x 0.05
    assert part_value("hdd", "hdd", 1, 2000, drives, [model]) is None      # no hard drive price
    assert part_value("gpu", "RTX 3060", 1, 0, drives, [model]) == 128     # 0.8 x 160
    assert part_value("gpu", "RTX 3070", 1, 0, drives, [model]) is None
