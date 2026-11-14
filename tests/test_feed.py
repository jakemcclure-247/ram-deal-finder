"""The whole run against invented listings, plus the API client with a fake network."""
from __future__ import annotations

import io
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ram_deal_finder import config
from ram_deal_finder.ebay import EbayClient, EbayError, FixtureClient
from ram_deal_finder.feed import build_feed, load_previous, price_band, price_cap, run, validate_feed, write_feed
from tests.make_fixture import LAPTOP_32
from tests.make_fixture import build as fixture

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 11, 12, 11, 0, tzinfo=timezone.utc)
SEEN = {"firstSeenAt": "2026-11-12T09:00:00.000Z", "lastSeenAt": "2026-11-12T09:00:00.000Z"}

EXPECTED = {
    "generatedAt": "2026-11-12T09:00:00.000Z",
    "marketplace": "EBAY_GB",
    "currency": "GBP",
    "affiliateLinks": False,
    # 11 different computers (one found twice), 23 memory listings, nothing seen before
    "stats": {"listingsScanned": 11, "memoryListingsSampled": 23, "newDealsThisRun": 3},
    "referencePrices": [
        {"generation": "DDR4", "form": "SODIMM", "pricePerGb": 4.28, "medianPerGb": 4.44, "sampleSize": 6},
        {"generation": "DDR4", "form": "DIMM", "pricePerGb": 3.78, "medianPerGb": 3.94, "sampleSize": 6},
    ],
    "deals": [
        # 0.8 x 64 x 4.28 = 219.14, less 120 + 8
        {"id": "v1|800000000013|0", "title": "HP EliteDesk 800 G4 Mini i5-8500T 64GB RAM 256GB NVMe",
         "url": "https://www.ebay.co.uk/itm/800000000013", "image": None, "category": "desktop", "condition": "Used",
         "location": "Reading", "listedAt": "2026-11-12T07:45:00.000Z", "price": 120, "shipping": 8, "totalCost": 128,
         "ramGb": 64, "ramGeneration": "DDR4", "ramForm": "SODIMM", "ramConfidence": "stated", "estRamValue": 219.14,
         "estMargin": 91.14, "warnings": ["ram-type-assumed"], **SEEN},
        # 0.8 x 32 x 4.28 = 109.57, less 55 + 6.99
        {"id": "v1|800000000001|0", "title": "Dell Latitude 5490 i5-8350U 32GB RAM 256GB SSD - cracked screen, spares or repairs",
         "url": "https://www.ebay.co.uk/itm/800000000001", "image": None, "category": "laptop",
         "condition": "For parts or not working", "location": "Leeds", "listedAt": "2026-11-12T08:14:00.000Z", "price": 55,
         "shipping": 6.99, "totalCost": 61.99, "ramGb": 32, "ramGeneration": "DDR4", "ramForm": "SODIMM",
         "ramConfidence": "stated", "estRamValue": 109.57, "estMargin": 47.58,
         "warnings": ["ram-type-assumed", "untested-or-faulty"], **SEEN},
        # 0.8 x 32 x 3.78 = 96.77, less 60 with no postage given
        {"id": "v1|800000000011|0", "title": "Dell OptiPlex 7050 SFF i5-6500 32GB DDR4 500GB HDD",
         "url": "https://www.ebay.co.uk/itm/800000000011", "image": None, "category": "desktop", "condition": "Used",
         "location": "Manchester", "listedAt": "2026-11-12T08:01:00.000Z", "price": 60, "shipping": None, "totalCost": 60,
         "ramGb": 32, "ramGeneration": "DDR4", "ramForm": "DIMM", "ramConfidence": "stated", "estRamValue": 96.77,
         "estMargin": 36.77, "warnings": ["postage-unknown"], **SEEN},
    ],
}


@pytest.fixture
def fixture_file(tmp_path):
    path = tmp_path / "ebay.json"
    path.write_text(json.dumps(fixture()), encoding="utf-8")
    return path


def quiet(*_):
    pass


def test_fixture_run_writes_the_expected_feed(fixture_file, tmp_path):
    out = tmp_path / "data" / "deals.json"
    client = FixtureClient(fixture_file)
    feed = run(client, out, NOW, log=quiet)
    assert feed == EXPECTED
    assert json.loads(out.read_text(encoding="utf-8")) == EXPECTED
    # every search fits on one page, so one call each
    assert client.calls == len(config.MEMORY) + len(config.COMPUTERS) == 30


def test_a_full_page_is_followed_by_the_next_one(tmp_path):
    listings = fixture()
    full = [laptop(itemId=f"v1|{600000000000 + n}|0", legacyItemId=str(600000000000 + n), title="Acer Aspire 4GB RAM",
                   price={"value": "500.00", "currency": "GBP"}) for n in range(200)]
    listings[LAPTOP_32] = full + listings[LAPTOP_32]
    path = tmp_path / "ebay.json"
    path.write_text(json.dumps(listings), encoding="utf-8")
    client = FixtureClient(path)
    feed = run(client, tmp_path / "deals.json", NOW, log=quiet)
    assert client.calls == 31                                    # one more, for the second page
    assert feed["stats"]["listingsScanned"] == 211
    assert [d["id"] for d in feed["deals"]] == [d["id"] for d in EXPECTED["deals"]]   # the Latitude is on page two


def test_committed_fixture_matches_its_generator():
    committed = json.loads((Path(__file__).parent / "fixtures" / "ebay.json").read_text(encoding="utf-8"))
    assert committed == fixture()


def test_second_run_keeps_first_seen_and_drops_what_has_gone(fixture_file, tmp_path):
    out = tmp_path / "deals.json"
    run(FixtureClient(fixture_file), out, NOW, log=quiet)
    listings = fixture()
    listings[LAPTOP_32] = listings[LAPTOP_32][1:]   # the Latitude has sold
    fixture_file.write_text(json.dumps(listings), encoding="utf-8")
    feed = run(FixtureClient(fixture_file), out, LATER, log=quiet)
    assert [d["id"] for d in feed["deals"]] == ["v1|800000000013|0", "v1|800000000011|0"]
    assert all(d["firstSeenAt"] == "2026-11-12T09:00:00.000Z" for d in feed["deals"])
    assert all(d["lastSeenAt"] == "2026-11-12T11:00:00.000Z" for d in feed["deals"])
    assert feed["generatedAt"] == "2026-11-12T11:00:00.000Z"
    assert feed["stats"] == {"listingsScanned": 10, "memoryListingsSampled": 23, "newDealsThisRun": 0}


def test_a_failed_run_leaves_the_previous_feed(fixture_file, tmp_path):
    out = tmp_path / "deals.json"
    run(FixtureClient(fixture_file), out, NOW, log=quiet)
    before = out.read_bytes()
    listings = fixture()
    for key in ("170083|DDR4 SODIMM", "170083|DDR4 desktop memory"):
        del listings[key]                              # no usable memory prices this time
    fixture_file.write_text(json.dumps(listings), encoding="utf-8")
    with pytest.raises(RuntimeError, match="No reference prices"):
        run(FixtureClient(fixture_file), out, LATER, log=quiet)
    assert out.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir() if p.suffix == ".tmp"] == []


def test_write_refuses_a_bad_feed_and_keeps_the_old_one(tmp_path):
    out = tmp_path / "deals.json"
    write_feed(EXPECTED, out)
    before = out.read_bytes()
    bad = json.loads(json.dumps(EXPECTED))
    bad["deals"][0]["url"] = "https://example.com/itm/1"
    with pytest.raises(ValueError, match="deal url"):
        write_feed(bad, out)
    assert out.read_bytes() == before


@pytest.mark.parametrize("change,message", [
    (lambda f: f["deals"].reverse(), "sorted"),
    (lambda f: f["deals"][0].update(estMargin=90), "margin arithmetic"),
    (lambda f: f["deals"][0].update(warnings=["made-up"]), "warning codes"),
    (lambda f: f["deals"][0].update(image="https://example.com/a.jpg"), "image"),
    (lambda f: f["deals"][0].pop("lastSeenAt"), "deal keys"),
    (lambda f: f.update(currency="USD"), "currency"),
])
def test_validate_catches(change, message):
    feed = json.loads(json.dumps(EXPECTED))
    change(feed)
    with pytest.raises(ValueError, match=message):
        validate_feed(feed)


def modules():
    listings = fixture()
    return listings["170083|DDR4 SODIMM"] + listings["170083|DDR4 desktop memory"]


def laptop(**changes):
    item = {"itemId": "v1|700000000001|0", "legacyItemId": "700000000001", "title": "Dell Latitude 5490 i5-8350U 32GB RAM",
            "price": {"value": "50.00", "currency": "GBP"}, "condition": "Used", "conditionId": "3000",
            "itemWebUrl": "https://www.ebay.co.uk/itm/700000000001?hash=abc",
            "shippingOptions": [{"shippingCost": {"value": "0.00", "currency": "GBP"}}]}
    item.update(changes)
    return item


def one_deal(item, affiliate=False):
    return build_feed([("laptop", item)], modules(), None, NOW, affiliate)["deals"]


def test_links_and_pictures_only_from_ebay():
    deal = one_deal(laptop(image={"imageUrl": "https://i.ebayimg.com/images/g/abc/s-l225.jpg"},
                           itemAffiliateWebUrl="https://www.ebay.co.uk/itm/700000000001?mkevt=1&campid=5330000000"))[0]
    assert deal["url"] == "https://www.ebay.co.uk/itm/700000000001"        # not asked for affiliate links
    assert deal["image"] == "https://i.ebayimg.com/images/g/abc/s-l225.jpg"
    assert deal["shipping"] == 0 and deal["totalCost"] == 50 and deal["warnings"] == ["ram-type-assumed"]
    deal = one_deal(laptop(image={"imageUrl": "https://evil.example/x.jpg"},
                           itemAffiliateWebUrl="https://www.ebay.co.uk/itm/700000000001?mkevt=1&campid=5330000000"), True)[0]
    assert deal["url"] == "https://www.ebay.co.uk/itm/700000000001?mkevt=1&campid=5330000000"
    assert deal["image"] is None
    deal = one_deal(laptop(itemAffiliateWebUrl="https://evil.example/itm/1"), True)[0]
    assert deal["url"] == "https://www.ebay.co.uk/itm/700000000001"


def test_listings_that_are_not_deals():
    assert one_deal(laptop(price={"value": "50.00", "currency": "USD"})) == []     # not priced in pounds
    assert one_deal(laptop(price={"value": "109.57", "currency": "GBP"})) == []    # margin exactly nil
    assert len(one_deal(laptop(price={"value": "109.56", "currency": "GBP"}))) == 1
    assert one_deal(laptop(title="Dell Latitude 5490 i5-8350U No RAM")) == []
    # a listing with a spec picker shows its cheapest option's price, not the titled spec's
    assert one_deal(laptop(itemGroupType="SELLER_DEFINED_VARIATIONS")) == []


def test_memory_listings_with_a_spec_picker_are_not_sampled():
    picker = [dict(m, itemGroupType="SELLER_DEFINED_VARIATIONS") for m in modules()]
    feed = build_feed([("laptop", laptop())], picker, None, NOW)
    assert feed["referencePrices"] == [] and feed["deals"] == []


def test_unknown_memory_type_is_priced_at_the_cheapest_and_says_so():
    deal = build_feed([("desktop", laptop(title="Custom PC 32GB RAM"))], modules(), None, NOW)["deals"][0]
    # cheapest desktop price 3.78: 0.8 x 32 x 3.78 = 96.77, less 50
    assert (deal["ramGeneration"], deal["estRamValue"], deal["estMargin"]) == (None, 96.77, 46.77)
    assert deal["warnings"] == ["ram-type-unknown", "ram-price-approximate"]


def test_price_cap_is_the_most_the_memory_could_be_worth():
    assert price_cap(EXPECTED["referencePrices"], 32) == 110   # 0.8 x 32 x 4.28 = 109.57, rounded up
    assert price_cap(EXPECTED["referencePrices"], 512) == 1754  # 1753.09
    refs = EXPECTED["referencePrices"] + [{"generation": "DDR5", "form": "SODIMM", "pricePerGb": 9.0}]
    assert price_cap(refs, 32) == 110                # DDR5 doesn't lift the cap of an ordinary search
    assert price_cap(refs, 32, ddr5=True) == 231     # 0.8 x 32 x 9 = 230.4
    assert price_cap(EXPECTED["referencePrices"], 32, ddr5=True) == 110   # no DDR5 price: the best there is


def test_price_band_of_each_kind_of_search():
    refs = EXPECTED["referencePrices"]
    assert price_band(refs, {"ram_gb": 512}) == (87, 1754)      # from a twentieth of the cap: 87.7
    assert price_band(refs, {"ram_gb": 32}) == (10, 110)        # never from under £10
    assert price_band(refs, {"max_price": 5000}) == (10, 5000)  # job lots: no size to cap by


def test_a_job_lot_is_valued_on_all_its_computers():
    lot = laptop(title="Job Lot x 6 HP ProBook 640 G4 i5-8250U 8GB RAM no SSD", price={"value": "150.00", "currency": "GBP"})
    deal = one_deal(lot)[0]
    # 6 x 8GB = 48GB: 0.8 x 48 x 4.28 = 164.35, less 150
    assert (deal["ramGb"], deal["estRamValue"], deal["estMargin"]) == (48, 164.35, 14.35)
    assert deal["ramConfidence"] == "inferred" and deal["warnings"] == ["ram-size-inferred", "ram-type-assumed"]


def test_load_previous_survives_rubbish(tmp_path):
    assert load_previous(tmp_path / "missing.json") is None
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert load_previous(tmp_path / "bad.json") is None
    (tmp_path / "list.json").write_text("[]", encoding="utf-8")
    assert load_previous(tmp_path / "list.json") is None
    assert build_feed([], modules(), {"deals": "nonsense"}, NOW)["deals"] == []


# ------------------------------------------------------------------ the API client, with no network

class FakeNetwork:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return io.BytesIO(json.dumps(response).encode())


def http_error(code):
    return urllib.error.HTTPError("https://api.ebay.com", code, "error", {}, io.BytesIO(b'{"errors":[]}'))


def test_client_gets_one_token_then_searches_ebay_uk():
    network = FakeNetwork({"access_token": "tok", "expires_in": 7200}, {"itemSummaries": [{"itemId": "a"}]}, {"total": 0})
    client = EbayClient("id", "secret", opener=network)
    assert client.search("32GB", "177", "price:[1..110],priceCurrency:GBP", "newlyListed") == [{"itemId": "a"}]
    assert client.search("64GB") == []
    token, first, second = network.requests
    assert token.full_url == "https://api.ebay.com/identity/v1/oauth2/token"
    assert token.get_header("Authorization") == "Basic aWQ6c2VjcmV0"                 # base64 of id:secret
    assert token.data == b"grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope"
    assert first.full_url == ("https://api.ebay.com/buy/browse/v1/item_summary/search?q=32GB&limit=200&category_ids=177"
                              "&filter=price%3A%5B1..110%5D%2CpriceCurrency%3AGBP&sort=newlyListed")
    assert first.get_header("Authorization") == "Bearer tok"
    assert first.get_header("X-ebay-c-marketplace-id") == "EBAY_GB"
    assert first.get_header("X-ebay-c-enduserctx") == "contextualLocation=country%3DGB"
    assert client.calls == 3


def test_client_sends_the_affiliate_campaign():
    network = FakeNetwork({"access_token": "tok"}, {})
    EbayClient("id", "secret", "5330000000", opener=network).search("32GB")
    assert network.requests[1].get_header("X-ebay-c-enduserctx") == "affiliateCampaignId=5330000000,contextualLocation=country%3DGB"


def test_client_retries_server_errors_but_not_refusals():
    network = FakeNetwork({"access_token": "tok"}, http_error(503), {"itemSummaries": []})
    client = EbayClient("id", "secret", opener=network, sleep=lambda s: None)
    assert client.search("32GB") == []
    network = FakeNetwork({"access_token": "tok"}, http_error(429))
    with pytest.raises(EbayError, match="HTTP 429"):
        EbayClient("id", "secret", opener=network, sleep=lambda s: None).search("32GB")
    assert len(network.requests) == 2


def test_client_stops_at_its_call_limit_and_needs_keys():
    network = FakeNetwork({"access_token": "tok"}, {}, {}, {})
    client = EbayClient("id", "secret", opener=network, max_calls=3)
    client.search("a"), client.search("b")
    with pytest.raises(EbayError, match="Stopped at 3"):
        client.search("c")
    with pytest.raises(EbayError, match="EBAY_CLIENT_ID"):
        EbayClient("", "")
