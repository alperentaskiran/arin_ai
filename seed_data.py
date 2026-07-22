# seed_data.py
import sqlite3
from rag_service import RAGService

def seed_database():
    print("🔄 Eski veritabanı kayıtları temizleniyor...")
    conn = sqlite3.connect("arin_knowledge.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM knowledge_base")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='knowledge_base'")
    conn.commit()
    conn.close()

    rag = RAGService()
    
    # 1. Mevzuat Verileri
    print("📥 Mevzuat verileri yapılandırılarak ekleniyor...")
    rag.add_document(
        source_type="mevzuat",
        title="Maden İşyerlerinde İSG Yönetmeliği - Madde 7 (Havalandırma)",
        content=(
            "Yeraltı madenlerinde havalandırma mekanik sistemle sağlanır. "
            "Hava akımı, en az iki bağımsız yolla yerüstüne bağlanmalıdır. "
            "Oksijen oranı %19'dan az, karbondioksit oranı %0.5'ten fazla olamaz. "
            "Metan oranı %1'e ulaştığında elektrikli cihazlar kesilir, %1.5'te tahliye başlar."
        ),
        metadata={
            "maden_turu": "yeraltı",
            "risk_kategorisi": "havalandırma_gaz",
            "ilgili_madde": "Madde 7",
            "yasal_sinir": "CH4_%1.5"
        }
    )
    
    rag.add_document(
        source_type="mevzuat",
        title="Maden İşyerlerinde İSG Yönetmeliği - Ek-3 (Tahkimat)",
        content=(
            "Yeraltı çalışmalarında tavan ve yan duvarların kendi kendini taşıyamayacağı "
            "durumlarda tahkimat yapılması zorunludur. Tahkimat planı maden mühendisi tarafından "
            "hazırlanır ve düzenli olarak kontrol edilerek kayıt altına alınır."
        ),
        metadata={
            "maden_turu": "yeraltı",
            "risk_kategorisi": "tahkimat_gocuk",
            "ilgili_madde": "Ek-3",
            "sorumlu": "maden_muhendisi"
        }
    )

    # 2. Kaza Raporları
    print("📥 Kaza raporları metaverileriyle birlikte ekleniyor...")
    
    rag.add_document(
        source_type="kaza_raporu",
        title="Soma Maden Faciası İnceleme Raporu - Sensör ve Havalandırma Hatası",
        content=(
            "Soma kazasındaki temel ihmallerden biri, karbonmonoksit sensörlerinin sürekli limit "
            "üstü değer vermesine rağmen maden yönetiminin üretime devam etmesidir. Ayrıca, "
            "havalandırma yönünün ters çevrilmesi yangın dumanının kaçış yollarına dolmasına neden olmuştur."
        ),
        metadata={
            "maden_turu": "yeraltı",
            "kaza_tipi": "yangin_gaz",
            "yil": "2014",
            "kok_neden": "sensor_ihmali_yanlis_havalandirma_yonu"
        }
    )
    
    rag.add_document(
        source_type="kaza_raporu",
        title="İliç Altın Madeni Kazası Raporu - Yığın Liçi Kayması",
        content=(
            "İliç'teki liç sahasında meydana gelen kaymanın temel nedeni, yığın liç yüksekliğinin "
            "proje limitlerinin çok üzerine çıkması, şev açılarının dikleşmesi ve sızdırmazlık "
            "izleme sistemlerindeki (inklinometre) uyarıların saha mühendisleri tarafından göz ardı edilmesidir."
        ),
        metadata={
            "maden_turu": "acik_isletme",
            "kaza_tipi": "sev_kaymasi_heyelan",
            "yil": "2024",
            "kok_neden": "limit_asimi_sensor_ihmali"
        }
    )

    rag.add_document(
        source_type="kaza_raporu",
        title="Amasra Maden Faciası İnceleme Raporu - Metan ve Havalandırma İhlali",
        content=(
            "Amasra'da meydana gelen grizu patlamasının temel teknik nedeni, ocak havalandırma sisteminin "
            "yetersiz kalması ve metan gazı (CH4) seviyesinin yasal alarm sınırı olan %1.5 seviyesini aşmasına "
            "rağmen üretime proaktif olarak ara verilmemesidir. Sensörlerin erken uyarı sinyalleri "
            "maden komuta merkezi tarafından anlık izlenmemiş, fan arızaları giderilmeden vardiyaya devam edilmiştir."
        ),
        metadata={
            "maden_turu": "yeraltı",
            "kaza_tipi": "grizu_patlamasi",
            "yil": "2022",
            "kok_neden": "yetersiz_havalandirma_sensor_ihmali"
        }
    )

    rag.add_document(
        source_type="kaza_raporu",
        title="Ermenek Maden Kazası Raporu - Eski İmalat ve Su Baskını İhlali",
        content=(
            "Ermenek'teki maden ocağında yaşanan facianın ana sebebi, eski imalat alanlarında ve kapatılmış "
            "galerilerde biriken büyük hacimli yeraltı sularının, yeni üretim yapılan galeriye doğru patlama yapmasıdır. "
            "Mevzuatta yer alan sondaj ve kontrol kuyusu açma yükümlülüklerinin yerine getirilmemesi "
            "iş sağlığı ve güvenliği zincirinin kırılmasına yol açmıştır."
        ),
        metadata={
            "maden_turu": "yeraltı",
            "kaza_tipi": "su_baskini",
            "yil": "2014",
            "kok_neden": "eski_imalat_sondaj_eksikligi"
        }
    )

    rag.add_document(
        source_type="kaza_raporu",
        title="Kozlu Maden Faciası Raporu - Kömür Degajı ve Erken Uyarı Eksikliği",
        content=(
            "Kozlu'da yaşanan grizu patlaması ve ani kömür degajı, derin madencilik operasyonlarında "
            "gaz drenajı (metan tahliyesi) çalışmalarının yetersizliğini ortaya koymuştur. Dinamit patlatmaları "
            "öncesinde yapılan gaz ölçümlerinin yasal sınırlara riayet etmemesi ve erken uyarı sistemlerinin "
            "entegrasyon eksikliği nedeniyle işçilerin tahliyesi zamanında gerçekleştirilememiştir."
        ),
        metadata={
            "maden_turu": "yeraltı",
            "kaza_tipi": "ani_degaj_grizu",
            "yil": "1992",
            "kok_neden": "yetersiz_drenaj_erken_uyari_eksikligi"
        }
    )

    print("✅ Veri tabanı metaveri mimarisiyle başarıyla güncellendi!")

if __name__ == "__main__":
    seed_database()