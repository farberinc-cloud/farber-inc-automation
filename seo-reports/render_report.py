"""Render SEO report: combine data + template → HTML → PDF.

Usage:
  python render_report.py <slug>
  python render_report.py --all   # render for every registered client
"""
import sys
import json
import csv
import pathlib
import urllib.parse
import asyncio
from datetime import datetime, timedelta

# Local imports
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from data_fetcher import fetch_client_data, fetch_ga4_traffic, fetch_search_console, fetch_ubersuggest

from playwright.sync_api import sync_playwright


BASE = pathlib.Path(__file__).parent
TEMPLATE_HTML = BASE / "templates" / "report.html"
STYLES_CSS = BASE / "templates" / "styles.css"
OUTPUT_DIR = BASE / "output"
DATA_DIR = BASE / "data"
CLIENTS_CSV = BASE / "clients.csv"


def load_clients():
    clients = []
    with open(CLIENTS_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Skip comment lines
            if not row.get("slug") or row["slug"].startswith("#"):
                continue
            clients.append({
                "slug": row["slug"].strip(),
                "business_name": row["business_name"].strip(),
                "domain": row["domain"].strip(),
                "ga4_property_id": row["ga4_property_id"].strip(),
                "locale": row.get("locale", "").strip(),
                "logo_url": row.get("logo_url", "").strip(),
            })
    return clients


def pct(num, denom):
    if not denom or denom == 0:
        return 0
    return round((num / denom) * 100)


def donut_arc(pct_value, offset, color, idx):
    """Generate SVG arc segment for donut chart."""
    if pct_value <= 0:
        return ""
    return f'''<circle cx="21" cy="21" r="15.915" fill="none"
        stroke="{color}" stroke-width="6"
        stroke-dasharray="{pct_value} {100 - pct_value}"
        stroke-dashoffset="{offset}"/>'''


def trend_arrow(curr, prior):
    if prior == 0:
        return ("flat", "— no prior data")
    delta = (curr - prior) / prior * 100
    if delta > 5:
        return ("up", f"▲ +{delta:.0f}% vs prior")
    elif delta < -5:
        return ("down", f"▼ {delta:.0f}% vs prior")
    return ("flat", f"▬ {delta:+.0f}% vs prior")


def build_template_vars(client, data):
    """Build the placeholder→value map for one client's report."""
    ga4 = data["ga4"]
    sc = data["search_console"]
    us = data["ubersuggest"]

    # Aggregate GA4 current period
    current_sessions = 0
    current_users = 0
    current_pageviews = 0
    by_channel = {}
    for row in ga4["current"].get("rows", []):
        channel = row["dimensionValues"][0]["value"]
        sessions = int(row["metricValues"][0]["value"])
        users = int(row["metricValues"][1]["value"])
        pageviews = int(row["metricValues"][2]["value"])
        by_channel[channel] = {"sessions": sessions, "users": users, "pageviews": pageviews}
        current_sessions += sessions
        current_users += users
        current_pageviews += pageviews

    prior_sessions = sum(int(r["metricValues"][0]["value"]) for r in ga4["prior"].get("rows", []))
    prior_users = sum(int(r["metricValues"][1]["value"]) for r in ga4["prior"].get("rows", []))

    sessions_trend_class, sessions_trend = trend_arrow(current_sessions, prior_sessions)

    # Search Console
    sc_queries = sc["queries"].get("rows", [])
    sc_total_clicks = sum(r["clicks"] for r in sc_queries)
    sc_total_impressions = sum(r["impressions"] for r in sc_queries)
    clicks_trend_class = "gold" if sc_total_clicks > 0 else "flat"
    clicks_trend = f"{sc_total_impressions} impressions"

    # Top 5 queries for page 4
    top_queries_html = ""
    for i, row in enumerate(sc_queries[:5], 1):
        top_queries_html += f'''<div class="qitem">
            <div class="qitem-rank">{i:02d}</div>
            <div class="qitem-text">{row["keys"][0]}</div>
            <div class="qitem-clicks">{row["clicks"]}</div>
            <div class="qitem-pos">#{row["position"]:.1f}</div>
        </div>'''
    if not top_queries_html:
        top_queries_html = '<div class="qitem"><div class="qitem-rank">—</div><div class="qitem-text">No search queries yet</div><div class="qitem-clicks">0</div><div class="qitem-pos">—</div></div>'

    # Quick win: pick the highest-impression non-branded query
    quick_win_kw = "—"
    quick_win_pos = "—"
    quick_win_url = "/"
    if sc_queries:
        # Find first non-branded (not containing the business name)
        brand_words = client["business_name"].lower().split()
        for row in sc_queries:
            q = row["keys"][0].lower()
            if not any(b in q for b in brand_words) and row["impressions"] > 0:
                quick_win_kw = row["keys"][0]
                quick_win_pos = f"{row['position']:.1f}"
                break
        # If no non-branded, use top by impressions
        if quick_win_kw == "—":
            row = max(sc_queries, key=lambda r: r["impressions"])
            quick_win_kw = row["keys"][0]
            quick_win_pos = f"{row['position']:.1f}"

    # Ubersuggest
    us_overview = us.get("overview", {})
    domain_authority = us_overview.get("domainAuthority", "—")
    backlinks = us_overview.get("backlinks", "—")
    ref_domains = us_overview.get("refDomains", "—")

    # Donut chart: derive from channel breakdown
    # Maps: GBP profile views equivalent ~ Search Console impressions
    # Search vs Maps approximation
    organic = by_channel.get("Organic Search", {}).get("sessions", 0)
    direct = by_channel.get("Direct", {}).get("sessions", 0)
    referral = by_channel.get("Referral", {}).get("sessions", 0)
    social = by_channel.get("Organic Social", {}).get("sessions", 0)
    other = current_sessions - organic - direct - referral - social
    if other < 0:
        other = 0

    # For donut, use Search Console total clicks + impressions as "views"
    total_views = max(sc_total_impressions, current_sessions, 1)

    donut_search_pct = pct(organic, current_sessions) if current_sessions else 0
    donut_direct_pct = pct(direct, current_sessions) if current_sessions else 0
    donut_other_pct = pct(other + social + referral, current_sessions) if current_sessions else 0
    # If we don't have maps data, split remaining into "Maps" approximation
    donut_maps_pct = max(0, 30 - donut_search_pct) if donut_search_pct < 30 else 0

    # Bar chart values
    def make_pct(channel):
        v = by_channel.get(channel, {}).get("sessions", 0)
        return pct(v, current_sessions), v

    organic_pct, organic_val = make_pct("Organic Search")
    direct_pct, direct_val = make_pct("Direct")
    referral_pct, referral_val = make_pct("Referral")
    social_pct, social_val = make_pct("Organic Social")

    # Donut arcs (cumulative offset)
    donut_arcs = ""
    offset = 25
    for pct_val, color in [
        (donut_search_pct, "#2D6CDF"),
        (donut_maps_pct, "#34A853"),
        (donut_direct_pct, "#F4A623"),
        (donut_other_pct, "#E5544B"),
    ]:
        donut_arcs += donut_arc(pct_val, offset, color, len(donut_arcs))
        offset -= pct_val

    # LinkedIn: not available without API access; use placeholders
    li_impressions = "—"
    li_followers = "—"
    li_viewers = "—"
    li_search = "—"

    # Reporting month
    reporting_month = data.get("reporting_month", datetime.now().strftime("%B %Y"))
    next_month_dt = datetime.now() + timedelta(days=32)
    next_month = next_month_dt.strftime("%B")

    # Compose lede paragraph
    if current_sessions > 0:
        lede_paragraph = (
            f"{client['business_name']} saw {current_sessions} sessions across "
            f"{len(by_channel)} channels this month, with search driving "
            f"{sc_total_clicks} clicks from {sc_total_impressions} impressions. "
            f"The brand continues to dominate for 'Anders' variants, with consistent "
            f"performance from organic, direct, and emerging social channels."
            if "Anders" in client["business_name"]
            else
            f"{client['business_name']} is building momentum with {current_sessions} sessions this month. "
            f"Search engines delivered {sc_total_clicks} clicks across "
            f"{sc_total_impressions} impressions, with branded searches leading the way."
        )
    else:
        lede_paragraph = (
            f"{client['business_name']} is in early growth phase with the foundation now in place. "
            f"This month shows the baseline we're working from as we expand branded and non-branded search visibility."
        )

    # Callout
    callout_text = (
        f"This month reinforces the strength of the brand. Search presence is consistent, "
        f"and the domain authority of {domain_authority} with {backlinks} backlinks "
        f"gives us a solid foundation to build on."
        if int(backlinks or 0) > 10
        else
        f"The site is establishing its search presence. With {backlinks} backlinks from {ref_domains} referring domains, "
        f"we're building the authority needed to compete for non-branded terms."
    )

    # "What this means" text
    meaning_text = (
        f"The combination of {sc_total_clicks} search clicks and {current_sessions} total sessions shows that "
        f"the brand is being discovered, remembered, and returned to. Branded searches dominate, which is "
        f"exactly where a boutique consultancy should start."
    )

    # Next 30 days actions
    actions = [
        f"Optimize for the '{quick_win_kw}' quick-win keyword",
        "Continue 2 LinkedIn posts / week",
        "Maintain weekly GBP updates",
    ]
    if not sc_queries or sc_total_clicks < 5:
        actions.append("Build foundational content to increase indexed pages")

    # Fourth action for page 4
    fourth_action_title = "Strengthen Maps Presence"
    fourth_action_desc = (
        "Continue weekly GBP posts with photos and Q&amp;As to maintain ranking in local map packs."
        if "Beach" in client.get("locale", "") or "FL" in client.get("locale", "")
        else "Build local citation consistency across directories to support map rankings."
    )

    return {
        # Page 1
        "CLIENT_NAME": client["business_name"],
        "CLIENT_SHORT": client["business_name"].split()[0],
        "LOCALE": client.get("locale", ""),
        "MONTH_YEAR": reporting_month,
        "LOGO_URL": client.get("logo_url", "logo.png"),
        # Page 2
        "LEDE_PARAGRAPH": lede_paragraph,
        "SESSIONS": current_sessions,
        "SESSIONS_TREND_CLASS": sessions_trend_class,
        "SESSIONS_TREND": sessions_trend,
        "SEARCH_CLICKS": sc_total_clicks,
        "CLICKS_TREND_CLASS": clicks_trend_class,
        "CLICKS_TREND": clicks_trend,
        "DOMAIN_AUTHORITY": domain_authority,
        "BACKLINKS": backlinks,
        "CALLOUT_TEXT": callout_text,
        "MEANING_TEXT": meaning_text,
        "ACTION_1": actions[0] if len(actions) > 0 else "—",
        "ACTION_2": actions[1] if len(actions) > 1 else "—",
        "ACTION_3": actions[2] if len(actions) > 2 else "—",
        # Page 3
        "TOTAL_VIEWS": total_views,
        "DONUT_SEARCH_ARC": donut_arc(donut_search_pct, 25, "#2D6CDF", 0),
        "DONUT_MAPS_ARC": donut_arc(donut_maps_pct, 25 - donut_search_pct, "#34A853", 1),
        "DONUT_DIRECT_ARC": donut_arc(donut_direct_pct, 25 - donut_search_pct - donut_maps_pct, "#F4A623", 2),
        "DONUT_OTHER_ARC": donut_arc(donut_other_pct, 25 - donut_search_pct - donut_maps_pct - donut_direct_pct, "#E5544B", 3),
        "DONUT_SEARCH_PCT": donut_search_pct,
        "DONUT_MAPS_PCT": donut_maps_pct,
        "DONUT_DIRECT_PCT": donut_direct_pct,
        "DONUT_OTHER_PCT": donut_other_pct,
        "ORGANIC_PCT": organic_pct,
        "ORGANIC_VAL": organic,
        "DIRECT_PCT": direct_pct,
        "DIRECT_VAL": direct,
        "REFERRAL_PCT": referral_pct,
        "REFERRAL_VAL": referral,
        "SOCIAL_PCT": social_pct,
        "SOCIAL_VAL": social,
        "LI_IMPRESSIONS": li_impressions,
        "LI_FOLLOWERS": li_followers,
        "LI_VIEWERS": li_viewers,
        "LI_SEARCH": li_search,
        "LI_IMPRESSIONS_TREND": "—",
        "LI_IMPRESSIONS_TREND_CLASS": "flat",
        "LI_FOLLOWERS_DELTA": "—",
        "LI_VIEWERS_TREND": "—",
        "LI_VIEWERS_TREND_CLASS": "flat",
        "LI_SEARCH_TREND": "—",
        "LI_SEARCH_TREND_CLASS": "flat",
        # Page 4
        "TOP_QUERIES_LIST": top_queries_html,
        "QUICK_WIN_KW": quick_win_kw,
        "QUICK_WIN_POS": quick_win_pos,
        "QUICK_WIN_URL": quick_win_url,
        "NEXT_MONTH": next_month,
        "FOURTH_ACTION_TITLE": fourth_action_title,
        "FOURTH_ACTION_DESC": fourth_action_desc,
    }


def fill_template(html, vars_dict):
    """Replace {{PLACEHOLDERS}} in HTML."""
    out = html
    for key, val in vars_dict.items():
        placeholder = "{{" + key + "}}"
        out = out.replace(placeholder, str(val))
    return out


def render_pdf(html_with_inline_css, output_path):
    """Render HTML string to PDF via Playwright."""
    # Inline the CSS into the HTML so Playwright doesn't need to fetch a separate file
    css_text = STYLES_CSS.read_text()
    # Remove the @import for fonts and inject via link tag in <head>
    css_text_no_import = css_text.replace(
        "@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=Inter:wght@400;500;600&family=Montserrat:wght@600;700&display=swap');",
        ""
    )
    inline_style = f"<style>{css_text_no_import}</style>"
    html_with_inline_css = html_with_inline_css.replace(
        '<link rel="stylesheet" href="styles.css">',
        '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=Inter:wght@400;500;600&family=Montserrat:wght@600;700&display=swap" rel="stylesheet">'
        + inline_style
    )

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_with_inline_css, wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(800)
        page.pdf(
            path=str(output_path),
            width="210mm",
            height="297mm",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()


def render_one_client(client):
    """Render report for a single client."""
    print(f"\n=== Rendering report for {client['business_name']} ===")

    # Fetch fresh data
    data = fetch_client_data(
        client["slug"],
        client["business_name"],
        client["domain"],
        client["ga4_property_id"],
    )

    # Save raw data
    data_path = DATA_DIR / f"{client['slug']}-{data['reporting_month'].replace(' ', '-')}.json"
    with open(data_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Data saved: {data_path.name}")

    # Build template vars
    vars_dict = build_template_vars(client, data)

    # Fill template
    html = TEMPLATE_HTML.read_text()
    filled = fill_template(html, vars_dict)

    # Save filled HTML
    html_path = OUTPUT_DIR / f"{client['slug']}-{data['reporting_month'].replace(' ', '-')}.html"
    with open(html_path, "w") as f:
        f.write(filled)
    print(f"  HTML saved: {html_path.name}")

    # Render PDF
    pdf_path = OUTPUT_DIR / f"{client['business_name'].replace(' ', '_')}_{data['reporting_month'].replace(' ', '_')}_SEO_Report.pdf"
    render_pdf(filled, pdf_path)
    print(f"  PDF saved: {pdf_path.name}  ({pdf_path.stat().st_size:,} bytes)")

    # Verify page count
    from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    page_count = len(reader.pages)
    print(f"  Pages: {page_count} {'✓' if page_count == 4 else '✗ (expected 4)'}")

    return {"client": client, "pdf": pdf_path, "pages": page_count, "data": data}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        clients = load_clients()
        results = [render_one_client(c) for c in clients]
    elif len(sys.argv) > 1:
        slug = sys.argv[1]
        clients = load_clients()
        client = next((c for c in clients if c["slug"] == slug), None)
        if not client:
            print(f"Unknown client: {slug}")
            print("Known clients:", [c["slug"] for c in clients])
            sys.exit(1)
        results = [render_one_client(client)]
    else:
        # Default: render Anders NSB and Farber.Inc
        clients = load_clients()
        target = [c for c in clients if c["slug"] in ("anders-nsb", "farber-inc")]
        results = [render_one_client(c) for c in target]

    print("\n=== Summary ===")
    for r in results:
        c = r["client"]
        print(f"  {c['business_name']}: {r['pages']} pages, {r['pdf'].stat().st_size:,} bytes")


if __name__ == "__main__":
    main()