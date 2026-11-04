#!/usr/bin/env python3
"""Courtside turnuva bildirimleri.

data/takvim.json (takvim_guncelle.py her sabah üretir) ile uygulamadaki cihazların
seçimlerini (Firebase: /bildirim/<cihaz-belirteci>) karşılaştırır ve Apple'ın push
servisi (APNs) üzerinden bildirim gönderir. GitHub Actions çalıştırır
(.github/workflows/bildirim.yml).

İki mod:
  --mod yeni      Dünden bu yana listeye eklenen turnuvalar ("Bugün 3 yeni turnuva açıklandı").
                  Hangi turnuvaların daha önce görüldüğü data/bildirim_durum.json'da tutulur.
                  İlk çalıştırmada sadece liste kaydedilir, bildirim gönderilmez.
  --mod sonkayit  Son kayıt günü bugün olan turnuvalar ("Bugün son kayıt günü").

Her cihaz yalnızca takvimde seçtiği yaş grupları ve şehirlerle eşleşen turnuvalar için
bildirim alır; ★ ile takip ettiği turnuvaların son kayıt günü her zaman bildirilir.

Gerekli ortam değişkenleri (GitHub > Settings > Secrets and variables > Actions):
  FIREBASE_SA    Firebase hizmet hesabı JSON'u (Proje ayarları > Hizmet hesapları > Yeni özel anahtar)
  APNS_KEY       Apple push anahtarı (.p8 dosyasının tüm içeriği)
  APNS_KEY_ID    Anahtar kimliği (10 karakter)
  APNS_TEAM_ID   Apple Team ID (10 karakter)
  APNS_TOPIC     Uygulamanın Bundle ID'si (Xcode > Signing & Capabilities)
İsteğe bağlı:
  APNS_SANDBOX=1 Xcode'dan doğrudan telefona kurulan (geliştirme) sürüm için.
                 TestFlight ve App Store sürümleri için boş bırak.

Deneme (hiçbir şey göndermez, hiçbir dosyayı değiştirmez):
  python scripts/bildirim_gonder.py --mod yeni --dry-run --cihazlar ornek_cihazlar.json
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

TR_TZ = dt.timezone(dt.timedelta(hours=3))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TAKVIM = os.path.join(ROOT, "data", "takvim.json")
DURUM = os.path.join(ROOT, "data", "bildirim_durum.json")
FIREBASE_DB = os.environ.get("FIREBASE_DB", "https://courtside-62f8e-default-rtdb.europe-west1.firebasedatabase.app")
MAX_YENI = 40  # bir günde bundan fazla "yeni" çıkarsa veri hatası say, gönderme
ITF_AGES = ["14", "16", "18"]


# ---------------------------------------------------------------- eşleştirme
# Uygulamadaki calAgeIn1 / calMatches / calCityName ile aynı kurallar.
def age_in(a, f):
    a = str(a)
    if f == "all":
        return False
    if f == "B":
        return a == "B"
    if f == "M":
        return a.startswith("M")
    if not a.isdigit():
        return False
    n = int(a)
    if f == "u10":
        return n <= 10
    if f.isdigit():
        return int(f) - 2 < n <= int(f)
    return False


def matches_ages(tr, fs):
    fs = [f for f in (fs or []) if f != "all"]
    if not fs:
        return True
    if tr.get("source") == "itf":
        return any(f == "itf" or f in ITF_AGES for f in fs)
    return any(age_in(a, f) for a in (tr.get("ages") or []) for f in fs)


def city_name(c):
    c = str(c or "").strip()
    return "İSTANBUL" if c.startswith("İSTANBUL") else c


def matches(tr, dev):
    if not matches_ages(tr, dev.get("ages")):
        return False
    cities = dev.get("cities") or []
    return not cities or city_name(tr.get("city")) in cities


# ---------------------------------------------------------------- metinler
def nice(s):
    """'İSTANBUL ANADOLU' -> 'İstanbul Anadolu' (Türkçe büyük/küçük harf)."""
    out = []
    for w in str(s or "").split():
        low = w.replace("I", "ı").replace("İ", "i").lower()
        first = low[0]
        first = "İ" if first == "i" else ("I" if first == "ı" else first.upper())
        out.append(first + low[1:])
    return " ".join(out)


def short(tr):
    name = str(tr.get("name") or "").strip()
    if name.isupper():
        name = nice(name)
    city = nice(city_name(tr.get("city")))
    s = name if len(name) <= 70 else name[:67] + "…"
    return s + (" · " + city if city else "")


def text_yeni(trs, lang):
    n = len(trs)
    if lang == "en":
        title = "New tournament" if n == 1 else f"{n} new tournaments"
        body = short(trs[0]) if n == 1 else short(trs[0]) + f" and {n - 1} more"
    else:
        title = "Yeni turnuva açıklandı" if n == 1 else f"Bugün {n} yeni turnuva açıklandı"
        body = short(trs[0]) if n == 1 else short(trs[0]) + f" ve {n - 1} turnuva daha"
    return title, body


def text_sonkayit(trs, lang):
    n = len(trs)
    if lang == "en":
        title = "Entries close today"
        body = short(trs[0]) if n == 1 else short(trs[0]) + f" and {n - 1} more"
    else:
        title = "Bugün son kayıt günü"
        body = short(trs[0]) if n == 1 else short(trs[0]) + f" ve {n - 1} turnuva daha"
    return title, body


# ---------------------------------------------------------------- Firebase
def firebase_token():
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    info = json.loads(os.environ["FIREBASE_SA"])
    cred = service_account.Credentials.from_service_account_info(info, scopes=[
        "https://www.googleapis.com/auth/firebase.database",
        "https://www.googleapis.com/auth/userinfo.email",
    ])
    cred.refresh(Request())
    return cred.token


def fb(method, path, token, body=None):
    import requests
    r = requests.request(method, f"{FIREBASE_DB}/{path}.json", params={"access_token": token},
                         json=body, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------- APNs
class Apns:
    def __init__(self):
        import jwt
        import httpx
        self.topic = os.environ["APNS_TOPIC"]
        host = "api.sandbox.push.apple.com" if os.environ.get("APNS_SANDBOX") == "1" else "api.push.apple.com"
        self.base = f"https://{host}/3/device/"
        tok = jwt.encode({"iss": os.environ["APNS_TEAM_ID"], "iat": int(time.time())},
                         os.environ["APNS_KEY"], algorithm="ES256",
                         headers={"kid": os.environ["APNS_KEY_ID"]})
        self.client = httpx.Client(http2=True, timeout=20, headers={
            "authorization": f"bearer {tok}", "apns-topic": self.topic,
            "apns-push-type": "alert", "apns-priority": "10"})

    def send(self, device, title, body):
        payload = {"aps": {"alert": {"title": title, "body": body}, "sound": "default"}, "ekran": "takvim"}
        r = self.client.post(self.base + device, json=payload)
        if r.status_code == 200:
            return "ok"
        reason = ""
        try:
            reason = r.json().get("reason", "")
        except Exception:
            pass
        # Uygulama silinmiş ya da belirteç geçersiz: kayıt temizlenir.
        if r.status_code == 410 or reason in ("BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"):
            return "gone"
        return f"hata {r.status_code} {reason}"


# ---------------------------------------------------------------- ana akış
def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", choices=["yeni", "sonkayit"], required=True)
    ap.add_argument("--dry-run", action="store_true", help="göndermeden ne gideceğini yaz")
    ap.add_argument("--cihazlar", help="Firebase yerine bu JSON dosyasındaki cihazları kullan (deneme)")
    ap.add_argument("--bugun", help="YYYY-AA-GG (deneme için)")
    a = ap.parse_args()

    today = a.bugun or dt.datetime.now(TR_TZ).strftime("%Y-%m-%d")
    data = load_json(TAKVIM, {})
    tours = [t for t in data.get("tournaments", []) if not t.get("cancelled") and t.get("id")]
    upcoming = [t for t in tours if (t.get("end") or t.get("start") or "") >= today]

    # Hangi turnuvalar bildirilecek?
    durum = None
    if a.mod == "yeni":
        durum = load_json(DURUM, None)
        ids = sorted({str(t["id"]) for t in tours})
        if durum is None or not isinstance(durum.get("seen"), list):
            print(f"İlk çalıştırma: {len(ids)} turnuva kaydedildi, bildirim gönderilmedi.")
            if not a.dry_run:
                with open(DURUM, "w", encoding="utf-8") as f:
                    json.dump({"seen": ids, "updated": today}, f, ensure_ascii=False, indent=0)
            return 0
        seen = set(durum["seen"])
        aday = [t for t in upcoming if str(t["id"]) not in seen]
        if len(aday) > MAX_YENI:
            print(f"{len(aday)} yeni turnuva: veri hatası olabilir, bildirim gönderilmedi.")
            aday = []
        durum = {"seen": sorted(seen | set(ids)), "updated": today}
    else:
        aday = [t for t in upcoming if t.get("deadline") == today]
    print(f"Mod {a.mod}, {today}: {len(aday)} turnuva.")

    if aday or a.dry_run:
        if a.cihazlar:
            devices = load_json(a.cihazlar, {})
            token = None
        else:
            token = firebase_token()
            devices = fb("GET", "bildirim", token) or {}
        print(f"{len(devices)} cihaz.")
        apns = None if a.dry_run else (Apns() if aday else None)
        sent = gone = 0
        for dev_token, dev in devices.items():
            if not isinstance(dev, dict):
                continue
            favs = set(str(x) for x in (dev.get("favs") or []))
            mine = [t for t in aday if matches(t, dev) or (a.mod == "sonkayit" and str(t["id"]) in favs)]
            if not mine:
                continue
            mine.sort(key=lambda t: (str(t["id"]) not in favs, t.get("start") or ""))
            lang = "en" if dev.get("lang") == "en" else "tr"
            title, body = (text_yeni if a.mod == "yeni" else text_sonkayit)(mine, lang)
            if a.dry_run:
                print(f"  [{dev_token[:8]}…] {title} — {body}")
                continue
            res = apns.send(dev_token, title, body)
            if res == "ok":
                sent += 1
            elif res == "gone":
                gone += 1
                if token:
                    try:
                        fb("DELETE", "bildirim/" + dev_token, token)
                    except Exception as e:  # silinemezse bir dahaki sefere
                        print("  silinemedi:", e)
            else:
                print(f"  [{dev_token[:8]}…] {res}")
        print(f"Gönderildi: {sent}, silinen cihaz: {gone}.")

    if durum is not None and not a.dry_run:
        with open(DURUM, "w", encoding="utf-8") as f:
            json.dump(durum, f, ensure_ascii=False, indent=0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
