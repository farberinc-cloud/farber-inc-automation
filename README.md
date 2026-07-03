# Farber.Inc Automation Stack

Self-hosted marketing automation backbone for Farber.Inc Media Group.

## Installed Tools

### ✅ n8n (v2.28.6)
- **What:** Open-source workflow automation (Zapier alternative)
- **Cost:** $0 (vs. $49/mo for Zapier Pro)
- **Install:** `npm install -g n8n`
- **Run:** `n8n start` → opens UI at http://localhost:5678
- **Use cases:**
  - Auto-publish blog posts to CMS when merged to `main`
  - Daily GA4 data pulls to analytics repo
  - Weekly Ubersuggest rank checks
  - Lead capture from website forms → email notifications
  - Social media scheduling (when connected)

### ✅ Prompt Library (awesome-chatgpt-prompts)
- **What:** 1,949 curated ChatGPT prompts
- **Source:** https://github.com/f/awesome-chatgpt-prompts
- **Location:** `prompt-library/`
- **Curated for Farber.Inc:** `prompt-library/farber-inc-curated/` (19 marketing-relevant prompts)
- **Best prompts for our work:**
  - **Advertiser** — campaign development
  - **SEO specialist** — keyword research, optimization
  - **Social Media Manager** — content calendars, posts
  - **Email Marketing** — sequences, broadcasts
  - **Storyteller** — brand narratives
  - **Google Ads Title Copywriter** — ad creative
  - **Title Generator for written pieces** — blog titles

### ✅ Connected Integrations (already working)
- **GitHub** — repo management, content publishing workflows
- **Google OAuth** — GA4 + Search Console data
- **Ubersuggest MCP** — 42 SEO tools
- **Hermes cron** — scheduled jobs

### ⏸️ Deferred (Postponed Until Needed)

| Tool | Why deferred | Reactivation plan |
|------|--------------|-------------------|
| **Listmonk** (email marketing) | Postgres setup complex on Windows | Use mailto: or Mailchimp free tier until volume justifies |
| **Mautic** (full automation) | Overkill at current scale | Add when 5+ clients active |
| **Plausible** (analytics) | We already have GA4 + GSC | Add only if client requires privacy-first analytics |

## ✅ Monthly SEO Report System (LIVE)

**Generates 4-page Farber.Inc-branded PDF reports for clients.**

- **Schedule:** 1st of every month at 8:00 AM ET (Hermes cron `618e5cdfdc9f`)
- **Clients:** Anders NSB, Farber.Inc, Clear Intentions (3 active)
- **Data sources:** GA4 + Search Console + Ubersuggest MCP
- **Output:** PDF (exactly 4 pages, ~450KB each)
- **Location:** `seo-reports/output/<Client>_<Month>_<Year>_SEO_Report.pdf`

### How it works
1. `data_fetcher.py` pulls fresh data from GA4, Search Console, Ubersuggest
2. `render_report.py` fills the HTML template with client data
3. Playwright Chromium renders HTML → PDF
4. `pypdf` verifies the PDF has exactly 4 pages

### Sample output
- `output/Anders_NSB_July_2026_SEO_Report.pdf` (468 KB, 4 pages)
- `output/Farber.Inc_Media_Group_July_2026_SEO_Report.pdf` (452 KB, 4 pages)

### Page structure
1. **Cover** — Navy gradient, client logo, name, locale, month
2. **Executive Summary** — Lede paragraph, 3 metric cards, navy callout, "What This Means" + "Next 30 Days" panels
3. **How People Found You** — Donut chart + bar charts + LinkedIn Performance block
4. **Search & Opportunity** — Top 5 queries, Quick Win card, Focused Items 2×2 grid

### Running manually
```bash
# All clients
python seo-reports/render_report.py --all

# Specific client
python seo-reports/render_report.py anders-nsb
```

## n8n Workflows (To Build)

### High Priority
- [ ] **Daily GA4 → analytics repo:** Pull 7-day traffic data, save as `analytics/daily/YYYY-MM-DD.json`
- [ ] **Weekly Ubersuggest rank check:** Pull top 10 keyword positions for each client, alert on drops > 5
- [x] **Monthly client report:** Auto-generate PDF reports (✅ Done — see above)
- [ ] **AEO monitoring:** Daily check if client content is cited in AI answers (Perplexity, ChatGPT)

### Medium Priority
- [ ] **Blog publish workflow:** When `farber-inc-content` PR merged → publish to website, send notification
- [ ] **Social scheduling:** Buffer/Later API integration (when account set up)
- [ ] **Lead notifications:** Webhook from website forms → Slack/email alert

### Low Priority (Future)
- [ ] **Backlink monitoring:** Daily check for new backlinks via Ubersuggest
- [ ] **Competitor alerts:** When competitor publishes content (via RSS), notify
- [ ] **Auto social posts from blog:** Generate 5 social snippets from each blog post
- [ ] **LinkedIn API integration:** Replace — placeholders on page 3 with real LinkedIn analytics

## Setup Instructions

### Start n8n

```bash
# Default port 5678
n8n start

# Custom port (if 5678 in use)
N8N_PORT=5679 n8n start

# With tunnel (for webhooks)
n8n start --tunnel
```

Then visit **http://localhost:5678** and create your account.

### Connect to Farber.Inc Data Sources

1. **GitHub credentials:** Generate a personal access token at https://github.com/settings/tokens (scopes: `repo`, `workflow`)
2. **Google credentials:** Already saved at `~/AppData/Local/hermes/google_token.json` — n8n's Google node will use this if configured
3. **Ubersuggest:** MCP endpoint at `https://ubersuggest-mcp.neilpatelapi.com/mcp` — n8n can use HTTP Request node + access token from `~/AppData/Local/hermes/ubersuggest_token.json`

### First Workflow (Recommended)

1. Open n8n UI → New workflow
2. Add **Schedule Trigger** node (e.g., every Monday at 9am)
3. Add **HTTP Request** node → GET `https://analyticsdata.googleapis.com/v1beta/properties/528246119:runReport`
   - Header: `Authorization: Bearer <token from disk>`
   - Body: 7-day traffic report
4. Add **Write Binary File** or **HTTP Request to GitHub** node to save result to `farber-inc-analytics/`
5. Test, save, activate

## Cost Savings Summary

| Tool | Replaces | Monthly savings | Annual savings |
|------|----------|-----------------|----------------|
| n8n | Zapier Pro | $49 | $588 |
| Prompt library | Copy.ai / Jasper | $49 | $588 |
| **Total** | | **$98/mo** | **~$1,176/year** |

## Related Docs

- `n8n-data/` — n8n workflow definitions and credentials (encrypted)
- `prompt-library/` — Cloned from awesome-chatgpt-prompts
- `prompt-library/farber-inc-curated/` — Marketing-relevant subset
- `../playbooks/` — SEO, AEO, GEO, Content playbooks that n8n will automate
- `../../cortana-system/` — Sub-agent definitions that n8n will orchestrate

## Notes

- n8n runs as a foreground process. Use `n8n start --tunnel` or set up as a Windows service for production.
- For multi-user access, run behind nginx or Caddy with HTTPS.
- Tokens stored in `~/AppData/Local/hermes/` are reused across all integrations.