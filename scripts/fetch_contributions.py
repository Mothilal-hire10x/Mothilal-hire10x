#!/usr/bin/env python3
"""
Pull real daily contribution counts for the profile and write
data/contributions.json with the raw days plus derived stats (current streak,
longest streak, best day, monthly totals).

Source, in order:
  1. github-contributions-api.jogruber.de -- public JSON mirror of the profile
     calendar, already carries GitHub's 0-4 intensity level per day.
  2. github.com/users/<user>/contributions -- the public HTML fragment the
     profile page itself renders (regex-parsed, no token needed).

Stdlib only, so the daily workflow needs no pip install.
Run daily by .github/workflows/update-profile-art.yml.

    GH_PROFILE_USER=Mothilal-M python scripts/fetch_contributions.py
"""
import datetime
import html
import json
import os
import re
import sys
import urllib.request

USERNAME = os.environ.get("GH_PROFILE_USER", "Mothilal-M")
API_URL = f"https://github-contributions-api.jogruber.de/v4/{USERNAME}?y=last"
HTML_URL = f"https://github.com/users/{USERNAME}/contributions"
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "contributions.json")
UA = {"User-Agent": "profile-readme-bot/1.0 (+https://github.com/Mothilal-M)"}


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch_api():
    data = json.loads(_get(API_URL))
    days = [{"date": d["date"], "count": int(d["count"]), "level": int(d["level"])}
            for d in data["contributions"]]
    if not days:
        raise ValueError("api returned no days")
    return days


def fetch_html():
    page = _get(HTML_URL)
    # <td ... data-date="2026-05-15" id="contribution-day-component-5-36" data-level="4" ...>
    cells = {}
    for m in re.finditer(r"<td\b[^>]*\bdata-date=\"(\d{4}-\d{2}-\d{2})\"[^>]*>", page):
        tag = m.group(0)
        lvl = re.search(r"data-level=\"(\d)\"", tag)
        cid = re.search(r"\bid=\"([^\"]+)\"", tag)
        cells[m.group(1)] = {"level": int(lvl.group(1)) if lvl else 0,
                             "id": cid.group(1) if cid else None}
    if not cells:
        raise ValueError("no calendar cells found -- github markup may have changed")
    # <tool-tip ... for="contribution-day-component-5-36" ...>29 contributions on May 15th.</tool-tip>
    tips = {}
    for m in re.finditer(r"<tool-tip\b[^>]*\bfor=\"([^\"]+)\"[^>]*>(.*?)</tool-tip>", page, re.S):
        tips[m.group(1)] = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
    days = []
    for date, c in cells.items():
        text = tips.get(c["id"], "")
        if re.search(r"no contributions", text, re.I):
            count = 0
        else:
            n = re.match(r"(\d[\d,]*)", text)
            count = int(n.group(1).replace(",", "")) if n else 0
        days.append({"date": date, "count": count, "level": c["level"]})
    return days


def fetch_days():
    if os.environ.get("FORCE_HTML"):
        return sorted(fetch_html(), key=lambda d: d["date"]), "html"
    try:
        days = fetch_api()
        src = "api"
    except Exception as e:                       # any failure -> fall back to scraping
        print(f"api failed ({e}); scraping github.com instead", file=sys.stderr)
        days = fetch_html()
        src = "html"
    days.sort(key=lambda d: d["date"])
    return days, src


def compute_current_streak(days):
    idx = len(days) - 1
    if days[idx]["count"] == 0:
        idx -= 1                                  # today isn't over yet -- don't break the streak on it
    streak = 0
    end_idx = idx
    while idx >= 0 and days[idx]["count"] > 0:
        streak += 1
        idx -= 1
    if streak == 0:
        return 0, None, None
    return streak, days[idx + 1]["date"], days[end_idx]["date"]


def compute_longest_streak(days):
    longest = run = 0
    longest_start = longest_end = None
    run_start = None
    for i, d in enumerate(days):
        if d["count"] > 0:
            if run == 0:
                run_start = i
            run += 1
            if run > longest:
                longest, longest_start, longest_end = run, days[run_start]["date"], d["date"]
        else:
            run = 0
    return longest, longest_start, longest_end


def build_data(days, source):
    total = sum(d["count"] for d in days)
    active_days = sum(1 for d in days if d["count"] > 0)
    best = max(days, key=lambda d: d["count"])
    cur_len, cur_start, cur_end = compute_current_streak(days)
    long_len, long_start, long_end = compute_longest_streak(days)

    monthly = {}
    for d in days:
        monthly[d["date"][:7]] = monthly.get(d["date"][:7], 0) + d["count"]

    return {
        "username": USERNAME,
        "source": source,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "range": {"start": days[0]["date"], "end": days[-1]["date"]},
        "total_contributions": total,
        "active_days": active_days,
        "avg_per_active_day": round(total / active_days, 1) if active_days else 0,
        "current_streak": {"length": cur_len, "start": cur_start, "end": cur_end},
        "longest_streak": {"length": long_len, "start": long_start, "end": long_end},
        "best_day": {"date": best["date"], "count": best["count"]},
        "monthly": [{"month": k, "total": v} for k, v in sorted(monthly.items())],
        "days": days,
    }


if __name__ == "__main__":
    days, source = fetch_days()
    data = build_data(days, source)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"wrote {os.path.relpath(OUT_PATH)} [{source}]: {data['total_contributions']} contributions, "
          f"current streak {data['current_streak']['length']}, "
          f"longest streak {data['longest_streak']['length']}")
