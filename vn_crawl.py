#!/usr/bin/env python3
"""
Crawl .NET / C# jobs in VIETNAM (domestic — no English wall) from LinkedIn guest API
(+ best-effort ITviec), tag level/remote/part-time/Vietnamese-only, keep junior/middle/fresher
that fit a ~2yr dev looking for a 2nd job. Output docs/vn-jobs.json for the Pages board.

Runs on GitHub Actions (US IP) or machine 150 (VN IP). LinkedIn guest API is global.
"""
import os, re, sys, json, html, time
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TIMEOUT = 25

# (keyword, extra filter) — f_WT=2 remote, f_JT=P part-time C contract, f_TPR=r2592000 last 30d
LI_QUERIES = [
    (".NET", ""), ("C# developer", ""), ("ASP.NET", ""), ("dotnet", ""),
    (".NET", "&f_WT=2"),            # remote
    (".NET", "&f_JT=P,C"),          # part-time / contract
    ("C# developer", "&f_WT=2"),
]
LI_LOCATIONS = ["Vietnam"]

SENIOR = ["senior", "sr ", "sr.", "lead", "principal", "manager", "head", "director",
          "architect", "techlead", "tech lead", "expert", "chief", "trưởng"]
LEVELS = [("fresher", ["fresher", "intern", "thực tập", "sinh viên"]),
          ("junior", ["junior", "jr "]),
          ("middle", ["middle", "mid-level", "mid level", "middle/senior"])]


def level_of(title):
    t = title.lower()
    for name, kws in LEVELS:
        if any(k in t for k in kws):
            return name
    return "unspecified"


def is_senior(title):
    t = title.lower()
    return any(k in t for k in SENIOR)


def clean(u):
    return (u or "").split("?")[0]


def fetch_linkedin():
    out, seen = [], set()
    for loc in LI_LOCATIONS:
        for kw, filt in LI_QUERIES:
            for start in (0, 10, 20):
                url = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                       f"?keywords={requests.utils.quote(kw)}&location={requests.utils.quote(loc)}"
                       f"&f_TPR=r2592000{filt}&start={start}")
                try:
                    r = requests.get(url, headers=UA, timeout=TIMEOUT)
                    if r.status_code != 200 or not r.text.strip():
                        break
                    cards = re.findall(r"<li>(.*?)</li>", r.text, re.S)
                    if not cards:
                        break
                    for c in cards:
                        title = re.search(r'base-search-card__title">\s*(.*?)\s*</h3>', c, re.S)
                        comp = re.search(r'base-search-card__subtitle">\s*<a[^>]*>\s*(.*?)\s*</a>', c, re.S)
                        locm = re.search(r'job-search-card__location">\s*(.*?)\s*</span>', c, re.S)
                        link = re.search(r'href="(https://[^"]*?/jobs/view/[^"]+)"', c)
                        if not title:
                            continue
                        t = html.unescape(title.group(1).strip())
                        u = clean(link.group(1)) if link else ""
                        key = u or t
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append({
                            "title": t,
                            "company": html.unescape(comp.group(1).strip()) if comp else "",
                            "location": html.unescape(locm.group(1).strip()) if locm else "Vietnam",
                            "url": u, "source": "linkedin",
                            "remote_hint": ("&f_WT=2" in filt),
                            "pt_hint": ("f_JT=P" in filt),
                        })
                    time.sleep(0.4)
                except Exception as e:
                    print("linkedin ERR", kw, e, file=sys.stderr)
                    break
    return out


def fetch_itviec():
    out = []
    try:
        for slug in ("dot-net", "c-sharp", "asp-net"):
            r = requests.get(f"https://itviec.com/it-jobs/{slug}", headers=UA, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            for m in re.finditer(r'<h3[^>]*>\s*<a[^>]*href="(/it-jobs/[^"]+)"[^>]*>\s*(.*?)\s*</a>', r.text, re.S):
                out.append({"title": html.unescape(re.sub(r"<[^>]+>", "", m.group(2)).strip()),
                            "company": "", "location": "Vietnam",
                            "url": "https://itviec.com" + m.group(1),
                            "source": "itviec", "remote_hint": False, "pt_hint": False})
            time.sleep(0.4)
    except Exception as e:
        print("itviec ERR", e, file=sys.stderr)
    return out


def main():
    raw = fetch_linkedin()
    print("linkedin:", len(raw))
    it = fetch_itviec()
    print("itviec:", len(it))
    raw += it

    # dedupe + tag
    seen, jobs = set(), []
    for r in raw:
        key = r["url"] or (r["title"] + r["company"])
        if key in seen:
            continue
        seen.add(key)
        t = r["title"]
        loc = r["location"]
        r["level"] = level_of(t)
        r["senior"] = is_senior(t)
        r["remote"] = r.get("remote_hint") or bool(re.search(r"remote|từ xa|wfh", (t + " " + loc).lower()))
        r["part_time"] = r.get("pt_hint") or bool(re.search(r"part[- ]?time|bán thời gian", t.lower()))
        r["vietnamese_only"] = bool(re.search(r"vietnamese only|tiếng việt|người việt", (t).lower()))
        r["night"] = bool(re.search(r"night[- ]?shift|ca đêm|graveyard|âm phủ|us hours|"
                                    r"us time|emea|overnight|0:00|2:00 ?am|đêm", (t + " " + loc).lower()))
        r["fit"] = not r["senior"]
        jobs.append({k: r[k] for k in ("title", "company", "location", "url", "source",
                                       "level", "senior", "remote", "part_time",
                                       "vietnamese_only", "night", "fit")})

    # sort: fit (junior/mid) first, then remote, then part-time
    jobs.sort(key=lambda x: (x["senior"], not x["remote"], not x["part_time"], x["title"].lower()))

    out = os.environ.get("JSON_OUT", "docs/vn-jobs.json")
    d = os.path.dirname(out)
    if d:
        os.makedirs(d, exist_ok=True)
    payload = {"count": len(jobs),
               "fit": sum(1 for j in jobs if j["fit"]),
               "remote": sum(1 for j in jobs if j["remote"]),
               "jobs": jobs}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"wrote {out}: {len(jobs)} VN .NET jobs ({payload['fit']} fit, {payload['remote']} remote)")


if __name__ == "__main__":
    main()
