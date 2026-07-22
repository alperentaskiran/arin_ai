import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Proje kök dizinini ekle
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.rag_engine import RagEngine

def main():
    print("==================================================")
    print("🔥 ARIN AI - RAG & JEOLOJİ/MTA TESTİ BAŞLATILIYOR")
    print("==================================================\n")

    rag = RagEngine()

    # ----------------------------------------------------
    # TEST 1: Doğrudan Jeoloji & MTA Arama Testi
    # ----------------------------------------------------
    print("📌 TEST 1: MTA / Jeoloji Arama Fonksiyonu Test Ediliyor...")
    jeoloji_sorgu = "Zonguldak taşkömürü havzası ve grizu riski"
    jeoloji_sonuc = rag.jeoloji_ara_ozetli(jeoloji_sorgu)
    
    print("\n[Jeoloji Arama Çıktısı]:")
    print(jeoloji_sonuc)
    print("\n" + "="*50 + "\n")

    # ----------------------------------------------------
    # TEST 2: 360° Saha Raporu Analizi (Mevzuat + Kaza + Jeoloji)
    # ----------------------------------------------------
    print("📌 TEST 2: Saha Vardiya Raporu Analizi (360° RAG + 5x5 Risk Matrisi)...")
    
    ornek_vardiya_raporu = """
    Vardiya: 08:00 - 16:00 (Yeraltı - Zonguldak Havzası 3. Ayna)
    Saha Notları:
    - 3. Ayna ilerlemesinde tavan kayacında killi şist yapısı sebebiyle yer yer çatlaklar ve kılcal dökülmeler gözlendi.
    - Metan (CH4) sensörü %1.4 seviyesini gösterdi.
    - Ahşap tahkimat kamalarında esneme tespit edildi, ancak imalatı durdurmadan ilerlemeye devam edildi.
    """

    analiz_sonucu = rag.saha_raporu_analiz_et(ornek_vardiya_raporu)

    print("\n[360° Saha Analizi ve Risk Matrisi Çıktısı]:")
    print(analiz_sonucu)

if __name__ == "__main__":
    main()