# Apple ile giriş: kurulum

Uygulamadaki **Apple ile giriş yap** düğmesi yalnızca iPhone uygulamasında, aşağıdaki eklenti
kuruluysa görünür. Web sürümünde (GitHub Pages) görünmez; orada e-posta ile giriş devam eder.

## 1. Firebase
1. Firebase Console → **Authentication** → **Sign-in method** → **Add new provider** → **Apple**.
2. **Enable**'ı aç ve **Save**'e bas. Yalnızca iPhone uygulamasından giriş yapılacağı için
   Services ID, Team ID ve anahtar alanlarını boş bırakabilirsin.

## 2. Apple Developer
1. developer.apple.com → **Certificates, Identifiers & Profiles** → **Identifiers**.
2. Courtside'ın App ID'sini aç, **Sign In with Apple** kutusunu işaretle, **Save**.

## 3. Mac (Xcode projesi)
Proje klasöründe Terminal'de:

```
npm install @capacitor-community/apple-sign-in
npx cap sync ios
```

Sonra Xcode'da: hedef (target) → **Signing & Capabilities** → **+ Capability** → **Sign in with Apple**.

Güncel `index.html`'i web klasörüne kopyaladıktan sonra `npx cap sync ios` komutunu bir kez daha
çalıştır ve yeni sürümü al.

## Nasıl çalışıyor
- Apple'ın verdiği kimlik Firebase'e gönderilir. Telefonda canlı yayın için açılmış anonim bir
  hesap varsa ona bağlanır, bu yüzden açık yayın linkleri bozulmaz. Bulut eşitleme, kulüp ve
  yoklama e-postayla girişteki gibi çalışır.
- Kullanıcı "E-postamı gizle"yi seçerse hesapta Apple'ın verdiği gizli adres görünür; bu normal.
- Apple adı yalnızca ilk girişte verir. Uygulama bu adı hesaba yazar, sonraki girişlerde de görünür.
- Aynı e-posta daha önce şifreyle kaydedildiyse uygulama "e-posta ve şifrenle giriş yap" der.

## Bilmen gereken bir nokta
Apple, "Apple ile giriş" sunan uygulamalarda hesap silinirken Apple bağlantısının da iptal
edilmesini (token revocation) istiyor. Uygulamadaki **Hesabı sil** Firebase hesabını ve verileri
siliyor ama bu iptali yapmıyor; bunun için sunucu tarafında Apple'a ayrı bir istek gerekiyor.
İnceleme sırasında Apple sorarsa ayrıca eklenebilir.
