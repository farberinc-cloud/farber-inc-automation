# Farber.Inc Automation

Scheduled jobs, GitHub Actions workflows, and publishing pipelines that run without human intervention.

## Structure

```
automation/
├── github-actions/    — .github/workflows/*.yml files (copy into each content repo)
├── hermes-cron/       — Hermes cron job specs (deployed via Hermes desktop)
├── scripts/           — Python/JS automation scripts
└── README.md          — this file
```

## Workflows

### Content publishing pipeline

1. **Cron triggers** content draft generation (e.g., weekly blog post)
2. **Draft** lands in `farber-inc-content` PR
3. **Review** by Randy/client reviewer (auto-assigned based on file path)
4. **Approve & merge** → triggers publish workflow
5. **Publish** to website (CMS API), social (Buffer/Later), email (Mailchimp)

### AEO monitoring

- Daily cron: query Perplexity/ChatGPT/Google AI Overviews for client keywords
- Track which sources get cited
- Flag drops (client content used to be cited, now isn't)
- Output: `analytics/seo/aeo-tracking-YYYY-MM.csv`

### SEO monitoring

- Weekly cron: pull GSC data, rank tracking, backlink updates
- Detect keyword position changes > 5
- Alert if technical SEO issues appear (crawl errors, page speed regressions)

### Analytics aggregation

- Monthly cron: generate client PDF reports from raw data
- Email to client with summary
- Archive in `farber-inc-analytics/reports/<client>/YYYY-MM.pdf`

## Setup

GitHub Actions files in `github-actions/` are templates — copy into the relevant repo's `.github/workflows/` directory and configure secrets.

Hermes cron jobs in `hermes-cron/` are managed via the Hermes desktop app's cron system.

## Secrets required (per repo)

| Secret | Purpose |
|--------|---------|
| `GITHUB_TOKEN` | already in this profile |
| `BUFFER_API_KEY` | social scheduling (when ready) |
| `MAILCHIMP_API_KEY` | email sends (when ready) |
| `CMS_API_KEY` | website publishing (per client) |
| `OPENAI_API_KEY` | LLM calls for content generation |

## Related repos

- **cortana-system** — agents, workflows, playbooks
- **farber-inc-content** — content drafts and publishing targets
- **farber-inc-analytics** — data outputs and reports