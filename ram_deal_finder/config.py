"""What to search for. One API call per page of results: a run makes 1 (token) + len(MEMORY) + between
len(COMPUTERS) and the sum of their "pages" calls. As it stands that is 31 to 41 a run, so at most about
500 a day on the two-hourly schedule."""
from __future__ import annotations

# eBay UK category ids (checked on a real run, 14 November 2026: every search returned listings).
LAPTOPS = "177"       # PC Laptops & Netbooks
DESKTOPS = "179"      # PC Desktops & All-In-Ones
SERVERS = "11211"     # Computer Servers
MEMORY_CAT = "170083"  # Computer Memory (RAM)

# Used memory modules, eBay's default "Best Match" order. Each listing is filed by what its own
# title says, not by which search found it. Server memory is searched without a category.
MEMORY = [
    {"q": "DDR3 SODIMM", "category_id": MEMORY_CAT},
    {"q": "DDR4 SODIMM", "category_id": MEMORY_CAT},
    {"q": "DDR5 SODIMM", "category_id": MEMORY_CAT},
    {"q": "DDR3 desktop memory", "category_id": MEMORY_CAT},
    {"q": "DDR4 desktop memory", "category_id": MEMORY_CAT},
    {"q": "DDR5 desktop memory", "category_id": MEMORY_CAT},
    {"q": "DDR3 ECC registered", "category_id": None},
    {"q": "DDR4 RDIMM", "category_id": None},
    {"q": "DDR5 RDIMM", "category_id": None},
]
MEMORY_FILTER = "conditionIds:{3000},itemLocationCountry:GB"  # 3000 = Used


def size_query(*sizes: int) -> str:
    """eBay reads "(a b, c d)" as "a b" OR "c d". A bare "32GB" mostly finds 4GB laptops with 32GB of
    storage; asking for the size next to a memory word finds the ones that have 32GB of memory."""
    return "(" + ", ".join(f"{gb}GB {word}" for gb in sizes for word in ("RAM", "DDR3", "DDR4", "memory")) + ")"


def ddr5_query(*sizes: int) -> str:
    return "(" + ", ".join(f"{gb}GB DDR5" for gb in sizes) + ")"


LOT_QUERY = "(job lot, joblot, bulk, wholesale, pallet)"
LOT_MAX_PRICE = 5000


def _sized(category: str, category_id: str, gb: int, pages: int = 2) -> dict:
    return {"category": category, "category_id": category_id, "q": size_query(gb), "ram_gb": gb, "pages": pages}


# Three kinds of search.
#   Sized: cheapest first, capped at the most that much DDR3/DDR4 memory could be worth, so everything
#     returned is a candidate and the best come first. Two pages, because listings with a spec picker
#     (left out later) crowd the cheap end.
#   DDR5: the same with the DDR5 price, which is several times higher.
#   Job lots: newest first up to LOT_MAX_PRICE; the title gives the count and one computer's memory.
COMPUTERS = [
    _sized("laptop", LAPTOPS, 16),
    _sized("laptop", LAPTOPS, 32),
    _sized("laptop", LAPTOPS, 64, pages=1),
    {"category": "laptop", "category_id": LAPTOPS, "q": ddr5_query(16, 32, 64), "ram_gb": 64, "ddr5": True},
    {"category": "laptop", "category_id": LAPTOPS, "q": LOT_QUERY, "max_price": LOT_MAX_PRICE, "sort": "newlyListed",
     "pages": 2},
    _sized("desktop", DESKTOPS, 16),
    _sized("desktop", DESKTOPS, 32),
    _sized("desktop", DESKTOPS, 64),
    _sized("desktop", DESKTOPS, 128, pages=1),
    {"category": "desktop", "category_id": DESKTOPS, "q": ddr5_query(16, 32, 64), "ram_gb": 64, "ddr5": True},
    {"category": "desktop", "category_id": DESKTOPS, "q": LOT_QUERY, "max_price": LOT_MAX_PRICE, "sort": "newlyListed",
     "pages": 2},
    _sized("server", SERVERS, 64),
    _sized("server", SERVERS, 128),
    _sized("server", SERVERS, 192, pages=1),
    _sized("server", SERVERS, 256),
    _sized("server", SERVERS, 384, pages=1),
    _sized("server", SERVERS, 512, pages=1),
    _sized("server", SERVERS, 768, pages=1),
    {"category": "server", "category_id": SERVERS, "q": "(1TB RAM, 1024GB RAM, 1.5TB RAM, 2TB RAM)", "ram_gb": 1024},
    {"category": "server", "category_id": SERVERS, "q": ddr5_query(64, 128, 256, 512), "ram_gb": 512, "ddr5": True},
    {"category": "server", "category_id": SERVERS, "q": LOT_QUERY, "max_price": LOT_MAX_PRICE, "sort": "newlyListed"},
]
COMPUTER_SORT = "price"   # cheapest first (price plus postage)
# Nothing costing under a twentieth of the memory's value is a computer; it keeps accessories out.
FLOOR_FRACTION = 0.05
MIN_PRICE = 10

MAX_CALLS_PER_RUN = 60
