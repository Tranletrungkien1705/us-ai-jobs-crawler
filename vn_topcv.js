// Scrape TopCV .NET jobs via Playwright (real chromium bypasses 403). -> docs/topcv-jobs.json
const { chromium } = require('playwright');
const fs = require('fs');
const REL = /c#|c-sharp|\.net|dotnet|asp\.net/i;
const NOISE = /game net|net cafe|tiệm net|quán net|kinh doanh máy tính|pc\/ ?game/i;
const SENIOR = /lead |team lead| manager|head of|director|architect|chief|trưởng nhóm|principal|leader|quản lý/i;
function level(t){ t=t.toLowerCase(); if(/fresher|intern|thực tập/.test(t))return'fresher'; if(/junior|jr /.test(t))return'junior'; if(/middle|mid-|senior/.test(t))return'middle'; return'unspecified'; }
(async () => {
  const b = await chromium.launch({ headless: true, args: ['--no-sandbox','--disable-dev-shm-usage'] });
  const ctx = await b.newContext({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36', locale: 'vi-VN' });
  const p = await ctx.newPage();
  const seen = new Set(); const raw = [];
  for (const u of ['https://www.topcv.vn/tim-viec-lam-.net','https://www.topcv.vn/tim-viec-lam-c-sharp','https://www.topcv.vn/tim-viec-lam-asp.net','https://www.topcv.vn/tim-viec-lam-.net-core','https://www.topcv.vn/tim-viec-lam-backend-.net']) {
    try {
      await p.goto(u, { waitUntil: 'domcontentloaded', timeout: 40000 });
      await p.waitForTimeout(4000);
      const links = await p.$$eval('a[href*="/viec-lam/"]', as => as.map(a => ({ h: a.href.split('?')[0], t: (a.textContent||'').replace(/\s+/g,' ').trim() })).filter(x => x.t.length > 5));
      for (const l of links) { if (!seen.has(l.h)) { seen.add(l.h); raw.push(l); } }
    } catch (e) { console.error('goto err', u, e.message.slice(0,60)); }
  }
  await b.close();
  const jobs = raw.filter(j => REL.test(j.t) && !NOISE.test(j.t)).map(j => {
    const lv = level(j.t), sen = SENIOR.test(j.t);
    return { title: j.t, company: '', location: 'Việt Nam', url: j.h, source: 'topcv', level: lv, senior: sen,
      relevant: true, hanoi: true, junior_up: lv !== 'fresher', night: false, vietnamese_only: true,
      needs_english: false, remote: false, part_time: false, min_years: 0, fit: !sen };
  });
  const uniq = [...new Map(jobs.map(j => [j.url, j])).values()];
  // gộp file cũ để tích luỹ
  let prev = [];
  try { prev = JSON.parse(fs.readFileSync('docs/topcv-jobs.json','utf8')).jobs || []; } catch (e) {}
  const have = new Set(uniq.map(j => j.url));
  for (const o of prev) if (o.url && !have.has(o.url)) { have.add(o.url); uniq.push(o); }
  fs.mkdirSync('docs', { recursive: true });
  fs.writeFileSync('docs/topcv-jobs.json', JSON.stringify({ count: uniq.length, jobs: uniq.slice(0,200) }, null, 1));
  console.log('TopCV: raw', raw.length, '-> .NET jobs', uniq.length);
})();
