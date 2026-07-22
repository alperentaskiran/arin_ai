"""
Arın AI - RAG Engine, Multi-Agent, Shift Memory & LOTO Equipment Entegrasyon Modülü
Aethel Technologies - 2026
"""

import os
import json
import logging
from datetime import datetime

# ==========================================
# CHROMA VE RUST KİLİTLENMELERİNİ ENGELLEYEN AYARLAR
# (Importlardan önce tanımlanması zorunludur)
# ==========================================
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_SERVER_NOFILE"] = "1"

from openai import OpenAI
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

# Logging Yapılandırması
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ArinAI_RagEngine")

# --- KÖK DİZİN (ABSOLUTE PATH) AYARLAMASI ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- 1. ADIM: SAHA LOKASYON HİYERARŞİSİ VE RİSK MATRİSİ ---
LOCATIONS_RISK_MATRIX = {
    "YERALTI_AYNA": {
        "title": "Üretim Aynası / Hazırlık Galerisi",
        "primary_risks": ["Ani Gaz Debisi (Metan/CO)", "Kaya Düşmesi / Göçük", "Toz Yoğunluğu"],
        "critical_checks": ["Gaz Dedektörü Kalibrasyonu", "Tahkimat ve Pasaj Kontrolü", "Su Perdesi / Toz Bastırma"]
    },
    "GALERI_KOR": {
        "title": "Kör Galeri / Havalandırma Uç Noktası",
        "primary_risks": ["Yetersiz Oksijen (O2 Boğulma)", "Tehlikeli Gaz Birikmesi", "Tıkalı/Devre Dışı Tali Fan"],
        "critical_checks": ["Tali Fan Çalışma Durumu", "Anlık O2 ve CH4 Ölçümü", "Yedek Güç Hattı"]
    },
    "NAKLIYAT_HATTI": {
        "title": "Ana Nakliyat & Konveyör Bant Hattı",
        "primary_risks": ["Bant Sürtünmesi ve Yangın Riskleri", "Mekanik Sıkışma / Uzuv Kaptırma", "Yüksek Gürültü ve İnce Toz"],
        "critical_checks": ["Acil Stop İp/Tel Mekanizması", "Bant Kayma Sensörü", "Otomatik Yangın Söndürme Nozulları"]
    },
    "ACIK_OCAK_KIRMA": {
        "title": "Kırma-Eleme Tesisleri / Açık Ocak Şantiye Alanı",
        "primary_risks": ["Solunabilir Kuvars Tozu", "Ağır İş Makinesi Trafiği", "Yüksekten Düşme"],
        "critical_checks": ["Toz Bastırma Fıskiyeleri", "Görünürlük ve Siren / KKD Kontrolü", "LOTO (Kilitleme/Etiketleme)"]
    }
}

# --- 4. ADIM: EKİPMAN (MAKİNE PARKI) VE LOTO MATRİSİ ---
EQUIPMENT_RISK_MATRIX = {
    "FAN_SISTEMI": {
        "name": "Ana / Tali Havalandırma Fanı",
        "risks": ["Gaz Birikimi (CH4/CO)", "Oksijensiz Kalma", "Elektrik Kontağı Yangını"],
        "loto_protocol": "Panodan enerji kesilmeli, LOTO kilidi asılmalı. Ex-proof gaz ölçümü yapılmadan müdahale yasaktır."
    },
    "KONVEYOR_BANT": {
        "name": "Konveyör Bant / Vagon Sistemi",
        "risks": ["Rulman Sürtünmesi (Yangın)", "Uzuv Kaptırma", "Kömür Tozu Patlaması"],
        "loto_protocol": "Acil stop teli çekilmeli. Motor şalteri kilitlenmeli, bantta biriken kömür tozu yıkanarak temizlenmeli."
    },
    "TRAFO_ELEKTRIK": {
        "name": "Yeraltı Trafosu / Dağıtım Panosu",
        "risks": ["Ark Parlaması", "Yüksek Voltaj Çarpılması", "İzolasyon Yağı Yangını"],
        "loto_protocol": "Ana kesici açılmalı, topraklama ıstakası takılmalı. Sadece yetkili YG personeli müdahale edebilir."
    },
    "IS_MAKINESI": {
        "name": "Yükleyici / Ekskavatör / LHD",
        "risks": ["Kör Nokta Çarpması", "Hidrolik Boşalması", "Fren Kaybı"],
        "loto_protocol": "Makine düz zemine park edilmeli, kova yere indirilmeli, tekerleklere takoz konmalı ve kontak anahtarı alınmalı."
    }
}


class RagEngine:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        
        # Mutlak Yollar (Absolute Paths)
        self.mevzuat_path = os.path.join(BASE_DIR, "database", "mevzuat")
        self.kazalar_path = os.path.join(BASE_DIR, "database", "kazalar")
        self.jeoloji_path = os.path.join(BASE_DIR, "database", "jeoloji")
        self.memory_file = os.path.join(BASE_DIR, "database", "shift_memory.json")

        # Canlı Web Arama Aracı Güvenli Yükleme
        self.web_search = None
        try:
            from langchain_community.tools import DuckDuckGoSearchRun
            self.web_search = DuckDuckGoSearchRun()
        except Exception as e:
            logger.warning(f"Web arama aracı pasif hale getirildi: {e}")

        # Güvenli Chroma Yükleme Fonksiyonu
        def safe_load_chroma(path):
            try:
                db_file = os.path.join(path, "chroma.sqlite3")
                if os.path.exists(db_file):
                    return Chroma(persist_directory=path, embedding_function=self.embeddings)
                else:
                    logger.warning(f"Veritabanı dosyası bulunamadı: {db_file}")
            except Exception as e:
                logger.error(f"Chroma yükleme hatası ({path}): {e}")
            return None

        self.db_mevzuat = safe_load_chroma(self.mevzuat_path)
        self.db_kazalar = safe_load_chroma(self.kazalar_path)
        self.db_jeoloji = safe_load_chroma(self.jeoloji_path)
        
        # Hafıza Dosyasını Başlat
        self._init_memory_file()

    # --- HAFIZA (MEMORY) FONKSİYONLARI ---
    def _init_memory_file(self):
        """Vardiya hafızası için JSON dosyası oluşturur."""
        try:
            os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
            if not os.path.exists(self.memory_file):
                with open(self.memory_file, "w", encoding="utf-8") as f:
                    json.dump({"shift_records": []}, f, indent=4)
        except Exception as e:
            logger.error(f"Hafıza dosyası oluşturma hatası: {e}")

    def save_to_memory(self, location_key: str, report_text: str, ch4_level: float = None):
        """Analizi yapılan vardiyayı lokasyon bazlı hafızaya kaydeder."""
        try:
            if not os.path.exists(self.memory_file):
                self._init_memory_file()

            with open(self.memory_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            record = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "location": location_key,
                "report_summary": report_text[:150] + "...",
                "ch4_level": ch4_level
            }
            data.setdefault("shift_records", []).append(record)
            
            if len(data["shift_records"]) > 50:
                data["shift_records"] = data["shift_records"][-50:]

            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Hafızaya kaydetme hatası: {e}")

    def get_location_history(self, location_key: str, limit: int = 3) -> str:
        """Belirtilen lokasyonun geçmiş vardiya verilerini getirir."""
        try:
            if not os.path.exists(self.memory_file):
                return "Bu lokasyon için geçmiş vardiya kaydı bulunamadı."

            with open(self.memory_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            history = [r for r in data.get("shift_records", []) if r.get("location") == location_key]
            recent_history = history[-limit:]
            
            if not recent_history:
                return "Bu lokasyon için geçmiş vardiya kaydı bulunamadı."
                
            history_text = "--- GEÇMİŞ VARDİYA TRENDLERİ ---\n"
            for i, r in enumerate(recent_history):
                ch4_str = f"| CH4: %{r['ch4_level']}" if r.get('ch4_level') is not None else ""
                history_text += f"[{i+1}] Tarih: {r['timestamp']} {ch4_str} | Özet: {r['report_summary']}\n"
            return history_text
        except Exception as e:
            logger.error(f"Hafıza okuma hatası: {e}")
            return "Hafıza okunamadı."

    def extract_metrics_from_report(self, report_text: str) -> float:
        """Rapordan basit kural tabanlı Metan (CH4) oranını çeker."""
        import re
        match = re.search(r'(?:ch4|metan).*?(?:%)\s*(\d+\.?\d*)', report_text.lower())
        if not match:
            match = re.search(r'(?:%)\s*(\d+\.?\d*).*?(?:ch4|metan)', report_text.lower())
        
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return None

    # --- LOKASYON & EKİPMAN TESPİTİ ---
    def detect_location(self, report_text: str) -> tuple:
        text_lower = report_text.lower()
        
        if any(k in text_lower for k in ["kör galeri", "uzatma", "dip", "tıkalı"]):
            return LOCATIONS_RISK_MATRIX["GALERI_KOR"], "GALERI_KOR"
        elif any(k in text_lower for k in ["bant", "nakliyat", "vagon", "varagel", "konveyör", "desandre"]):
            return LOCATIONS_RISK_MATRIX["NAKLIYAT_HATTI"], "NAKLIYAT_HATTI"
        elif any(k in text_lower for k in ["kırma", "eleme", "tesis", "şantiye", "konkasör", "açık ocak"]):
            return LOCATIONS_RISK_MATRIX["ACIK_OCAK_KIRMA"], "ACIK_OCAK_KIRMA"
        else:
            return LOCATIONS_RISK_MATRIX["YERALTI_AYNA"], "YERALTI_AYNA"

    def detect_equipment(self, report_text: str) -> dict:
        text_lower = report_text.lower()
        found_equipment = {}

        if any(k in text_lower for k in ["fan", "havalandırma", "aspiratör", "vantilatör"]):
            found_equipment["FAN_SISTEMI"] = EQUIPMENT_RISK_MATRIX["FAN_SISTEMI"]
        if any(k in text_lower for k in ["bant", "konveyör", "tambur", "rulman"]):
            found_equipment["KONVEYOR_BANT"] = EQUIPMENT_RISK_MATRIX["KONVEYOR_BANT"]
        if any(k in text_lower for k in ["trafo", "elektrik", "pano", "kablo", "şalter", "voltaj"]):
            found_equipment["TRAFO_ELEKTRIK"] = EQUIPMENT_RISK_MATRIX["TRAFO_ELEKTRIK"]
        if any(k in text_lower for k in ["yükleyici", "lhd", "ekskavatör", "kamyon", "fren", "fayton"]):
            found_equipment["IS_MAKINESI"] = EQUIPMENT_RISK_MATRIX["IS_MAKINESI"]

        return found_equipment
            
    # --- ARAMA FONKSİYONLARI ---
    def canli_web_ara(self, sorgu: str) -> str:
        if not self.web_search:
            return "Canlı arama aracı yapılandırılamadı."
        try:
            logger.info(f"🌐 Canlı Web Taraması Başlatılıyor: '{sorgu}'")
            arama_sorgusu = f"site:mevzuat.gov.tr OR site:resmigazete.gov.tr maden ISG {sorgu}"
            sonuc = self.web_search.run(arama_sorgusu)
            return f"--- CANLI WEB TARAMA SONUÇLARI ---\n{sonuc}" if sonuc else "Canlı aramada sonuç bulunamadı."
        except Exception as e:
            logger.error(f"Canlı web aramasında hata: {e}")
            return f"Canlı arama hatası: {e}"

    def mevzuat_ara(self, sorgu: str, k: int = 8, score_threshold: float = 0.75, use_mmr: bool = True) -> str:
        if not self.db_mevzuat:
            logger.warning("Mevzuat veritabanı bulunamadı/yüklenemedi. Canlı aramaya geçiliyor...")
            return self.canli_web_ara(sorgu)
            
        try:
            if use_mmr:
                retriever = self.db_mevzuat.as_retriever(
                    search_type="mmr",
                    search_kwargs={"k": k, "fetch_k": 30, "lambda_mult": 0.7}
                )
                docs = retriever.invoke(sorgu)
                if docs:
                    return "\n\n".join([doc.page_content for doc in docs])
            
            sonuclar_ile_skor = self.db_mevzuat.similarity_search_with_score(sorgu, k=k)
            filtrelenmis = [doc.page_content for doc, score in sonuclar_ile_skor if score < score_threshold]
            
            if not filtrelenmis:
                if sonuclar_ile_skor:
                    return "\n\n".join([doc.page_content for doc, score in sonuclar_ile_skor[:3]])
                return self.canli_web_ara(sorgu)
                
            return "\n\n".join(filtrelenmis)
        except Exception as e:
            logger.error(f"Mevzuat aramasında hata: {e}")
            return self.canli_web_ara(sorgu)

    def kaza_raporu_ara(self, sorgu: str, k: int = 6) -> str:
        if not self.db_kazalar:
            return "Kaza raporları veritabanı bulunamadı."
        try:
            sonuclar = self.db_kazalar.similarity_search(sorgu, k=k)
            return "\n\n".join([doc.page_content for doc in sonuclar]) if sonuclar else "İLGİLİ_KAZA_KAYDI_BULUNAMADI"
        except Exception as e:
            return f"Kaza aramasında hata: {e}"

    def jeoloji_ara(self, sorgu: str, k: int = 6) -> str:
        if not self.db_jeoloji:
            return "MTA / Jeoloji veritabanı bulunamadı."
        try:
            sonuclar = self.db_jeoloji.similarity_search(sorgu, k=k)
            return "\n\n".join([doc.page_content for doc in sonuclar]) if sonuclar else "İLGİLİ_JEOLOJİ_KAYDI_BULUNAMADI"
        except Exception as e:
            return f"Jeoloji aramasında hata: {e}"

    # --- 2. ADIM: ÇOKLU AJAN (CREW SIMULATION), HAFIZA & LOTO ENTEGRASYONU ---
    def saha_raporu_analiz_et(self, vardiya_raporu: str) -> dict:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return {"error": "⚠️ OPENAI_API_KEY eksik."}

        location_info, loc_key = self.detect_location(vardiya_raporu)
        equipment_info = self.detect_equipment(vardiya_raporu)
        ch4_level = self.extract_metrics_from_report(vardiya_raporu)

        eq_text = ""
        if equipment_info:
            eq_text = "Tespit Edilen Kritik Ekipmanlar ve LOTO Prosedürleri:\n"
            for key, info in equipment_info.items():
                eq_text += f"- {info['name']}:\n  Riskler: {', '.join(info['risks'])}\n  Zorunlu LOTO: {info['loto_protocol']}\n"

        shift_history = self.get_location_history(loc_key, limit=3)
        self.save_to_memory(loc_key, vardiya_raporu, ch4_level)

        mevzuat_bg = self.mevzuat_ara(vardiya_raporu, k=8)
        kaza_bg = self.kaza_raporu_ara(vardiya_raporu, k=6)
        jeoloji_bg = self.jeoloji_ara(vardiya_raporu, k=6)
        
        birlesik_rag = f"--- MEVZUAT BİLGİLERİ ---\n{mevzuat_bg}\n\n--- JEOLOJİ VE MTA ---\n{jeoloji_bg}\n\n--- GEÇMİŞ KAZALAR ---\n{kaza_bg}"

        client = OpenAI(api_key=api_key)

        prompt_isg = f"""
        Sen tavizsiz bir Maden İSG Başdenetçisisin.
        LOKASYON: {location_info['title']}
        KRİTİK KONTROLLER: {location_info['critical_checks']}
        
        EKİPMAN DURUMU:
        {eq_text if eq_text else "Spesifik bir makine arızası belirtilmedi."}
        
        GEÇMİŞ VARDİYA TRENDİ:
        {shift_history}
        
        ANLIK SAHA VARDİYA RAPORU: "{vardiya_raporu}"
        RAG / MEVZUAT VERİSİ:\n{birlesik_rag}
        
        GÖREVİN: Üretimi ve maliyeti tamamen göz ardı et. Varsa EKİPMAN DURUMU'ndaki LOTO (Kilitleme) prosedürünün uygulanıp uygulanmadığını sorgula. Geçmiş trendleri dikkate alarak hayati tehlikeleri, mevzuat ihlallerini ve durdurulması gereken riskleri net, sert ve tavizsiz bir dille raporla.
        """

        prompt_uretim = f"""
        Sen Kıdemli Maden İşletme Mühendisisin.
        LOKASYON: {location_info['title']}
        EKİPMAN DURUMU: {eq_text if eq_text else "Normal"}
        GEÇMİŞ VARDİYA TRENDİ: {shift_history}
        ANLIK SAHA VARDİYA RAPORU: "{vardiya_raporu}"
        
        GÖREVİN: Üretim hedeflerini, imalatın aksamamasının önemini ve duruş maliyetlerini göz önünde tut. Eğer bir makine arızası varsa (örneğin Tali Fan veya Bant arızası) tüm galeriyi kapatmak yerine arızalı makineyi baypas edecek veya yedek ekipmanı devreye alacak pratik, hızlı ve operasyonel çözümler öner.
        """

        try:
            res_isg = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt_isg}],
                temperature=0.2
            ).choices[0].message.content

            res_uretim = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt_uretim}],
                temperature=0.3
            ).choices[0].message.content

            prompt_basmuhendis = f"""
            Sen Arın AI Maden İşletme Başmühendisisin (Karar Makamı).
            LOKASYON: {location_info['title']} 
            EKİPMAN BİLGİSİ VE ZORUNLU LOTO PROSEDÜRLERİ: {eq_text}
            GEÇMİŞ VARDİYA TRENDİ: {shift_history}
            
            ANLIK SAHA VARDİYA RAPORU: "{vardiya_raporu}"
            
            İSG DENETÇİSİ GÖRÜŞÜ:
            {res_isg}
            
            ÜRETİM MÜHENDİSİ GÖRÜŞÜ:
            {res_uretim}
            
            360° RAG KAYNAKLARI (Mevzuat + Kaza + Jeoloji):
            {birlesik_rag}
            
            GÖREVLERİN:
            1. **SON KARAR**: Geçmiş vardiya trendini, ekipman arızasını ve ajan görüşlerini sentezleyerek [ÜRETİM ACİL DURDURULMALI] / [ŞARTLI/TEDBİRLİ DEVAM] / [GÜVENLİ - DEVAM EDEBİLİR] etiketlerinden birini seç.
            2. **RİSK SKORLAMASI**: 5x5 Risk Matrisine göre Olasılık (1-5) x Şiddet (1-5) skoru belirle.
            3. **GEREKÇE**: İSG kanunu ve jeolojik verileri harmanlayarak gerekçeni açıkla. Ekipman arızası varsa LOTO protokolünün neden zorunlu olduğunu belirt.
            4. **DÖF PLANI (Düzeltici Önleyici Faaliyetler)**: Sahada hemen uygulanacak 3 net eylem adımı yaz (Biri mutlaka Ekipman LOTO/Bakım adımı olmalı).
            """

            res_final = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt_basmuhendis}],
                temperature=0.2
            ).choices[0].message.content

            return {
                "location": location_info,
                "equipment": equipment_info,
                "history": shift_history,
                "isg_agent": res_isg,
                "uretim_agent": res_uretim,
                "final_decision": res_final,
                "rag_sources": birlesik_rag
            }

        except Exception as e:
            logger.error(f"Saha raporu analiz hatası: {e}")
            return {"error": f"Analiz sırasında hata oluştu: {e}"}

    def _llm_ozetle(self, ham_metin: str, veri_tipi: str, sorgu: str = "", mod: str = "analiz") -> str:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return f"⚠️ API Anahtarı Eksik. Ham veri:\n\n{ham_metin}"
            
        client = OpenAI(api_key=api_key)
        
        if mod == "kaza":
            prompt = f"""
Sen Kıdemli Maden Kazaları ve Kök Neden Analiz Uzmanısın.
SANA İLETİLEN SAHA BİLDİRİMİ / ANOMALİ: "{sorgu}"
VERİTABANINDAN ÇEKİLEN GEÇMİŞ KAZA KESİTLERİ:\n---\n{ham_metin}\n---
GÖREVİN: Saha risklerini ele al, Türkiye/Dünya maden facialarıyla (Amasra, Soma vb.) kök neden bazında eşleştir.
"""
        elif mod == "jeoloji":
            prompt = f"""
Sen MTA Saha Raporları ve Maden Jeolojisi Uzmanısın.
SORGULANAN BÖLGE / TERİM: "{sorgu}"
VERİTABANINDAN ÇEKİLEN JEOLOJİ KESİTLERİ:\n---\n{ham_metin}\n---
GÖREVİN: Formasyon yapısını, cevher potansiyelini ve bölgeye özgü İSG risklerini açıkla.
"""
        else:
            prompt = f"""
Sen Arın AI Maden Mevzuat Danışmanısın.
KULLANICI SORUSU: "{sorgu}"
MEVZUAT VERİTABANI VE CANLI ARAMA KESİTLERİ:\n---\n{ham_metin}\n---
GÖREVİN: Sağlanan veritabanı/canlı arama kesitlerini öncelikli baz alarak soruyu yönetmelik maddeleriyle net bir şekilde yanıtla.
"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"⚠️ LLM Hatası ({e})."

    def mevzuat_ara_ozetli(self, sorgu: str, k: int = 8) -> str:
        ham_sonuc = self.mevzuat_ara(sorgu, k=k, score_threshold=0.75)
        return self._llm_ozetle(ham_sonuc, "maden mevzuatı", sorgu=sorgu, mod="mevzuat")

    def kaza_raporu_ara_ozetli(self, sorgu: str, k: int = 6) -> str:
        ham_sonuc = self.kaza_raporu_ara(sorgu, k=k)
        return self._llm_ozetle(ham_sonuc, "kaza raporu", sorgu=sorgu, mod="kaza")

    def jeoloji_ara_ozetli(self, sorgu: str, k: int = 6) -> str:
        ham_sonuc = self.jeoloji_ara(sorgu, k=k)
        return self._llm_ozetle(ham_sonuc, "jeoloji ve maden verisi", sorgu=sorgu, mod="jeoloji")