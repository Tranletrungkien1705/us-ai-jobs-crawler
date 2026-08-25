# us-ai-jobs-crawler

Cào job remote/US mà **AI có thể làm thay được** (content, VA, data entry, support, SEO, transcribe, translate, copywriting...) từ nhiều nguồn free, chấm keyword, lưu vào **Supabase** (free). Chạy tự động bằng **GitHub Actions** (runner IP Mỹ), cron mỗi ngày.

## Nguồn
RemoteOK · Remotive · Arbeitnow · Himalayas (đều API JSON free, không cần key).

## Cài (1 lần)
1. **Supabase → SQL Editor** → dán nội dung `schema.sql` → Run (tạo bảng `us_ai_jobs`).
2. **Repo → Settings → Secrets and variables → Actions** → thêm 2 secret:
   - `SUPABASE_URL` = `https://atuwytlrpogbzwjbatdn.supabase.co`
   - `SUPABASE_KEY` = key `sb_secret_...` (bypass RLS)
3. **Actions tab → crawl-ai-jobs → Run workflow** để chạy thử ngay (hoặc chờ cron 14:00 VN mỗi ngày).

## Xem kết quả
```sql
select title, company, region, salary, repl_kw, url
from public.us_ai_jobs where is_us order by crawled_at desc limit 50;
```

## Chạy tay (local, có venv)
```bash
SUPABASE_URL=... SUPABASE_KEY=... python crawl.py
# không set env -> chạy dry-run, chỉ in ra màn hình
```

## Tuỳ biến
Sửa list `REPL` trong `crawl.py` để đổi nhóm nghề muốn theo dõi.
