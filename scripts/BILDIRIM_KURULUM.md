# Turnuva bildirimleri: kurulum

Bildirimler yalnızca iPhone uygulamasında çalışır. Takvim ekranının en üstünde **🔔 Bildirimler**
anahtarı çıkar (web sürümünde görünmez). Açan cihaz, takvimde seçtiği yaş grupları, şehirler ve
★ ile takip ettiği turnuvalarla birlikte Firebase'e kaydolur. Her sabah GitHub Actions
`scripts/bildirim_gonder.py`'yi çalıştırır:

- **08:47** bugün son kayıt günü olan turnuvalar ("Bugün son kayıt günü")
- **10:27** dünden beri yeni açıklanan turnuvalar ("Bugün 3 yeni turnuva açıklandı")

Bildirime dokununca uygulama takvimde açılır.

## 1. Apple Developer
1. developer.apple.com → **Certificates, Identifiers & Profiles** → **Keys** → **+**.
2. Bir ad ver (ör. "Courtside Push"), **Apple Push Notifications service (APNs)** kutusunu işaretle,
   **Continue → Register**.
3. **.p8 dosyasını indir** (yalnızca bir kez indirilebilir, sakla). Sayfadaki **Key ID**'yi not al.
4. **Team ID**: sağ üstte adının altında ya da **Membership** sayfasında yazar.
5. **Identifiers** → Courtside'ın App ID'si → **Push Notifications** kutusunu işaretle → **Save**.

## 2. Mac (Xcode projesi)
Proje klasöründe Terminal'de:

```
npm install @capacitor/push-notifications
npx cap sync ios
```

Xcode'da: hedef (target) → **Signing & Capabilities** → **+ Capability** → **Push Notifications**.

`ios/App/App/AppDelegate.swift` dosyasında `class AppDelegate` içine, diğer fonksiyonların yanına
şu iki fonksiyonu ekle (yoksa uygulama belirteci alamaz):

```swift
func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
    NotificationCenter.default.post(name: .capacitorDidRegisterForRemoteNotifications, object: deviceToken)
}

func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
    NotificationCenter.default.post(name: .capacitorDidFailToRegisterForRemoteNotifications, object: error)
}
```

**Bundle ID**'yi de not al (Signing & Capabilities'te yazar, ör. `com.ogiterzi.courtside`).

## 3. Firebase
1. **Realtime Database → Rules**: `scripts/firebase-kurallari.json`'un içeriğini yapıştır, **Publish**.
   (İçinde `bildirim` bölümü var; cihazlar kendi kaydını yazabilir, kimse okuyamaz.)
2. **Proje ayarları (⚙️) → Hizmet hesapları → Yeni özel anahtar oluştur**. İnen JSON dosyasını sakla;
   bu, betiğin cihaz listesini okumasını sağlar. Kimseyle paylaşma.

## 4. GitHub
Repo → **Settings → Secrets and variables → Actions → New repository secret**. Beş tane:

| Ad | Değer |
|---|---|
| `FIREBASE_SA` | Firebase'den inen JSON dosyasının tüm içeriği |
| `APNS_KEY` | .p8 dosyasının tüm içeriği (`-----BEGIN PRIVATE KEY-----` satırları dahil) |
| `APNS_KEY_ID` | Key ID (10 karakter) |
| `APNS_TEAM_ID` | Team ID (10 karakter) |
| `APNS_TOPIC` | Bundle ID |

Xcode'dan kabloyla telefona kurduğun geliştirme sürümüyle denemek istersen aynı sayfadaki
**Variables** sekmesinde `APNS_SANDBOX` = `1` ekle. TestFlight ve App Store sürümleri için bu
değişkeni sil ya da boş bırak.

## 5. İlk çalıştırma ve deneme
1. GitHub → **Actions → Turnuva bildirimleri → Run workflow**, mod: `yeni`.
   İlk çalıştırma sadece mevcut turnuvaları kaydeder (`data/bildirim_durum.json`), bildirim
   göndermez; böylece ilk gün herkese 50 "yeni turnuva" gitmez.
2. Telefonda yeni sürümü aç → Takvim → **🔔 Bildirimler**'i aç, izin ver.
3. Ertesi sabah otomatik çalışır. Hemen denemek istersen bir turnuvayı ★ ile takip et ve son
   kayıt günü bugün olan biri varsa mod `sonkayit` ile elle çalıştır.

Bir sorun olursa Actions'taki çalıştırmanın kaydında hangi cihaza ne gittiği ve hata varsa
nedeni yazar. Uygulaması silinmiş cihazlar listeden kendiliğinden temizlenir.
