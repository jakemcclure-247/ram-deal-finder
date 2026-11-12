"""py -m ram_deal_finder run [--fixtures FILE] [--out FILE]   |   py -m ram_deal_finder check"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import config
from .ebay import EbayClient, FixtureClient
from .feed import run

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path) -> None:
    """KEY=VALUE lines from .env; anything already in the environment wins."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def live_client() -> EbayClient:
    load_env(ROOT / ".env")
    return EbayClient(os.environ.get("EBAY_CLIENT_ID", ""), os.environ.get("EBAY_CLIENT_SECRET", ""),
                      os.environ.get("EPN_CAMPAIGN_ID", "").strip() or None, max_calls=config.MAX_CALLS_PER_RUN)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ram_deal_finder")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="search eBay UK and write the feed")
    run_parser.add_argument("--fixtures", help="answer searches from this JSON file instead of eBay (no network)")
    run_parser.add_argument("--out", help="feed path (default data/deals.json; data/deals.fixture.json with --fixtures)")
    commands.add_parser("check", help="get a token and make one search, to prove the keys work")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        if args.command == "check":
            client = live_client()
            found = client.search("DDR4 SODIMM", config.MEMORY_CAT, config.MEMORY_FILTER, limit=3)
            print(f"Keys work: token issued and a search returned {len(found)} listings.")
            return 0
        if args.fixtures:
            # Invented listings: never written over the real feed unless --out says so.
            run(FixtureClient(args.fixtures), args.out or ROOT / "data" / "deals.fixture.json")
        else:
            run(live_client(), args.out or ROOT / "data" / "deals.json")
        return 0
    except Exception as err:  # the previous feed stays as it was
        print(f"Run failed, feed left untouched: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
