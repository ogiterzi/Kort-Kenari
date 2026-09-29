#!/usr/bin/env python3
"""Courtside turnuva takvimi güncelleyici.

ikort.com.tr/turnuvalar sayfasındaki güncel turnuvaları okur, her turnuvanın
detay sayfasından tarih aralığını ve yaş gruplarını çıkarır ve sonucu
data/takvim.json dosyasına yazar. GitHub Actions her gün bir kez çalıştırır
(.github/workflows/takvim.yml).

Kişisel veri (oyuncu adı, doğum tarihi vb.) okunmaz ve kaydedilmez; yalnızca
turnuvanın kendisine ait bilgiler alınır.

Yerel deneme:  pip install requests beautifulsoup4 && python scripts/takvim_guncelle.py
Kayıtlı HTML ile deneme: python scripts/takvim_guncelle.py --list liste.html --detail-dir detaylar/
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ikort.com.tr"
LIST_URL = BASE + "/turnuvalar"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "takvim.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}
DELAY = 1.5  # siteyi yormamak için istekler arası bekleme (sn)

AYLAR = {"ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5,
         "haziran": 6, "temmuz": 7, "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
         "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12}
TARIH_RE = re.compile(r"(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+(\d{4})")
TR_TZ = dt.timezone(dt.timedelta(hours=3))


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def tr_lower(s):
    return s.replace("I", "ı").replace("İ", "i").lower()


def parse_dates(text):
    """'24 Eylül 2026 - 04 Ekim 2026' içinden bulunan tarihleri ISO olarak döndürür."""
    out = []
    for d, ay, y in TARIH_RE.findall(text or ""):
        m = AYLAR.get(tr_lower(ay))
        if m:
            try:
                out.append(dt.date(int(y), m, int(d)).isoformat())
            except ValueError:
                pass
    return out


def ages_from(texts):
    """Grup/turnuva adlarından yaş etiketleri çıkarır.
    Gençler: "8".."18" · Büyükler: "B" · Yeni başlayan: "YB" · Masters: "M30", "M35"… (yaş yoksa "M")."""
    tags = set()
    for raw in texts:
        s = clean(raw)
        low = tr_lower(s)
        for grp in re.findall(r"((?:\d{1,2}\s*[-,/]\s*)*\d{1,2})\s*yaş", low):
            for n in re.findall(r"\d{1,2}", grp):
                if 6 <= int(n) <= 18:
                    tags.add(str(int(n)))
        for n in re.findall(r"(\d{2})\s*\+", s):
            if 30 <= int(n) <= 90:
                tags.add("M" + n)
        if "büyükler" in low:
            tags.add("B")
        if "yeni başlayan" in low:
            tags.add("YB")
    if not any(t.startswith("M") for t in tags) and any("masters" in tr_lower(x) or "master " in tr_lower(x) for x in texts):
        tags.add("M")
    order = lambda t: (0, int(t)) if t.isdigit() else ((1, 0) if t == "B" else ((2, 0) if t == "YB" else (3, int(t[1:] or 0))))
    return sorted(tags, key=order)


def get(session, url):
    for attempt in range(3):
        try:
            r = session.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                r.encoding = r.encoding or "utf-8"
                return r.text
            print(f"  ! {url} -> HTTP {r.status_code}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  ! {url} -> {e}", file=sys.stderr)
        time.sleep(3 * (attempt + 1))
    return None


def parse_list(html):
    soup = BeautifulSoup(html, "html.parser")
    scope = soup.find(id="guncelturnuvalar")  # "Güncel" sekmesi
    if not scope or not scope.select('a[href*="turnuva-detay/"]'):
        scope = soup  # sekme bulunamazsa ya da boşsa tüm sayfa
    seen, rows = set(), []
    for a in scope.select('a[href*="turnuva-detay/"]'):
        m = re.search(r"turnuva-detay/(\d+)", a.get("href", ""))
        if not m or m.group(1) in seen:
            continue
        tr = a.find_parent("tr")
        tds = [clean(td.get_text(" ")) for td in tr.find_all(["td", "th"])] if tr else []
        if len(tds) >= 5:
            date_txt, club, city, cat = tds[1], tds[2], tds[3], tds[4]
        else:  # tablo değilse: bağlantının içinde olduğu kutudaki metinden tarihi bul
            box, date_txt = a.parent, ""
            for _ in range(4):
                if box is None:
                    break
                if parse_dates(box.get_text(" ")):
                    date_txt = box.get_text(" ")
                    break
                box = box.parent
            club = city = cat = ""
        seen.add(m.group(1))
        dates = parse_dates(date_txt)
        rows.append({
            "id": m.group(1),
            "name": clean(a.get_text(" ")) or (tds[0] if tds else ""),
            "start": dates[0] if dates else None,
            "club": "" if club == "-" else club,
            "city": "" if city == "-" else city,
            "category": cat,
        })
    return rows


def parse_detail(html):
    soup = BeautifulSoup(html, "html.parser")
    text = clean(soup.get_text(" "))
    info = {}
    # 1) "Turnuva tarihi: 24 Eylül 2026 - 04 Ekim 2026"
    dates = []
    for m in re.finditer(r"Turnuva tarihi\s*:?\s*(.{0,120})", text, re.I):
        dates = parse_dates(m.group(1))[:2]
        if dates:
            break
    if dates:
        info["start"] = dates[0]
        info["end"] = max(dates)
    # 2) "Tarihler" bölümü: "Tarihi 24-09-2026 (39)" / "Bitiş Tarihi 04-10-2026 (40)"
    num = lambda d, mo, y: dt.date(int(y), int(mo), int(d)).isoformat()
    m = re.search(r"Bitiş Tarihi\s*:?\s*(\d{1,2})[-./](\d{1,2})[-./](\d{4})", text, re.I)
    if m:
        info["end"] = max(info.get("end", ""), num(*m.groups()))
    m = re.search(r"(?<!Bitiş )(?<!Eleme )(?<!Son Kayıt )\bTarihi\s*:?\s*(\d{1,2})[-./](\d{1,2})[-./](\d{4})", text)
    if m and "start" not in info:
        info["start"] = num(*m.groups())
    m = re.search(r"Son Kayıt Tarihi\s*:?\s*(\d{1,2})[-./](\d{1,2})[-./](\d{4})", text, re.I)
    if m:
        try:
            info["deadline"] = num(*m.groups())
        except ValueError:
            pass
    info["debug"] = " | ".join(clean(x.group(0))[:140] for x in re.finditer(r"(Turnuva tarihi|Bitiş Tarihi).{0,100}", text, re.I))[:400]
    m = re.search(r"Oynanacak Zemin Türü\s+([A-Za-zÇĞİÖŞÜçğıöşü ]+?Zemin)", text)
    if m:
        info["surface"] = clean(m.group(1))
    # Yaş grupları: "Fikstür Grupları" tablosundaki grup adları (katılımcı adları DEĞİL).
    groups = []
    for a in soup.select('a[href*="turnuvaya-katilanlar-listesi"]'):
        tr = a.find_parent("tr")
        td = tr.find("td") if tr else None
        if td:
            name = clean(td.get_text(" "))
            if name and name not in groups:
                groups.append(name)
    if not groups:  # yedek: katılımcı listesi seçim kutusundaki grup adları
        for opt in soup.select("select option"):
            name = clean(opt.get_text(" "))
            if re.search(r"(Tek|Çift)$", name) and name not in groups:
                groups.append(name)
    info["groups"] = groups
    return info


def diagnose(html):
    """Liste okunamadığında sayfada ne geldiğini kayda yazar (sorun gidermek için)."""
    soup = BeautifulSoup(html, "html.parser")
    print("---- TEŞHİS ----", file=sys.stderr)
    print("boyut:", len(html), "| başlık:", clean(soup.title.get_text()) if soup.title else "-", file=sys.stderr)
    print("'turnuva-detay' geçen yer:", html.count("turnuva-detay"),
          "| tablo:", len(soup.find_all("table")), "| satır:", len(soup.find_all("tr")),
          "| id=guncelturnuvalar:", bool(soup.find(id="guncelturnuvalar")), file=sys.stderr)
    for f in soup.find_all("form"):
        print("form:", f.get("method"), f.get("action"), file=sys.stderr)
    for sc in soup.find_all("script"):
        src, body = sc.get("src"), sc.string or ""
        if src and "ikort" in src:
            print("script:", src, file=sys.stderr)
        for u in re.findall(r"""["'](/[A-Za-z0-9_\-/]*(?:turnuva|ajax|api|list)[A-Za-z0-9_\-/]*)["']""", body, re.I)[:15]:
            print("js adresi:", u, file=sys.stderr)
    i = html.find("turnuva-detay")
    if i >= 0:
        print("örnek:", clean(html[max(0, i - 400):i + 400]), file=sys.stderr)
    body = clean(soup.body.get_text(" ")) if soup.body else clean(html)
    print("metin başı:", body[:600], file=sys.stderr)
    print("---- /TEŞHİS ----", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", help="liste sayfası için kayıtlı HTML (deneme)")
    ap.add_argument("--detail-dir", help="detay sayfaları için kayıtlı HTML klasörü: <id>.html (deneme)")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--today", help="YYYY-MM-DD (deneme)")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(TR_TZ).date()
    session = requests.Session()

    if args.list:
        with open(args.list, encoding="utf-8") as f:
            list_html = f.read()
    else:
        list_html = get(session, LIST_URL)
    if not list_html:
        sys.exit("Liste sayfası alınamadı; mevcut takvim korunuyor.")

    rows = parse_list(list_html)
    if not rows:
        diagnose(list_html)
        sys.exit("Listede turnuva bulunamadı (site yapısı değişmiş olabilir); mevcut takvim korunuyor.")

    # Başlangıcı 45 günden eski olanlar kesin bitmiştir; detayına bakmaya gerek yok.
    cutoff = (today - dt.timedelta(days=45)).isoformat()
    rows = [r for r in rows if not r["start"] or r["start"] >= cutoff]

    out = []
    for i, r in enumerate(rows):
        detail_html = None
        if args.detail_dir:
            p = os.path.join(args.detail_dir, r["id"] + ".html")
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    detail_html = f.read()
        else:
            if i:
                time.sleep(DELAY)
            detail_html = get(session, f"{BASE}/turnuva-detay/{r['id']}")
        d = parse_detail(detail_html) if detail_html else {"groups": []}
        start = d.get("start") or r["start"]
        end = d.get("end")
        if (not end or end <= start) and start:
            # Bitiş okunamadıysa türe göre tahmin: hafta sonu 3 gün, seri/kategori 5 gün, T-masters 10 gün.
            cat = tr_lower(r["category"] + " " + r["name"])
            days = 2 if "haftasonu" in cat or "hafta sonu" in cat else (9 if re.search(r"\bt\d00\b", cat) else 4)
            end = (dt.date.fromisoformat(start) + dt.timedelta(days=days)).isoformat()
            if i < 3:
                print("  (bitiş tahmini) detay:", d.get("debug", "-"), file=sys.stderr)
        if not start or end < today.isoformat():
            continue  # bitmiş turnuva
        name = r["name"]
        out.append({
            "id": r["id"],
            "name": name,
            "start": start,
            "end": end,
            "club": r["club"],
            "city": r["city"],
            "category": r["category"],
            "surface": d.get("surface", ""),
            "deadline": d.get("deadline", ""),
            "ages": ages_from([name, r["category"]] + d["groups"]),
            "cancelled": "iptal" in tr_lower(name),
            "url": f"{BASE}/turnuva-detay/{r['id']}",
        })
        print(f"  {start} {name[:60]} -> {out[-1]['ages']}")

    out.sort(key=lambda x: (x["start"], x["name"]))
    data = {
        "updated": dt.datetime.now(TR_TZ).isoformat(timespec="minutes"),
        "source": LIST_URL,
        "tournaments": out,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{len(out)} turnuva yazıldı -> {args.out}")


if __name__ == "__main__":
    main()
