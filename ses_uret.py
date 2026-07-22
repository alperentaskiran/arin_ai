from gtts import gTTS
import os

# Jürinin hayran kalacağı profesyonel İSG ses raporu metni
metin = (
    "Vardiya amiri Alperen Taşkıran rapor ediyor. Bugün kot eksi iki yüz kırk üretim panosunda "
    "yaptığımız incelemelerde, arın bölgesine yakın tavan bloklarında hafif dökülmeler "
    "ve yer yer çatlama sesleri tespit ettik. Tahkimat ustasını uyardım ancak üretime ara vermedik, "
    "çalışmaya devam ediyoruz. Ayrıca ana nakliye bandının koruyucu kafesi yerinden çıkmış durumda "
    "ve tambur açıkta dönüyor, ciddi uzuv kaybı riski var. Acil aksiyon alınmasını talep ediyorum."
)

print("🔊 Ses dosyası yapay zeka tarafından oluşturuluyor...")

# Google Text-to-Speech kullanarak Türkçe ses dosyası üretiyoruz
tts = gTTS(text=metin, lang='tr')
tts.save("test_isg.mp3")

print("✅ Başarılı! 'test_isg.mp3' dosyası klasöründe oluşturuldu.")