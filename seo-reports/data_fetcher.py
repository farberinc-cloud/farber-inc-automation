"""Data fetcher for monthly SEO reports.

Pulls data from GA4, Search Console, and Ubersuggest MCP for a single client
and returns a unified dict ready for the HTML template.
"""
import json
import urllib.request
import urllib.parse
import urllib.error
import pathlib
import time
from datetime import datetime, timedelta


def load_token(name):
    """Load an OAuth token from the Hermes config dir."""
    paths = {
        "google": pathlib.Path("~/AppData/Local/hermes/google_token.json").expanduser(),
        "ubersuggest": pathlib.Path("~/AppData/Local/hermes/ubersuggest_token.json").expanduser(),
    }
    with open(paths[name]) as f:
        return json.load(f)


def api_post(url, body, token_name="google"):
    """POST JSON to a Google API."""
    token = load_token(token_name)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
    req.add_header("Authorization", f"Bearer {token['access_token']}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def api_get(url, token_name="google"):
    """GET from a Google API."""
    token = load_token(token_name)
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token['access_token']}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def mcp_call(tool_name, arguments, token_name="ubersuggest"):
    """Call a Ubersuggest MCP tool."""
    token = load_token(token_name)
    mcp_url = "https://ubersuggest-mcp.neilpatelapi.com/mcp"
    body = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000) % 1000000,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    req = urllib.request.Request(mcp_url, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    req.add_header("Authorization", f"Bearer {token['access_token']}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode()
            for line in text.split("\n"):
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if "result" in data and "content" in data["result"]:
                        content = data["result"]["content"]
                        if content and content[0].get("type") == "text":
                            try:
                                return json.loads(content[0]["text"])
                            except json.JSONDecodeError:
                                return {"raw": content[0]["text"]}
                    return data
            return json.loads(text)
    except urllib.error.HTTPError as e:
        return {"error": e.code, "message": e.read().decode()[:200]}


def fetch_ga4_traffic(property_id, days=30):
    """Fetch GA4 traffic summary for last N days + prior period for comparison."""
    end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days + 1)).strftime("%Y-%m-%d")
    prior_end = (datetime.now() - timedelta(days=days + 1)).strftime("%Y-%m-%d")
    prior_start = (datetime.now() - timedelta(days=days * 2 + 1)).strftime("%Y-%m-%d")

    url = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"

    # Current period: by channel
    body_current = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "metrics": [
            {"name": "sessions"},
            {"name": "totalUsers"},
            {"name": "screenPageViews"},
            {"name": "averageSessionDuration"},
            {"name": "bounceRate"},
        ],
        "dimensions": [{"name": "sessionDefaultChannelGroup"}],
    }
    current = api_post(url, body_current)

    # Prior period: by channel
    body_prior = {
        "dateRanges": [{"startDate": prior_start, "endDate": prior_end}],
        "metrics": [
            {"name": "sessions"},
            {"name": "totalUsers"},
            {"name": "screenPageViews"},
        ],
        "dimensions": [{"name": "sessionDefaultChannelGroup"}],
    }
    prior = api_post(url, body_prior)

    # Top pages (current period)
    body_pages = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "metrics": [
            {"name": "screenPageViews"},
            {"name": "averageSessionDuration"},
        ],
        "dimensions": [{"name": "pagePath"}, {"name": "pageTitle"}],
        "limit": 10,
    }
    pages = api_post(url, body_pages)

    return {
        "current": current,
        "prior": prior,
        "top_pages": pages,
        "date_range": {"start": start, "end": end},
    }


def fetch_search_console(site_url, days=30):
    """Fetch Search Console data: top queries, top pages."""
    end = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days + 3)).strftime("%Y-%m-%d")
    encoded_site = urllib.parse.quote(site_url, safe="")

    # Top queries
    url_queries = f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site}/searchAnalytics/query"
    body_queries = {
        "startDate": start,
        "endDate": end,
        "dimensions": ["query"],
        "rowLimit": 10,
    }
    try:
        queries = api_post(url_queries, body_queries)
    except urllib.error.HTTPError:
        queries = {"rows": []}

    # Top pages
    body_pages = {
        "startDate": start,
        "endDate": end,
        "dimensions": ["page"],
        "rowLimit": 10,
    }
    try:
        sc_pages = api_post(url_queries, body_pages)
    except urllib.error.HTTPError:
        sc_pages = {"rows": []}

    # Daily clicks for trend chart
    body_daily = {
        "startDate": start,
        "endDate": end,
        "dimensions": ["date"],
        "rowLimit": 50,
    }
    try:
        daily = api_post(url_queries, body_daily)
    except urllib.error.HTTPError:
        daily = {"rows": []}

    return {"queries": queries, "pages": sc_pages, "daily": daily, "date_range": {"start": start, "end": end}}


def fetch_ubersuggest(domain):
    """Fetch domain overview from Ubersuggest MCP."""
    overview = mcp_call("domain_overview", {"domain": domain})
    keywords = mcp_call("domain_keywords", {"domain": domain, "limit": 20})
    return {"overview": overview, "keywords": keywords}


def fetch_client_data(slug, business_name, domain, ga4_property_id, days=30):
    """Fetch all data for one client."""
    print(f"  Fetching data for {business_name} ({domain})...")

    ga4 = fetch_ga4_traffic(ga4_property_id, days)
    print(f"    ✓ GA4 traffic")

    sc = fetch_search_console(f"https://{domain}/", days)
    print(f"    ✓ Search Console ({len(sc['queries'].get('rows', []))} queries)")

    try:
        us = fetch_ubersuggest(domain)
        print(f"    ✓ Ubersuggest")
    except Exception as e:
        print(f"    ⚠ Ubersuggest failed: {e}")
        us = {"overview": {}, "keywords": {}}

    return {
        "slug": slug,
        "business_name": business_name,
        "domain": domain,
        "ga4_property_id": ga4_property_id,
        "ga4": ga4,
        "search_console": sc,
        "ubersuggest": us,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "reporting_month": datetime.now().strftime("%B %Y"),
    }


if __name__ == "__main__":
    # Test with Anders NSB
    data = fetch_client_data(
        "anders-nsb",
        "Anders NSB",
        "andersnsb.com",
        "522083745",
    )

    # Save raw data
    out_path = pathlib.Path(__file__).parent / "data" / f"{data['slug']}-{data['reporting_month'].replace(' ', '-')}.json"
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\nSaved: {out_path}")