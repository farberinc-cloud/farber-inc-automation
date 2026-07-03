#!/usr/bin/env python
"""Monthly SEO report cron job.

Runs on the 1st of each month, generates the previous month's report
for all registered clients, and pushes them to farber-inc-analytics repo.

Trigger: 1st of each month at 8:00 AM ET
Setup: Add to Hermes cron via desktop app or Windows Task Scheduler.
"""
import sys
import subprocess
import pathlib
from datetime import datetime, timedelta


REPO_ROOT = pathlib.Path(__file__).parent.parent
REPORT_GENERATOR = REPO_ROOT / "seo-reports" / "render_report.py"


def main():
    print(f"[{datetime.now().isoformat()}] Monthly SEO report generation starting...")

    last_month = (datetime.now().replace(day=1) - timedelta(days=1))
    print(f"Reporting period: {last_month.strftime('%B %Y')}")

    result = subprocess.run(
        [sys.executable, str(REPORT_GENERATOR), "--all"],
        cwd=REPORT_GENERATOR.parent,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"FAILED: {result.stderr}")
        return 1

    print(result.stdout)
    print(f"[{datetime.now().isoformat()}] Monthly report generation complete.")

    # Find generated PDFs and push to farber-inc-analytics
    output_dir = REPORT_GENERATOR.parent / "output"
    pdfs = list(output_dir.glob("*_SEO_Report.pdf"))
    print(f"\nGenerated {len(pdfs)} PDFs:")
    for pdf in pdfs:
        size_mb = pdf.stat().st_size / 1024 / 1024
        print(f"  - {pdf.name}  ({size_mb:.2f} MB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
