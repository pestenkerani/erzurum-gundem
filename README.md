# Erzurum Gündem — ücretsiz web sürümü

GitHub Pages üzerinde şifresiz okunan, GitHub Actions ile günlük güncellenen haber paneli. Python 3.12 standart kütüphanesi kullanılır; ücretli haber/AI API'si veya kullanıcıya ait API anahtarı gerekmez.

## Kullanım

- Ziyaretçi yalnızca site bağlantısını açar; hesap veya uygulama kurulumu gerekmez.
- Günlük tarama Türkiye saati **08.00** için zamanlanır. GitHub çalışmayı geciktirebilir; bu saat garanti değildir.
- **Listeyi yenile**, son yayımlanan haber verisini getirir. İnternetten yeni haber toplama başlatmaz.
- Haberleri hemen toplamak için deponun sahibi Actions → Haberleri topla ve siteyi yayimla → Run workflow seçer.
- Notlar, yıldızlı haberler ve takip kelimeleri yalnızca o tarayıcının yerel deposundadır. Başka cihazlarla paylaşılmaz; tarayıcı verileri temizlenince silinir. İndirilen CSV/brifing ilgili kişisel notları içerebilir.
- Site herkese açıktır. Yalnızca kamuya açık haber başlıkları, kaynaklar, tarih ve bağlantılar yayımlanır. Yerel SQLite veritabanı, notlar veya günlükler yüklenmez.

## GitHub'a yayımlama

1. Kendi GitHub hesabınızda `erzurum-gundem` adlı **public** bir depo oluşturun.
2. Bu klasörün içeriklerini deponun köküne `main` dalında gönderin. `.github/workflows/publish.yml` dahil olmalı. `data/` ve `dist/` Git tarafından dışlanır; bunları ayrıca yüklemeyin.
3. Deponun Settings → Pages → Build and deployment → Source alanını **GitHub Actions** yapın.
4. Actions sekmesinde **Haberleri topla ve siteyi yayimla** iş akışını çalıştırın. Başarılı `deploy` adımının verdiği adres gerçek site bağlantısıdır. Yayım başarıyla doğrulanmadan bağlantıyı çalışıyor saymayın.

Pages proje adresi normalde `https://KULLANICI.github.io/erzurum-gundem/` biçimindedir. Hesap ve depo adı gerçek adlarla değiştirilmelidir. Özel alan adı gerekmez. Kurum politikaları Actions veya Pages kullanımını kısıtlayabilir.

GitHub Free'de public depo ve standart GitHub-hosted runner kullanımı bu tasarım için ücretsizdir; ücretli runner veya üçüncü taraf hizmet kullanılmaz. Güncel kullanım koşulları: https://docs.github.com/en/actions/concepts/billing-and-usage ve https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits

## Güncelleme ve arşiv

Altı Google Haberler RSS sorgusu son 7 günü tarar. Başlık ve kaynak bazında tekrarlar ayıklanır. `archive.json` yalnızca kamuya açık alanları içerir; son 365 günlük kayıtlar korunur. Günlük iş bu arşivi depoya kaydeder, ardından `dist/` klasörünü Pages'e yayımlar. Böylece işin her çalışmasında arşiv sıfırlanmaz.

Bazı kaynaklar çalışmazsa ulaşılabilen kayıtlar yayımlanır, panel başarısız akışları gösterir. Tam bağlantı kesintisinde eski arşiv korunur ve hata durumu yayımlanır. Kullanılabilir arşiv de yoksa iş başarısız olur; mevcut canlı site değiştirilmez. Son başarılı tarama üzerinden 36 saat geçerse panel eskilik uyarısı gösterir.

Google'ın dizin ve sonuç sınırları nedeniyle bütün haberleri kapsama garantisi yoktur. İlçe/konu etiketleri başlık eşleşmelerinden çıkar; teyit edilmelidir. Brifing başlık derlemesidir, haber metni özeti değildir.

GitHub, public depolarda 60 gün etkinlik olmadığında zamanlanmış işleri durdurabilir. Actions bölümündeki durum ve paneldeki son tarama tarihini kontrol edin. Gerekirse iş akışını yeniden etkinleştirin. Kaynak: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows

## Yerel doğrulama

```text
python -m unittest discover -s . -p 'test_*.py' -v
python build.py
python -m http.server 8766 --bind 127.0.0.1 --directory dist
```

`python build.py --no-refresh` arşivi yeniden kullanarak internetten tarama yapmadan site üretir. Yayına gönderilen klasör yalnızca `dist/` olmalıdır; depo kökünü web sunucusu olarak açmayın.
