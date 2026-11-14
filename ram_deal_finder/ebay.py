"""eBay's official Browse API, and nothing else: an application token, then item_summary/search.

Docs: https://developer.ebay.com/develop/api/buy/browse_api/item_summary/search
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"
MARKETPLACE = "EBAY_GB"
PAGE_SIZE = 200  # the API's maximum


class EbayError(RuntimeError):
    pass


class EbayClient:
    """Counts its own calls and refuses to go past max_calls, so a bug can't eat the daily allowance."""

    def __init__(self, client_id: str, client_secret: str, campaign_id: str | None = None, *,
                 max_calls: int = 40, opener=urllib.request.urlopen, sleep=time.sleep):
        if not client_id or not client_secret:
            raise EbayError("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are not set (see README).")
        self._basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        self.campaign_id = campaign_id or None
        self.max_calls = max_calls
        self.calls = 0
        self._opener = opener
        self._sleep = sleep
        self._token: str | None = None

    def _send(self, request: urllib.request.Request) -> dict:
        for attempt in range(3):
            if self.calls >= self.max_calls:
                raise EbayError(f"Stopped at {self.max_calls} API calls in one run.")
            self.calls += 1
            try:
                with self._opener(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                if err.code < 500 or attempt == 2:
                    detail = err.read().decode("utf-8", "replace")[:300]
                    raise EbayError(f"eBay answered HTTP {err.code}: {detail}") from None
            except urllib.error.URLError as err:
                if attempt == 2:
                    raise EbayError(f"Could not reach eBay: {err.reason}") from None
            self._sleep(2 ** attempt)
        raise EbayError("unreachable")

    def token(self) -> str:
        if self._token is None:
            body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": SCOPE}).encode()
            request = urllib.request.Request(TOKEN_URL, data=body, method="POST", headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {self._basic}",
            })
            token = self._send(request).get("access_token")
            if not token:
                raise EbayError("eBay returned no access token.")
            self._token = token
        return self._token

    def search(self, q: str, category_id: str | None = None, filters: str | None = None,
               sort: str | None = None, limit: int = PAGE_SIZE, offset: int = 0) -> list[dict]:
        """One page of item summaries. Buy It Now listings only: that is the API's default."""
        params = {"q": q, "limit": str(limit)}
        if offset:
            params["offset"] = str(offset)
        if category_id:
            params["category_ids"] = category_id
        if filters:
            params["filter"] = filters
        if sort:
            params["sort"] = sort
        context = "contextualLocation=" + urllib.parse.quote("country=GB", safe="")
        if self.campaign_id:
            context = f"affiliateCampaignId={self.campaign_id}," + context
        request = urllib.request.Request(SEARCH_URL + "?" + urllib.parse.urlencode(params), headers={
            "Authorization": f"Bearer {self.token()}",
            "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE,
            "X-EBAY-C-ENDUSERCTX": context,
            "Accept": "application/json",
        })
        return self._send(request).get("itemSummaries") or []


class FixtureClient:
    """Answers searches from a JSON file: {"<category id>|<q>": [item summaries]}. No network."""

    campaign_id = None

    def __init__(self, path):
        with open(path, encoding="utf-8") as handle:
            self._responses = json.load(handle)
        self.calls = 0

    def search(self, q: str, category_id: str | None = None, filters: str | None = None,
               sort: str | None = None, limit: int = PAGE_SIZE, offset: int = 0) -> list[dict]:
        self.calls += 1
        return self._responses.get(f"{category_id or ''}|{q}", [])[offset:offset + limit]
