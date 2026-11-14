# RAM Deal Finder

Finds computers on eBay UK that cost less than the estimated resale value of the memory inside them, and
writes the result to `data/deals.json`. The page at https://jakem.uk/ram-deals/ reads that file straight
from this repository, which is why the repository is public.

It uses eBay's official Browse API only. It never fetches or scrapes eBay's website.

## How it works

1. Gets an application token (client-credentials grant).
2. Searches eBay UK for **used memory modules** (DDR3/4/5 as laptop SODIMM, desktop DIMM and server RDIMM)
   and works out a price per GB for each kind from the listings whose titles make the generation, form
   and capacity clear. Postage is left out. The **reference price is the lower quartile**, and the median
   and sample size are published beside it. A kind with fewer than 5 usable listings gets no price.
3. Searches laptops, desktops and servers in three ways (`ram_deal_finder/config.py`):
   - **By size:** titles with a size next to a memory word ("32GB RAM", "32GB DDR4"...), cheapest first,
     capped at the most that much DDR3/DDR4 memory could be worth. Everything returned is a candidate.
   - **DDR5:** the same, capped with the DDR5 price, which is several times higher.
   - **Job lots:** "job lot", "bulk", "wholesale" and "pallet" listings, newest first. The title's count
     is multiplied by one computer's memory ("Job Lot x 6 ... 8GB RAM" is 48GB), always with the
     `ram-size-inferred` warning. A lot that gives no count is valued as one computer.

   Buy It Now listings only (the API's default); auctions are left out because their price isn't final.
4. Reads each title for memory size, generation and form (`ram_deal_finder/parse.py`), then:

   ```
   estRamValue = 0.8 x ramGb x pricePerGb        (0.8 covers fees, postage and duds)
   totalCost   = price + postage (postage counted as 0 when eBay doesn't give it)
   estMargin   = estRamValue - totalCost
   ```

   Listings with a positive margin are the deals, best first.
5. Writes the feed. A deal seen on an earlier run keeps its `firstSeenAt`; a listing eBay no longer
   returns is dropped.

Where the title leaves doubt, the estimate takes the cheaper reading and the deal carries a warning:

| Code | Meaning |
| --- | --- |
| `ram-size-inferred` | No word in the title says which size is the memory, the listing offers several sizes (the smallest is used), or it is a job lot (count times one computer's memory) |
| `ram-type-assumed` | Generation taken from the processor or server model |
| `ram-type-uncertain` | Could be DDR4 or DDR5 (priced as the cheaper) |
| `ram-type-unknown` | Nothing to go on (priced as the cheapest generation) |
| `ram-price-approximate` | No reference price for exactly this kind of memory, so a cheaper neighbour was used |
| `ram-may-be-soldered` | A model line that often has soldered memory |
| `untested-or-faulty` | Sold as spares, repairs, untested or not working |
| `postage-unknown` | eBay gave no postage cost (often collection only) |

Left out altogether: no memory fitted, memory that is certainly soldered (LPDDR, Apple silicon, MacBook
Air, Surface), pick-your-spec listings (anything eBay marks as having variations, because the price shown
is the cheapest option's), a bare "32GB" on a Celeron or similar, which is storage, and a bare size in a
title that names a drive but gives no size for it.

## Setting up

You need an [eBay developer account](https://developer.ebay.com/) with a **production** keyset.
Before the keys work eBay makes you either subscribe to, or opt out of, marketplace account deletion
notifications (Application Keys → Notifications). This project stores no eBay user data: no seller
names, no buyer data.

```bash
copy .env.example .env
```

Put the keys in `.env` (git ignores it): `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, and optionally
`EPN_CAMPAIGN_ID` (an eBay Partner Network campaign id) to get affiliate links in the feed.

```bash
py -m ram_deal_finder check
```

```bash
py -m ram_deal_finder run
```

`check` gets a token and makes one search. `run` writes `data/deals.json` and prints how many listings
each search returned. If a search returns nothing, its category id in `ram_deal_finder/config.py` is
probably wrong for eBay UK.

No dependencies beyond Python 3.10+. Tests need pytest and no network:

```bash
py -m pytest -q
```

```bash
py -m ram_deal_finder run --fixtures tests/fixtures/ebay.json
```

The second command is a dry run against invented listings. It writes `data/deals.fixture.json` (ignored
by git), never the real feed, unless you pass `--out`.

## GitHub Actions

`.github/workflows/feed.yml` runs every two hours and on demand (Actions → feed → Run workflow). It runs
the tests, builds the feed and commits `data/deals.json` if it changed. A failed run commits nothing, so
the previous feed stays. A push only runs the tests.

Add the repository secrets `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` (Settings → Secrets and variables →
Actions), and `EPN_CAMPAIGN_ID` if you have one.

**API calls:** 31 to 41 a run (1 token, 9 memory searches, 21 computer searches, some of which take a
second page), so at most about 500 a day. The client stops itself at 60 calls in one run. eBay allows 1,000 application tokens a day; the Browse API's own
daily allowance is shown under Application Keys in the developer account.

## eBay's terms that shape this

From the [API License Agreement](https://developer.ebay.com/join/api-license-agreement) and the Buy API
requirements, as read on 12 November 2026:

- **Listings shown must be no more than 6 hours old**, and the page must say how old they are. Hence the
  two-hourly run; the page shows the feed's age.
- **Content no longer on eBay must be deleted.** Each run drops listings eBay no longer returns. Old feeds
  do remain in this repository's git history.
- eBay asks for **written permission** before showing eBay content in a way that lets someone derive the
  **average selling price for a category**, and lists using eBay content **"to suggest or model prices for
  items listed on eBay"** among restricted activities. The reference prices here are asking prices of
  current listings, not sold prices, but this is close to that line.
- eBay content must not be **mixed with non-eBay content**, must not be used to **train AI**, and must not
  be distributed other than through your application.
- eBay says production use of the Buy APIs (Browse included) is **for approved partners**, applied for
  through the eBay Partner Network.

## Layout

```
ram_deal_finder/
  parse.py     titles -> memory size, generation, form, warnings
  pricing.py   reference prices per GB, value and margin
  ebay.py      Browse API client (token, search) and the fixture stand-in
  feed.py      builds, checks and writes the feed; the run itself
  config.py    the searches and category ids
tests/         hand-worked expectations; make_fixture.py writes tests/fixtures/ebay.json
data/deals.json  the feed (written by the workflow)
```
