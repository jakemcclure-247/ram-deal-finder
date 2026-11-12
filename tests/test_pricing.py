"""Reference prices and margins, worked by hand."""
from __future__ import annotations

from ram_deal_finder.pricing import estimate, lookup, module_sample, quantile, reference_prices

SODIMM = [4.00, 4.25, 4.375, 4.50, 4.75, 5.00]
DIMM = [3.50, 3.75, 3.875, 4.00, 4.25, 4.50]


def test_quantile_interpolates():
    # six values: the quartile sits at position 5 * 0.25 = 1.25, a quarter of the way from 4.25 to 4.375
    assert quantile(SODIMM, 0.25) == 4.28125
    assert quantile(SODIMM, 0.5) == 4.4375   # halfway between 4.375 and 4.50
    assert quantile([7.0], 0.25) == 7.0
    assert quantile([5.0, 1.0, 3.0], 0.5) == 3.0   # sorts first


def test_module_sample_is_price_over_capacity():
    assert module_sample("Kingston 16GB (2x8GB) DDR4 SO-DIMM Kit", 70) == ("DDR4", "SODIMM", 4.375)
    assert module_sample("Samsung 16GB DDR4 SODIMM", 800) is None    # £50 a GB is not a memory price
    assert module_sample("Samsung 16GB DDR4 SODIMM", 1) is None      # nor is 6p
    assert module_sample("16GB DDR4 RAM", 50) is None


def test_reference_prices_need_five_listings_and_use_the_lower_quartile():
    samples = [("DDR4", "DIMM", p) for p in DIMM] + [("DDR4", "SODIMM", p) for p in SODIMM]
    samples += [("DDR3", "SODIMM", 1.0)] * 4   # one short
    assert reference_prices(samples) == [
        {"generation": "DDR4", "form": "SODIMM", "pricePerGb": 4.28, "medianPerGb": 4.44, "sampleSize": 6},
        {"generation": "DDR4", "form": "DIMM", "pricePerGb": 3.78, "medianPerGb": 3.94, "sampleSize": 6},
    ]


REFS = [
    {"generation": "DDR3", "form": "SODIMM", "pricePerGb": 1.10, "medianPerGb": 1.3, "sampleSize": 9},
    {"generation": "DDR4", "form": "SODIMM", "pricePerGb": 4.28, "medianPerGb": 4.44, "sampleSize": 6},
    {"generation": "DDR4", "form": "DIMM", "pricePerGb": 3.78, "medianPerGb": 3.94, "sampleSize": 6},
    {"generation": "DDR5", "form": "SODIMM", "pricePerGb": 3.20, "medianPerGb": 3.5, "sampleSize": 7},
]


def test_lookup_exact():
    assert lookup(REFS, ("DDR4",), "SODIMM") == ("DDR4", 4.28, False)


def test_lookup_takes_the_cheaper_of_two_possible_generations():
    assert lookup(REFS, ("DDR4", "DDR5"), "SODIMM") == ("DDR5", 3.20, False)


def test_lookup_falls_back_to_the_cheapest_form_of_the_same_generation():
    assert lookup(REFS, ("DDR4",), "RDIMM") == ("DDR4", 3.78, True)


def test_lookup_unknown_generation_uses_the_cheapest_of_that_form():
    assert lookup(REFS, (), "SODIMM") == (None, 1.10, True)
    assert lookup(REFS, (), "RDIMM") == (None, 1.10, True)   # no server prices at all: cheapest of anything


def test_lookup_never_borrows_another_generation_for_a_known_one():
    assert lookup(REFS, ("DDR5",), "DIMM") == ("DDR5", 3.20, True)
    assert lookup(REFS[1:3], ("DDR3",), "SODIMM") is None
    assert lookup([], (), "DIMM") is None


def test_estimate():
    # 0.8 x 64 GB x £4.28 = £219.136 -> £219.14; less £120 + £8 postage = £91.14
    assert estimate(64, 4.28, 128) == (219.14, 91.14)
    # 0.8 x 32 x 4.28 = 109.568 -> 109.57; less 61.99 = 47.58
    assert estimate(32, 4.28, 61.99) == (109.57, 47.58)
    # 0.8 x 32 x 3.78 = 96.768 -> 96.77; a £260 computer loses £163.23
    assert estimate(32, 3.78, 260) == (96.77, -163.23)
