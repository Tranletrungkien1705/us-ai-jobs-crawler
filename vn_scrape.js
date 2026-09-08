// Scrape .NET jobs from TopCV + VietnamWorks via Playwright (real chromium, VN IP). -> docs/topcv-jobs.json
const { chromium } = require('playwright');
const fs = require('fs');
const REL = /c#|c-sharp|\.net|dotnet|asp\.net/i;
const NOISE = /game net|net cafe|tiệm net|quán net|kinh doanh máy tính|pc\/ ?game/i;
const SENIOR = /lead |team lead| manager|head of|director|architect|chief|trưởng nhóm|principal|leader|quản lý/i;
function level(t){ t=t.toLowerCase(); if(/fresher|intern|thực tập/.test(t))return'fresher'; if(/junior|jr /.test(t))return'junior'; if(/middle|mid-|senior/.test(t))return'middle'; return'unspecified'; }
function needEng(t){ return /english|tiếng anh|chinese|japanese|korean/i.test(t); }
function enrich(title, url, source, prio, company){
  const lv = level(title), sen = SENIOR.test(title);
  return { title, company: (company||'').slice(0,80), location: 'Việt Nam', url, source, prio,
    level: lv, senior: sen, relevant: true, hanoi: true, junior_up: lv !== 'fresher',
    night: false, vietnamese_only: !needEng(title), needs_english: needEng(title),
    remote: /remote|từ xa/i.test(title), part_time: false, min_years: 0, fit: !sen };
}
// lấy title + url + company từ mỗi card (đi ngược lên tổ tiên tìm link công ty)
const EXTRACT = (sel, coSel) => (as, coSel2) => as.map(a => {
  const t=(a.textContent||'').replace(/\s+/g,' ').trim();
  let el=a.parentElement, co='';
  for(let i=0;i<7 && el;i++){ const c=el.querySelector(coSel2); if(c && (c.textContent||'').trim().length>1){ co=(c.textContent||'').replace(/\s+/g,' ').trim(); break; } el=el.parentElement; }
  return { h:a.href.split('?')[0], t, co };
}).filter(x=>x.t.length>5);

async function topcv(p){
  const seen=new Set(), out=[];
  const coSel='a[href*="/cong-ty/"],a[href*="/brand/"],[class*="company"] a,[class*="company-name"]';
  for(const u of ['https://www.topcv.vn/tim-viec-lam-.net','https://www.topcv.vn/tim-viec-lam-c-sharp','https://www.topcv.vn/tim-viec-lam-asp.net','https://www.topcv.vn/tim-viec-lam-.net-core','https://www.topcv.vn/tim-viec-lam-backend-.net']){
    try{
      await p.goto(u,{waitUntil:'domcontentloaded',timeout:40000}); await p.waitForTimeout(3500);
      const cards=await p.$$eval('a[href*="/viec-lam/"]', EXTRACT(null,null), coSel);
      for(const l of cards) if(!seen.has(l.h)){ seen.add(l.h); out.push(l); }
    }catch(e){ console.error('topcv',u,e.message.slice(0,50)); }
  }
  return out.filter(j=>REL.test(j.t)&&!NOISE.test(j.t)).map(j=>enrich(j.t,j.h,'topcv',3,j.co));
}
async function vietnamworks(p){
  const seen=new Set(), out=[];
  const coSel='a[href*="/nha-tuyen-dung/"],a[href*="/cong-ty/"],[class*="company"] a,[class*="employer"]';
  for(const q of ['.net','c%23','asp.net','dotnet','backend%20.net']){
    try{
      await p.goto(`https://www.vietnamworks.com/viec-lam?q=${q}`,{waitUntil:'domcontentloaded',timeout:40000}); await p.waitForTimeout(4000);
      for(let s=0;s<4;s++){ await p.mouse.wheel(0,4000); await p.waitForTimeout(1500); }
      const cards=await p.$$eval('a[href*="-jv"]', EXTRACT(null,null), coSel);
      for(const l of cards) if(!seen.has(l.h)){ seen.add(l.h); out.push(l); }
    }catch(e){ console.error('vnw',q,e.message.slice(0,50)); }
  }
  return out.filter(j=>REL.test(j.t)&&!NOISE.test(j.t)).map(j=>enrich(j.t.replace(/^Mới\s+/,''),j.h,'vietnamworks',2,j.co));
}
(async () => {
  const b = await chromium.launch({ headless: true, args: ['--no-sandbox','--disable-dev-shm-usage'] });
  const ctx = await b.newContext({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36', locale: 'vi-VN' });
  const p = await ctx.newPage();
  const tc = await topcv(p); const vw = await vietnamworks(p);
  await b.close();
  let all = [...tc, ...vw];
  let prev = [];
  try { prev = JSON.parse(fs.readFileSync('docs/topcv-jobs.json','utf8')).jobs || []; } catch (e) {}
  const byUrl = new Map(all.map(j => [j.url, j]));
  for (const o of prev) if (o.url && !byUrl.has(o.url)) byUrl.set(o.url, o);
  const jobs = [...byUrl.values()].slice(0, 250);
  fs.mkdirSync('docs', { recursive: true });
  fs.writeFileSync('docs/topcv-jobs.json', JSON.stringify({ count: jobs.length, jobs }, null, 1));
  console.log(`TopCV ${tc.length} + VietnamWorks ${vw.length} -> total ${jobs.length}; with company: ${jobs.filter(j=>j.company).length}`);
})();
