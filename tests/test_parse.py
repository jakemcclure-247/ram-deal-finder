"""Title reading. Every expectation was worked out by hand from the title."""
from __future__ import annotations

import pytest

from ram_deal_finder.parse import parse_computer, parse_module

COMPUTERS = [
    # title, category, GB, generations, form, confidence, warnings
    ("Dell Latitude 5490 i5-8350U 32GB RAM 256GB SSD", "laptop", 32, ("DDR4",), "SODIMM", "stated", ["ram-type-assumed"]),
    # no word says which size is memory: the smaller one, and 11th-gen Intel means DDR4
    ("Lenovo ThinkPad T14 Gen 2 i7-1165G7 16GB 512GB", "laptop", 16, ("DDR4",), "SODIMM", "inferred",
     ["ram-size-inferred", "ram-type-assumed"]),
    ("Dell Latitude 5420 i5-1145G7 16GB 256GB NVMe 14\"", "laptop", 16, ("DDR4",), "SODIMM", "inferred",
     ["ram-size-inferred", "ram-type-assumed"]),
    ("HP EliteBook 840 G9 i5-1245U 16GB DDR5 256GB SSD", "laptop", 16, ("DDR5",), "SODIMM", "stated", []),
    # 12th-gen Intel takes either
    ("Dell XPS 15 9520 i7-12700H 32GB RAM 1TB SSD", "laptop", 32, ("DDR4", "DDR5"), "SODIMM", "stated", ["ram-type-uncertain"]),
    ("Lenovo ThinkPad X1 Carbon Gen 6 i7-8650U 16GB RAM 512GB SSD", "laptop", 16, ("DDR4",), "SODIMM", "stated",
     ["ram-type-assumed", "ram-may-be-soldered"]),
    ("Acer Aspire 5 Ryzen 7 5700U 2x16GB DDR4 1TB NVMe", "laptop", 32, ("DDR4",), "SODIMM", "stated", []),
    # the T460 is the 6th-gen ThinkPad that still takes DDR3; the T460s doesn't
    ("Lenovo ThinkPad T460 i5-6300U 16GB RAM 256GB SSD", "laptop", 16, ("DDR3",), "SODIMM", "stated", ["ram-type-assumed"]),
    ("Lenovo ThinkPad T460s i5-6300U 16GB RAM 256GB SSD", "laptop", 16, ("DDR4",), "SODIMM", "stated", ["ram-type-assumed"]),
    ("Custom PC 32GB RAM 1TB HDD Windows 11", "desktop", 32, (), "DIMM", "stated", ["ram-type-unknown"]),
    # 8GB belongs to the graphics card, 12GB likewise
    ("Gaming PC i7-6700K GTX 1070 8GB 16GB DDR4 480GB SSD", "desktop", 16, ("DDR4",), "DIMM", "stated", []),
    ("Gaming PC Ryzen 5 5600X 32GB RAM RTX 3060 12GB 1TB NVMe", "desktop", 32, ("DDR4",), "DIMM", "stated", ["ram-type-assumed"]),
    # mini desktops take laptop memory; "up to 64GB" is not what's fitted
    ("HP EliteDesk 800 G4 Mini i5-8500T 64GB RAM 256GB NVMe", "desktop", 64, ("DDR4",), "SODIMM", "stated", ["ram-type-assumed"]),
    ("Lenovo ThinkCentre M920q Tiny i5-8500T up to 64GB 16GB RAM", "desktop", 16, ("DDR4",), "SODIMM", "stated", ["ram-type-assumed"]),
    ("Dell OptiPlex 7050 SFF i5-6500 32GB DDR4 500GB HDD", "desktop", 32, ("DDR4",), "DIMM", "stated", []),
    # a listing with options is priced for the smallest
    ("Dell OptiPlex 7060 SFF i7-8700 16GB/32GB RAM 256GB SSD", "desktop", 16, ("DDR4",), "DIMM", "inferred",
     ["ram-size-inferred", "ram-type-assumed"]),
    ("HP Z440 Workstation Xeon E5-1650 v3 64GB DDR4 ECC", "desktop", 64, ("DDR4",), "RDIMM", "stated", []),
    ("Dell PowerEdge R730 2x E5-2680 v4 256GB RAM 8x 1.2TB SAS", "server", 256, ("DDR4",), "RDIMM", "stated", ["ram-type-assumed"]),
    # 2x 300GB SAS is storage; Gen8 means DDR3
    ("HP ProLiant DL380 Gen8 128GB 2x 300GB SAS", "server", 128, ("DDR3",), "RDIMM", "inferred",
     ["ram-size-inferred", "ram-type-assumed"]),
    ("Dell Latitude 5490 i5-8350U 32GB RAM - spares or repairs", "laptop", 32, ("DDR4",), "SODIMM", "stated",
     ["ram-type-assumed", "untested-or-faulty"]),
]


@pytest.mark.parametrize("title,category,gb,generations,form,confidence,warnings", COMPUTERS)
def test_computer_titles(title, category, gb, generations, form, confidence, warnings):
    memory = parse_computer(title, category)
    assert memory is not None
    assert (memory.ram_gb, memory.generations, memory.form, memory.confidence) == (gb, generations, form, confidence)
    assert list(memory.warnings) == warnings


@pytest.mark.parametrize("title,category", [
    ("HP Stream 14 Celeron N4000 32GB", "laptop"),            # a bare 32GB on a Celeron is storage
    ("Dell Latitude 7490 i5 No RAM No SSD", "laptop"),
    ("Dell Latitude 5590 i7-8650U No HDD/RAM (supports 32GB)", "laptop"),
    ("Apple MacBook Air M2 16GB 256GB", "laptop"),            # soldered for certain
    ("Apple Mac mini M1 16GB RAM 512GB SSD", "desktop"),
    ("Microsoft Surface Pro 7 i7 16GB RAM 256GB", "laptop"),
    ("Dell XPS 13 9310 i7 16GB LPDDR4x 512GB", "laptop"),
    ("Dell OptiPlex 3080 Micro i5-10500T 32GB RAM - choose your spec", "desktop"),
    ("Dell PowerEdge R630 barebones chassis only", "server"),
    ("Lenovo ThinkPad T480 i5-8250U 256GB SSD", "laptop"),    # no memory size at all
    ("Lenovo ThinkPad T480 i5 256GB", "laptop"),              # too big to be a laptop's memory unless it says so
    ("Dell VFR5T 256GB 6Gbps SATA M.2 2280 SSD - 1yr Wty", "server"),   # a drive: the size is the drive's
    ("Lenovo ThinkSmart HUB 500 AIO PC-i5-7500T 128GB M. 2,8GB RAM-NO OS", "desktop"),
    ("HP ENVY x2 13-j000na Detachable PC For Spares Or Repair 128gb", "desktop"),
])
def test_computers_that_cannot_be_deals(title, category):
    assert parse_computer(title, category) is None


def test_condition_for_parts_counts_as_faulty():
    memory = parse_computer("Dell Latitude 5490 i5-8350U 32GB RAM", "laptop", "7000")
    assert list(memory.warnings) == ["ram-type-assumed", "untested-or-faulty"]


@pytest.mark.parametrize("title,expected", [
    ("Samsung 16GB DDR4 SODIMM PC4-2666V Laptop Memory", ("DDR4", "SODIMM", 16)),
    ("Kingston 16GB (2x8GB) DDR4 SO-DIMM Kit", ("DDR4", "SODIMM", 16)),
    ("Corsair 2x8GB DDR4 3200 Desktop Memory", ("DDR4", "DIMM", 16)),
    ("Crucial 16GB DDR5 Non-ECC Desktop RAM", ("DDR5", "DIMM", 16)),
    ("Crucial 8GB DDR3L SODIMM PC3L-12800S", ("DDR3", "SODIMM", 8)),
    ("Samsung 32GB DDR4 PC4-2400T-R ECC Registered RDIMM Server Memory", ("DDR4", "RDIMM", 32)),
    ("Kingston 16GB DDR4 ECC Unbuffered UDIMM", None),         # neither desktop nor registered
    ("DDR4 SODIMM 8GB 16GB 32GB laptop memory", None),          # options: which one is the price for?
    ("Job lot 10 x 4GB DDR4 SODIMM laptop RAM", None),
    ("4x Samsung 16GB DDR4 SODIMM", None),                      # four sticks at an unknown split
    ("16GB DDR4 RAM 2666MHz", None),                            # laptop or desktop?
    ("Faulty Corsair 16GB DDR4 desktop memory", None),
    ("Dell PowerEdge R730 2x Xeon E5-2680 v4 64GB DDR4 RDIMM", None),  # a whole server
    ("16GB DDR3 DDR4 SODIMM", None),
])
def test_memory_titles(title, expected):
    assert parse_module(title) == expected
