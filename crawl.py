#!/usr/bin/env python3
"""
Crawl remote/US jobs that AI can realistically REPLACE (automatable knowledge work),
tag them, and upsert into a free Supabase table. Designed to run on GitHub Actions (US runner).

Env:
  SUPABASE_URL  e.g. https://xxxx.supabase.co
  SUPABASE_KEY  service/secret key (sb_secret_... or service_role) - bypasses RLS
"""
import os, re, sys, json, hashlib, datetime, sqlite3
import xml.etree.ElementTree as ET
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) job-crawler"}
TIMEOUT = 30

# --- job families AI can realistically do the work of ("ngon" = tri-thuc, luong tot) ---
REPL = [
    # writing / content
    "content", "copywrit", "copy editor", "writer", "blog", "article", "ghostwrit",
    "technical writer", "ux writer", "scriptwrit", "grant writer", "newsletter",
    "editor", "proofread", "product description", "documentation", "localization",
    # data / annotation
    "data entry", "annotat", "data label", "labeling", "transcri", "translat", "captioning",
    "subtitle", "tagging", "categoriz", "survey", "data processing",
    # support / VA / admin
    "virtual assistant", "administrative assistant", "executive assistant", "admin assistant",
    "customer support", "customer service", "customer success", "chat support", "email support",
    "help desk", "helpdesk", "support specialist", "moderat", "scheduler", "data clerk",
    # marketing / sales
    "marketing", "marketer", "seo", "social media", "community", "email marketing",
    "market research", "research assistant", "appointment setter", "outreach", "lead gen",
    "sales development", "sdr", "bdr", "account manager", "cold call",
    # finance / hr / legal (clerical)
    "bookkeep", "accounts payable", "accounting clerk", "recruit", "sourcer", "paralegal",
    # design / media / education
    "graphic design", "presentation", "powerpoint", "video edit", "voice over",
    "tutor", "english teacher", "curriculum",
    # analytics / qa
    "data analyst", "qa tester", "quality analyst", "reviewer", "curator", "prompt",
]
# jobs that are ABOUT building AI (informational tag)
AISKILL = ["ai", "ml", "llm", "gpt", "prompt", "machine learning", "nlp", "data scien", "generative"]

US_HINTS = ["us", "u.s", "united states", "usa", "america", "worldwide", "anywhere", "remote"]


# kem chat luong: chi match REPL trong TITLE (tags cua Lemon.io/... la list da danh muc -> nhieu)
def kw_hits(title, tags):
    tl = (title or "").lower()
    blob = f"{title} {tags}".lower()
    repl = sorted({k for k in REPL if k in tl})
    ai = sorted({k for k in AISKILL if re.search(r"\b" + re.escape(k) + r"\b", blob)})
    return repl, ai


def is_us(loc):
    l = (loc or "").lower().strip()
    if l == "":
        return True
    return any(h in l for h in US_HINTS)


def jid(source, raw):
    return f"{source}:{raw}" if raw else f"{source}:" + hashlib.md5(raw.encode() if raw else b'').hexdigest()[:12]


def norm(source, title, company, location, salary, tags, url, raw_id, desc=""):
    return {
        "job_id": jid(source, str(raw_id or url)),
        "source": source,
        "title": (title or "").strip()[:300],
        "company": (company or "").strip()[:200],
        "location": (location or "").strip()[:200],
        "salary": (str(salary).strip()[:120] if salary else None),
        "tags": (tags or "").strip()[:500],
        "url": (url or "").strip()[:600],
        "_desc": (desc or "")[:6000],   # chi de quet needs_speaking; KHONG luu DB
    }


# tin hieu "phai NOI tieng Anh" trong mo ta job
SPEAK_RE = re.compile(
    r"\b(verbal|spoken english|fluent(ly)?\s+(in\s+)?english|native(\s+level)?\s+english|"
    r"phone call|video call|on calls|cold call|answer(ing)? calls|calls with|"
    r"speaking skills|verbal communication|excellent communication skills|"
    r"present to|presenting to|client-facing|customer-facing|stakeholder)\b", re.I)
# nghe theo TITLE luon can noi nhieu
SPEAK_TITLE = ["customer support", "customer service", "customer success", "account manager",
               "account executive", "sales development", "sdr", "bdr", "cold call", "tutor",
               "teacher", "recruiter", "community", "success manager", "sales manager",
               "appointment", "outreach", "interpreter", "voice"]


def needs_speaking(title, desc):
    t = (title or "").lower()
    if any(k in t for k in SPEAK_TITLE):
        return True
    if desc and SPEAK_RE.search(desc):
        return True
    return False


def fetch_remoteok():
    out = []
    try:
        d = requests.get("https://remoteok.com/api", headers=UA, timeout=TIMEOUT).json()
        for j in d:
            if not isinstance(j, dict) or "position" not in j:
                continue
            out.append(norm("remoteok", j.get("position"), j.get("company"),
                            j.get("location"), j.get("salary_min"),
                            " ".join(j.get("tags", []) or []), j.get("url"), j.get("id"),
                            desc=j.get("description", "")))
    except Exception as e:
        print("remoteok ERR", e, file=sys.stderr)
    return out


def fetch_remotive():
    out = []
    try:
        d = requests.get("https://remotive.com/api/remote-jobs", headers=UA, timeout=TIMEOUT).json()
        for j in d.get("jobs", []):
            out.append(norm("remotive", j.get("title"), j.get("company_name"),
                            j.get("candidate_required_location"), j.get("salary"),
                            " ".join(j.get("tags", []) or []), j.get("url"), j.get("id"),
                            desc=j.get("description", "")))
    except Exception as e:
        print("remotive ERR", e, file=sys.stderr)
    return out


def fetch_arbeitnow():
    out = []
    for page in range(1, 5):  # phan trang de lay nhieu hon
        try:
            d = requests.get(f"https://www.arbeitnow.com/api/job-board-api?page={page}",
                             headers=UA, timeout=TIMEOUT).json()
            data = d.get("data", [])
            if not data:
                break
            for j in data:
                loc = j.get("location") or ("Remote" if j.get("remote") else "")
                out.append(norm("arbeitnow", j.get("title"), j.get("company_name"),
                                loc, None, " ".join(j.get("tags", []) or []),
                                j.get("url"), j.get("slug"), desc=j.get("description", "")))
        except Exception as e:
            print(f"arbeitnow p{page} ERR", e, file=sys.stderr)
            break
    return out


def fetch_jobicy():
    out = []
    try:
        d = requests.get("https://jobicy.com/api/v2/remote-jobs?count=50", headers=UA, timeout=TIMEOUT).json()
        for j in d.get("jobs", []):
            sal = None
            if j.get("annualSalaryMin"):
                sal = f"${j.get('annualSalaryMin')}-{j.get('annualSalaryMax')} {j.get('salaryCurrency','')}".strip()
            ind = j.get("jobIndustry")
            tags = " ".join(ind) if isinstance(ind, list) else str(ind or "")
            out.append(norm("jobicy", j.get("jobTitle"), j.get("companyName"),
                            j.get("jobGeo") or "Anywhere", sal, tags, j.get("url"), j.get("id"),
                            desc=j.get("jobDescription") or j.get("jobExcerpt") or ""))
    except Exception as e:
        print("jobicy ERR", e, file=sys.stderr)
    return out


def fetch_himalayas():
    out = []
    try:
        d = requests.get("https://himalayas.app/jobs/api?limit=100", headers=UA, timeout=TIMEOUT).json()
        for j in d.get("jobs", []):
            loc = j.get("locationRestrictions") or []
            loc = ", ".join(loc) if isinstance(loc, list) else str(loc)
            out.append(norm("himalayas", j.get("title"), j.get("companyName"),
                            loc, j.get("maxSalary"),
                            " ".join(j.get("categories", []) or []),
                            j.get("applicationLink") or j.get("guid"), j.get("guid"),
                            desc=j.get("description") or j.get("excerpt") or ""))
    except Exception as e:
        print("himalayas ERR", e, file=sys.stderr)
    return out


COLS = ["job_id", "source", "title", "company", "location", "region", "is_us",
        "salary", "tags", "url", "repl_kw", "ai_skill_kw", "crawled_at"]


def store_sqlite(rows, path):
    con = sqlite3.connect(path)
    con.execute("""create table if not exists us_ai_jobs (
        job_id text primary key, source text, title text, company text,
        location text, region text, is_us integer, salary text, tags text,
        url text, repl_kw text, ai_skill_kw text,
        first_seen text default (datetime('now')), crawled_at text)""")
    n = 0
    for r in rows:
        vals = [int(r[c]) if c == "is_us" else r.get(c) for c in COLS]
        ph = ",".join("?" * len(COLS))
        upd = ",".join(f"{c}=excluded.{c}" for c in COLS if c not in ("job_id", "first_seen"))
        con.execute(f"insert into us_ai_jobs ({','.join(COLS)}) values ({ph}) "
                    f"on conflict(job_id) do update set {upd}", vals)
        n += 1
    con.commit()
    total = con.execute("select count(*) from us_ai_jobs").fetchone()[0]
    con.close()
    print(f"\nSQLite {path}: upserted {n}, table now has {total} rows.")


def _rec(r):
    sal = r.get("salary") or ""
    sal = sal.strip() if isinstance(sal, str) else str(sal)
    return {
        "job_id": r.get("job_id"),
        "title": r["title"], "company": r["company"], "region": r.get("region") or "(unspecified)",
        "salary": sal or None, "has_salary": bool(sal),
        "repl_kw": r.get("repl_kw", ""), "ai_skill_kw": r.get("ai_skill_kw", ""),
        "needs_speaking": bool(r.get("needs_speaking")),
        "source": r["source"], "url": r["url"], "crawled_at": r.get("crawled_at"),
    }


def write_json(rows, path):
    cur = {}
    for r in rows:
        if r.get("is_us"):
            cur[r.get("url") or r.get("job_id")] = _rec(r)
    # gop file cu -> tich luy nhieu ngay (ban hien tai thang)
    if os.path.exists(path):
        try:
            prev = json.load(open(path, encoding="utf-8")).get("jobs", [])
            for p in prev:
                k = p.get("url") or p.get("job_id")
                if k and k not in cur:
                    cur[k] = p
        except Exception as e:
            print("merge prev ERR", e, file=sys.stderr)
    data = list(cur.values())
    data.sort(key=lambda x: (x.get("crawled_at") or ""), reverse=True)          # moi truoc
    data.sort(key=lambda x: (not x.get("has_salary"), bool(x.get("needs_speaking"))))  # co luong + it-noi len dau
    data = data[:500]
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    updated = max((r["crawled_at"] for r in rows if r.get("crawled_at")), default=None)
    sal_n = sum(1 for x in data if x["has_salary"])
    low_n = sum(1 for x in data if not x.get("needs_speaking"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"updated": updated, "count": len(data), "salaried": sal_n,
                   "low_english": low_n, "jobs": data}, f, ensure_ascii=False, indent=1)
    print(f"wrote {path}: {len(data)} US jobs ({sal_n} salaried, {low_n} it-noi-TA)")


# --- ATS cong ty (Greenhouse) — token da verify tra jobs ---
GH_BOARDS = {
    "duolingo": "Duolingo", "webflow": "Webflow", "coursera": "Coursera",
    "gitlab": "GitLab", "mozilla": "Mozilla", "wikimedia": "Wikimedia Foundation",
    "dropbox": "Dropbox", "coinbase": "Coinbase", "cloudflare": "Cloudflare",
    "scaleai": "Scale AI", "labelbox": "Labelbox", "turing": "Turing", "andela": "Andela",
    "udemy": "Udemy", "khanacademy": "Khan Academy", "figma": "Figma", "reddit": "Reddit",
    "pinterest": "Pinterest", "twitch": "Twitch", "invisibletech": "Invisible",
    "snorkelai": "Snorkel AI", "anthropic": "Anthropic", "databricks": "Databricks",
    "brex": "Brex", "airtable": "Airtable", "robinhood": "Robinhood", "instacart": "Instacart",
    "affirm": "Affirm", "chime": "Chime", "asana": "Asana", "twilio": "Twilio",
    "elastic": "Elastic", "mongodb": "MongoDB", "gusto": "Gusto", "lyft": "Lyft",
    "stripe": "Stripe", "flexport": "Flexport",
}

ASHBY_BOARDS = {
    "Notion": "Notion", "Linear": "Linear", "Ramp": "Ramp", "Vanta": "Vanta",
    "Replit": "Replit", "Runway": "Runway", "openai": "OpenAI", "cohere": "Cohere",
    "Cursor": "Cursor", "Perplexity": "Perplexity", "ElevenLabs": "ElevenLabs",
    "Multiverse": "Multiverse", "Hex": "Hex", "Watershed": "Watershed",
}


def fetch_ashby():
    out = []
    for tok, name in ASHBY_BOARDS.items():
        try:
            d = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{tok}",
                             headers=UA, timeout=TIMEOUT).json()
            for j in d.get("jobs", []):
                loc = j.get("location") or (j.get("address", {}) or {}).get("postalAddress", {}).get("addressLocality", "")
                out.append(norm("ashby", j.get("title"), name, loc, None,
                                j.get("department", "") or j.get("team", ""),
                                j.get("jobUrl") or j.get("applyUrl"), j.get("id"),
                                desc=j.get("descriptionPlain") or ""))
        except Exception as e:
            print("ashby ERR", tok, e, file=sys.stderr)
    return out


def fetch_greenhouse():
    out = []
    for tok, name in GH_BOARDS.items():
        try:
            d = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{tok}/jobs",
                             headers=UA, timeout=TIMEOUT).json()
            for j in d.get("jobs", []):
                loc = (j.get("location") or {}).get("name", "")
                out.append(norm("greenhouse", j.get("title"), name, loc, None, "",
                                j.get("absolute_url"), j.get("id")))
        except Exception as e:
            print("greenhouse ERR", tok, e, file=sys.stderr)
    return out


def fetch_lever():
    out = []
    for c in ["ro", "spotify"]:
        try:
            d = requests.get(f"https://api.lever.co/v0/postings/{c}?mode=json",
                             headers=UA, timeout=TIMEOUT).json()
            if not isinstance(d, list):
                continue
            for j in d:
                cat = j.get("categories") or {}
                dsc = j.get("descriptionPlain") or j.get("description") or ""
                out.append(norm("lever", j.get("text"), c.capitalize(), cat.get("location", ""),
                                None, cat.get("team", ""), j.get("hostedUrl"), j.get("id"), desc=dsc))
        except Exception as e:
            print("lever ERR", c, e, file=sys.stderr)
    return out


def fetch_weworkremotely():
    out = []
    for cat in ["remote-jobs", "categories/remote-design-jobs",
                "categories/remote-customer-support-jobs"]:
        try:
            r = requests.get(f"https://weworkremotely.com/{cat}.rss", headers=UA, timeout=TIMEOUT)
            root = ET.fromstring(r.content)
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                region = (it.findtext("region") or "").strip()
                dsc = (it.findtext("description") or "").strip()
                if ":" in title:
                    company, role = title.split(":", 1)
                else:
                    company, role = "", title
                out.append(norm("weworkremotely", role.strip() or title, company.strip(),
                                region or "Remote", None, "", link, link, desc=dsc))
        except Exception as e:
            print("wwr ERR", cat, e, file=sys.stderr)
    return out


def main():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "")

    raw = []
    for f in (fetch_remoteok, fetch_remotive, fetch_arbeitnow, fetch_himalayas, fetch_jobicy,
              fetch_greenhouse, fetch_ashby, fetch_lever, fetch_weworkremotely):
        got = f()
        print(f"{f.__name__}: {len(got)}")
        raw += got

    # dedupe by job_id (later source wins), filter to AI-replaceable
    seen = {}
    for r in raw:
        repl, ai = kw_hits(r["title"], r["tags"])
        if not repl:
            continue
        r["repl_kw"] = ",".join(repl)
        r["ai_skill_kw"] = ",".join(ai)
        r["region"] = r["location"] or "(unspecified)"
        r["is_us"] = is_us(r["location"])
        r["needs_speaking"] = needs_speaking(r["title"], r.get("_desc", ""))
        r["crawled_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        seen[r["job_id"]] = r

    rows = list(seen.values())
    us_rows = [r for r in rows if r["is_us"]]
    low = [r for r in us_rows if not r["needs_speaking"]]
    print(f"\nAI-replaceable total: {len(rows)} | US: {len(us_rows)} | it-noi-TA: {len(low)}")
    for r in low[:10]:
        print(f"  [{r['source']}] {r['title'][:46]:46} @ {r['company'][:16]:16} | {r['repl_kw'][:30]}")

    # luu kho tho vao Supabase (chi cac cot that) hoac sqlite fallback
    if url and key:
        payload = [{c: r.get(c) for c in COLS} for r in rows]
        endpoint = f"{url}/rest/v1/us_ai_jobs?on_conflict=job_id"
        headers = {"apikey": key, "Authorization": f"Bearer {key}",
                   "Content-Type": "application/json",
                   "Prefer": "resolution=merge-duplicates,return=minimal"}
        ok = 0
        for i in range(0, len(payload), 200):
            batch = payload[i:i + 200]
            resp = requests.post(endpoint, headers=headers, data=json.dumps(batch), timeout=TIMEOUT)
            if resp.status_code in (200, 201, 204):
                ok += len(batch)
            else:
                print(f"upsert ERR {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
        print(f"Upserted {ok}/{len(payload)} rows into us_ai_jobs.")
    else:
        store_sqlite(rows, os.environ.get("DB_PATH", os.path.expanduser("~/jobs.db")))

    # board = crawl hien tai + gop file cu (tich luy + giu co needs_speaking)
    write_json(rows, os.environ.get("JSON_OUT", "docs/jobs.json"))


if __name__ == "__main__":
    main()
