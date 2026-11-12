"""What to search for. One API call per entry, so a run makes len(MEMORY) + len(COMPUTERS) + 1 calls
(the extra one is the token): 19 as it stands, about 230 a day on the two-hourly schedule."""
from __future__ import annotations

# eBay UK category ids. If a search comes back empty on a real run, check the id with eBay's
# Taxonomy API (getCategorySuggestions) and correct it here.
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

# Computers whose titles mention a large memory size, newest first. Each search is capped at the most
# that much memory could be worth, so everything returned is a candidate.
COMPUTERS = [
    {"category": "laptop", "category_id": LAPTOPS, "q": "32GB", "ram_gb": 32},
    {"category": "laptop", "category_id": LAPTOPS, "q": "64GB", "ram_gb": 64},
    {"category": "desktop", "category_id": DESKTOPS, "q": "32GB", "ram_gb": 32},
    {"category": "desktop", "category_id": DESKTOPS, "q": "64GB", "ram_gb": 64},
    {"category": "desktop", "category_id": DESKTOPS, "q": "128GB", "ram_gb": 128},
    {"category": "server", "category_id": SERVERS, "q": "64GB", "ram_gb": 64},
    {"category": "server", "category_id": SERVERS, "q": "128GB", "ram_gb": 128},
    {"category": "server", "category_id": SERVERS, "q": "256GB", "ram_gb": 256},
    {"category": "server", "category_id": SERVERS, "q": "512GB", "ram_gb": 512},
]
COMPUTER_SORT = "newlyListed"

MAX_CALLS_PER_RUN = 40
