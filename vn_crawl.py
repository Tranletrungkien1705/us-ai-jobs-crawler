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
LI_LOCATIONS = ["Hanoi, Vietnam"]   # focus Hà Nội (distance=30mi ~ 50km)

# Hà Nội + vùng bán kính ~50km (để lọc client-side vì LinkedIn hay trả cả nước)
HANOI_KW = ["hà nội", "ha noi", "hanoi", "capital region", "gia lâm", "gia lam",
            "long biên", "long bien", "cầu giấy", "cau giay", "đống đa", "dong da",
            "hai bà trưng", "thanh xuân", "thanh xuan", "hoàng mai", "từ liêm", "tu liem",
            "hà đông", "ha dong", "hoàn kiếm", "hoan kiem", "tây hồ", "ba đình", "ba dinh",
            "bắc ninh", "bac ninh", "hưng yên", "hung yen"]

SENIOR = ["senior", "sr ", "sr.", "lead", "principal", "manager", "head", "director",
          "architect", "techlead", "tech lead", "expert", "chief", "trưởng"]
LEVELS = [("fresher", ["fresher", "intern", "thực tập", "sinh viên"]),
          ("junior", ["junior", "jr "]),
          ("middle", ["middle", "mid-level", "mid level", "middle/senior"])]


# ĐÚNG mảng của bạn: C#/.NET/SQL
RELEVANT_CORE = ["c#", "c-sharp", "csharp", ".net", "dotnet", "asp.net", "sql"]
# LOẠI ngôn ngữ/stack KHÔNG phải của bạn (C/C++, Java, Python, mobile, game, BrSE-Nhật...)
EXCLUDE_RE = re.compile(
    r"(c\+\+|c/c|\bjava\b|\bphp\b|\bpython\b|\bgolang\b|\bruby\b|\brust\b|\bkotlin\b|"
    r"\bscala\b|\bswift\b|cocos|unity|unreal|\bbrse\b|cầu nối|embedded|firmware|"
    r"flutter|react native|\breactjs\b|\bangular\b|\bvuejs\b|\bgame\b|\btester\b|"
    r"\bqc\b|japanese|tiếng nhật|nhật bản|\bdesigner\b|front-?end)", re.I)


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
                       f"&distance=30&f_TPR=r2592000{filt}&start={start}")
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


def li_desc(url):
    """Đọc mô tả job từ LinkedIn guest jobPosting endpoint (để bắt năm KN + English)."""
    m = re.search(r"(\d{8,})", url or "")   # job-id LinkedIn = số ~10 chữ số cuối url
    if not m:
        return ""
    try:
        r = requests.get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}",
                         headers=UA, timeout=TIMEOUT)
        if r.status_code == 200:
            return html.unescape(re.sub(r"<[^>]+>", " ", r.text))
    except Exception:
        pass
    return ""


ENGLISH_RE = re.compile(
    r"good (at |command of )?english|fluent(ly)?( in)? english|excellent english|strong english|"
    r"english (communication|proficiency|fluency|skills|is a must|required)|"
    r"proficient in english|tiếng anh (tốt|khá|thành thạo|giao tiếp)", re.I)


def desc_flags(desc):
    yrs = [int(x) for x in re.findall(r"(\d{1,2})\s*\+?\s*years", desc or "", re.I) if 1 <= int(x) <= 15]
    min_years = min(yrs) if yrs else 0        # ngưỡng KN tối thiểu job đòi
    return min_years, bool(desc and ENGLISH_RE.search(desc))


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
        if EXCLUDE_RE.search(t):        # loại C/C++/Java/mobile/game/BrSE...
            continue
        loc = r["location"]
        r["relevant"] = any(k in t.lower() for k in RELEVANT_CORE)  # đúng C#/.NET/SQL
        r["level"] = level_of(t)
        my, eng = (0, False)
        if r["source"] == "linkedin":
            my, eng = desc_flags(li_desc(r["url"]))  # ĐỌC MÔ TẢ: năm KN + English
            time.sleep(0.25)
        r["min_years"] = my
        r["needs_english"] = eng
        r["over_exp"] = my >= 4                       # job đòi ≥4 năm = quá tầm (bạn ~2 năm)
        r["senior"] = is_senior(t) or r["over_exp"]
        r["remote"] = r.get("remote_hint") or bool(re.search(r"remote|từ xa|wfh", (t + " " + loc).lower()))
        r["part_time"] = r.get("pt_hint") or bool(re.search(r"part[- ]?time|bán thời gian", t.lower()))
        r["vietnamese_only"] = bool(re.search(r"vietnamese only|tiếng việt|người việt", (t).lower()))
        r["night"] = bool(re.search(r"night[- ]?shift|ca đêm|graveyard|âm phủ|us hours|"
                                    r"us time|emea|overnight|0:00|2:00 ?am|đêm", (t + " " + loc).lower()))
        r["hanoi"] = r["remote"] or any(k in loc.lower() for k in HANOI_KW)
        r["junior_up"] = r["level"] != "fresher"   # bỏ fresher/intern
        r["fit"] = not r["senior"]
        jobs.append({k: r[k] for k in ("title", "company", "location", "url", "source",
                                       "level", "senior", "remote", "part_time",
                                       "vietnamese_only", "night", "hanoi", "junior_up",
                                       "relevant", "min_years", "needs_english", "fit")})

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
