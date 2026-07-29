import os
from dotenv import load_dotenv

# .env dosyasındaki OPENAI_API_KEY'i otomatik yükle
load_dotenv()

# API Key kontrolü
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("❌ OPENAI_API_KEY bulunamadı! Lütfen .env dosyanıza veya sistem ortam değişkenlerine ekleyin.")

try:
    # Güncel paket yapısı
    from langchain_chroma import Chroma
except ImportError:
    # Eski paket yapısı (fallback)
    from langchain_community.vectorstores import Chroma

from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

# Projedeki ChromaDB dizini ile eşleşecek şekilde
CHROMA_PATH = "./database/mevzuat"

def msha_iso_mermer_verilerini_yukle():
    documents = [
        # --- ISO 45001 MADDELERİ ---
        Document(
            page_content="ISO 45001 Madde 6.1.2: Tehlikelerin tanımlanması ve risklerin ve fırsatların değerlendirilmesi. Kuruluş, sürekli ve önleyici bir tehlike tanımlama süreci kurmalı, uygulamalı ve sürdürmelidir. Kimyasal, fiziksel ve havalandırma yetersizlikleri acil risk sınıfındadır.",
            metadata={"kaynak": "ISO 45001:2018", "kategori": "Uluslararası Standart", "standart": "ISO"}
        ),
        Document(
            page_content="ISO 45001 Madde 8.1.2: Tehlikeleri ortadan kaldırma ve İSG risklerini azaltma (Hiyerarşi): 1. Tehlikeyi ortadan kaldır, 2. Tehlikeli olanı daha az tehlikeli ile değiştir, 3. Mühendislik kontrollerini ve sistemlerini uygula (Örn: Otomatik havalandırma ve gaz kesme sensörleri).",
            metadata={"kaynak": "ISO 45001:2018", "kategori": "Uluslararası Standart", "standart": "ISO"}
        ),
        
        # --- MSHA STANDARTLARI ---
        Document(
            page_content="MSHA Standard 30 CFR § 75.323: Yeraltı Kömür ve Metal/Ametal Madenlerinde Metan Gazı Limitleri. Dönüş havasındaki metan (CH4) oranı %1.0 ulaştığında havalandırma artırılmalıdır. CH4 oranı %1.5 ulaştığında ilgili bölgedeki tüm elektrikli ekipmanlar derhal kesilmeli ve alan tahliye edilmelidir.",
            metadata={"kaynak": "MSHA 30 CFR § 75.323", "kategori": "Maden Mevzuatı", "standart": "MSHA"}
        ),
        Document(
            page_content="MSHA Standard 30 CFR § 75.321: Hava Kalitesi ve Oksijen Oranı. Yeraltı çalışma alanlarında hava en az %19.5 Oksijen (O2) içermelidir ve Karbonmonoksit (CO) seviyesi hiçbir koşulda 50 ppm (TWA) değerini aşamaz. 12-25 ppm arası dikkatle izlenmelidir.",
            metadata={"kaynak": "MSHA 30 CFR § 75.321", "kategori": "Maden Mevzuatı", "standart": "MSHA"}
        ),
        Document(
            page_content="MSHA LOTO (Lockout/Tagout) Standardı 30 CFR § 56.12016: Bakım veya tamir yapılmadan önce tüm enerji kaynakları (elektrik, pnömatik, hidrolik) kapatılmalı, kilitlenmeli ve etiketlenmelidir. Ekipman arızasında LOTO uygulanmadan müdahale edilemez.",
            metadata={"kaynak": "MSHA 30 CFR § 56.12016", "kategori": "Uluslararası Ekipman Güvenliği", "standart": "MSHA"}
        ),

        # --- SÖĞÜT MERMER & DOĞALTAŞ OCAKLARI ÖZEL STANDARTLARI ---
        Document(
            page_content="Mermer Ocaklarında Şev ve Basamak Güvenliği: Açık işletme mermer ocaklarında basamak yüksekliği, kullanılan iş makinesinin maksimum erişim yüksekliğini aşamaz. Şev açısı kaya yapısının çatlak ve eklem durumuna göre belirlenmeli, gevşek bloklar derhal arındırılmalıdır.",
            metadata={"kaynak": "Açık İşletmeler İSG Yönetmeliği", "kategori": "Mermer Madenciliği"}
        ),
        Document(
            page_content="Mermer Tel Kesme Güvenliği: Elmas tel kesme makinesi çalışırken, tel kopma riski ve fırlama açısı dikkate alınarak tel doğrultusunda en az 30 metre yarıçaplı güvenlik alanı oluşturulmalı ve personel bu alana girmemelidir.",
            metadata={"kaynak": "Mermer İSG Standartları", "kategori": "Ekipman Güvenliği"}
        ),
        Document(
            page_content="MSHA 30 CFR § 56.9300 - Nakliyat Yolları ve Döküm Sahaları Emniyet Setleri (Berms): Ağır iş makinelerinin çalıştığı ocak içi nakliyat yollarında ve kademe kenarlarında, kullanılan en büyük iş makinesi tekerlek yüksekliğinin en az yarısı (1/2) yüksekliğinde toprak/taş koruma seti (berm) bulunması zorunludur.",
            metadata={"kaynak": "MSHA 30 CFR § 56.9300", "kategori": "Açık Ocak Araç Emniyeti"}
        )
    ]
    
    embeddings = OpenAIEmbeddings()
    vector_store = Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=embeddings,
        collection_name="arin_isg_hafiza"
    )
    
    vector_store.add_documents(documents)
    print(f"✅ Toplam {len(documents)} adet ISO, MSHA ve Söğüt Mermer Ocağı standardı ChromaDB'ye başariyla işlendi!")

if __name__ == "__main__":
    msha_iso_mermer_verilerini_yukle()