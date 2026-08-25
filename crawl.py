#!/usr/bin/env python3
"""
Crawl remote/US jobs that AI can realistically REPLACE (automatable knowledge work),
tag them, and upsert into a free Supabase table. Designed to run on GitHub Actions (US runner).

Env:
  SUPABASE_URL  e.g. https://xxxx.supabase.co
  SUPABASE_KEY  service/secret key (sb_secret_... or service_role) - bypasses RLS
"""
import os, re, sys, json, hashlib, datetime, sqlite3
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) job-crawler"}
TIMEOUT = 30

# --- job families AI can realistically do the work of ("ngon" = tri-thuc, luong tot) ---
REPL = [
    "content", "copywrit", "writer", "blog", "article", "ghostwrit",
    "data entry", "annotat", "data label", "transcri", "translat", "proofread", "editor",
    "virtual assistant", "customer support", "customer service", "chat support", "email support",
    "moderat", "bookkeep", "accounts payable", "seo", "social media", "community manager",
    "research assistant", "market research", "appointment setter", "outreach", "lead generation",
    "sales development", "sdr", "recruit", "sourcer", "paralegal", "tutor", "english teacher",
    "voice over", "video edit", "graphic design", "presentation", "data analyst", "qa tester",
]
# jobs that are ABOUT building AI (informational tag)
AISKILL = ["ai", "ml", "llm", "gpt", "prompt", "machine learning", "nlp", "data scien", "generative"]

US_HINTS = ["us", "u.s", "united states", "usa", "america", "worldwide", "anywhere", "remote"]


def kw_hits(blob):
    t = blob.lower()
    repl = sorted({k for k in REPL if k in t})
    ai = sorted({k for k in AISKILL if re.search(r"\b" + re.escape(k) + r"\b", t)})
    return repl, ai


def is_us(loc):
    l = (loc or "").lower().strip()
    if l == "":
        return True
    return any(h in l for h in US_HINTS)


def jid(source, raw):
    return f"{source}:{raw}" if raw else f"{source}:" + hashlib.md5(raw.encode() if raw else b'').hexdigest()[:12]


def norm(source, title, company, location, salary, tags, url, raw_id):
    return {
        "job_id": jid(source, str(raw_id or url)),
        "source": source,
        "title": (title or "").strip()[:300],
        "company": (company or "").strip()[:200],
        "location": (location or "").strip()[:200],
        "salary": (str(salary).strip()[:120] if salary else None),
        "tags": (tags or "").strip()[:500],
        "url": (url or "").strip()[:600],
    }


def fetch_remoteok():
    out = []
    try:
        d = requests.get("https://remoteok.com/api", headers=UA, timeout=TIMEOUT).json()
        for j in d:
            if not isinstance(j, dict) or "position" not in j:
                continue
            out.append(norm("remoteok", j.get("position"), j.get("company"),
                            j.get("location"), j.get("salary_min"),
                            " ".join(j.get("tags", []) or []), j.get("url"), j.get("id")))
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
                            " ".join(j.get("tags", []) or []), j.get("url"), j.get("id")))
    except Exception as e:
        print("remotive ERR", e, file=sys.stderr)
    return out


def fetch_arbeitnow():
    out = []
    try:
        d = requests.get("https://www.arbeitnow.com/api/job-board-api", headers=UA, timeout=TIMEOUT).json()
        for j in d.get("data", []):
            loc = j.get("location") or ("Remote" if j.get("remote") else "")
            out.append(norm("arbeitnow", j.get("title"), j.get("company_name"),
                            loc, None, " ".join(j.get("tags", []) or []),
                            j.get("url"), j.get("slug")))
    except Exception as e:
        print("arbeitnow ERR", e, file=sys.stderr)
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
                            j.get("applicationLink") or j.get("guid"), j.get("guid")))
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


def main():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "")

    raw = []
    for f in (fetch_remoteok, fetch_remotive, fetch_arbeitnow, fetch_himalayas):
        got = f()
        print(f"{f.__name__}: {len(got)}")
        raw += got

    # dedupe by job_id (later source wins), filter to AI-replaceable
    seen = {}
    for r in raw:
        blob = f"{r['title']} {r['tags']}"
        repl, ai = kw_hits(blob)
        if not repl:
            continue
        r["repl_kw"] = ",".join(repl)
        r["ai_skill_kw"] = ",".join(ai)
        r["region"] = r["location"] or "(unspecified)"
        r["is_us"] = is_us(r["location"])
        r["crawled_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        seen[r["job_id"]] = r

    rows = list(seen.values())
    us_rows = [r for r in rows if r["is_us"]]
    print(f"\nAI-replaceable total: {len(rows)} | US/worldwide: {len(us_rows)}")
    for r in us_rows[:10]:
        print(f"  [{r['source']}] {r['title'][:50]:50} | {r['region'][:18]:18} | {r['salary'] or '-'} | {r['repl_kw'][:40]}")

    if not url or not key:
        db = os.environ.get("DB_PATH", os.path.expanduser("~/jobs.db"))
        store_sqlite(rows, db)
        return

    # bulk upsert (omit first_seen so it stays at original insert time)
    endpoint = f"{url}/rest/v1/us_ai_jobs?on_conflict=job_id"
    headers = {
        "apikey": key, "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    ok = 0
    for i in range(0, len(rows), 200):
        batch = rows[i:i + 200]
        resp = requests.post(endpoint, headers=headers, data=json.dumps(batch), timeout=TIMEOUT)
        if resp.status_code in (200, 201, 204):
            ok += len(batch)
        else:
            print(f"upsert ERR {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
    print(f"\nUpserted {ok}/{len(rows)} rows into us_ai_jobs.")


if __name__ == "__main__":
    main()
