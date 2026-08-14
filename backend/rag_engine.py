"""
Arın AI - RAG Engine, Multi-Agent Debate Loop, Shift Memory, LOTO & Function Calling Modülü
Aethel Technologies - 2026
"""

import os
import json
import logging
import re
import requests
from datetime import datetime

# ==========================================
# CHROMA VE RUST KİLİTLENMELERİNİ ENGELLEYEN AYARLAR
# ==========================================
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_SERVER_NOFILE"] = "1"

from openai import OpenAI
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

# İSG Deterministik Motoru ve Araç Tanımları Entegrasyonu
from isg_engine import ISGRiskEngine, ARIN_TOOLS

# Logging Yapılandırması
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ArinAI_RagEngine")

# --- KÖK DİZİN (ABSOLUTE PATH) AYARLAMASI ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ==========================================
# 1. DİNAMİK MADEN TİPİ VE RİSK VERİTABANI
# ==========================================
DYNAMIC_RISK_DB = {
    "Mermer & Doğaltaş (Şev Stabilitesi & Tel Kesme)": {
        "lokasyonlar": ["Açık Ocak", "Kademeler", "Kırma Eleme", "Stok Alanı", "Elmas Tel Kesme Bölgesi"],
        "riskler": ["Şev Kayması", "Tel Kesme Makinesi Kopması / Tel Çarpması", "Ağır Tonajlı Blok Devrilmesi", "İş Makinesi Kör Nokta Kazası"],
        "loto_ekipmanlari": ["Ekskavatör", "Elmas Tel Kesme Makinesi", "Loder", "Kaya Delici (Rok)"]
    },
    "Kömür & Yeraltı Galerisi (Grizu / Havalandırma)": {
        "lokasyonlar": ["Yeraltı Ayna", "Kör Galeri", "Nakliyat Hattı", "Nefeslik"],
        "riskler": ["Grizu Patlaması", "Göçük / Tavan Çökmesi", "Karbonmonoksit Zehirlenmesi", "Toz İnfılakı"],
        "loto_ekipmanlari": ["Ana Emiş Fanı", "Konveyör Bant", "Yeraltı Trafosu", "Sürekli Kazıcı"]
    },
    "Değerli Metal (Altın, Gümüş - Siyanür / Atık Barajı)": {
        "lokasyonlar": ["Yığın Liç Alanı", "Atık Barajı", "Kimyasal Tesis (ADR)", "Açık Ocak"],
        "riskler": ["Siyanür Sızıntısı / Zehirlenme", "Atık Barajı Yırtılması / Taşması", "Ağır Metal Kontaminasyonu", "Şev Kayması"],
        "loto_ekipmanlari": ["Sirkülasyon Pompaları", "Siyanür Dozajlama Tankları", "Karıştırıcılar"]
    },
    "Metalik Madencilik (Bakır, Demir - Patlatma & Ağır Metal)": {
        "lokasyonlar": ["Açık Ocak", "Patlatma Patern Alanı", "Zenginleştirme Tesisi", "Kırma Eleme"],
        "riskler": ["Kontrolsüz Patlatma / Uçan Kaya", "Ağır Makine Çarpışması", "Asit Kaya Drenajı", "Toz Emisyonu"],
        "loto_ekipmanlari": ["Delici Makine", "Kırıcı Çeneler", "Değirmenler"]
    },
    "Nadir Toprak Elementleri & Endüstriyel (Kimyasal Risk)": {
        "lokasyonlar": ["Flotasyon Tesisi", "Açık Ocak / Galeri", "Kimyasal Depolama"],
        "riskler": ["Kimyasal Reaksiyon", "Radyasyon (NTE Ocağı ise)", "Toz Solunumu", "Korozyon / Asit Yanığı"],
        "loto_ekipmanlari": ["Flotasyon Hücreleri", "Asit Pompaları", "Basınçlı Kaplar"]
    }
}


class RagEngine:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Mutlak Yollar
        self.mevzuat_path = os.path.join(BASE_DIR, "database", "mevzuat")
        self.kazalar_path = os.path.join(BASE_DIR, "database", "kazalar")
        self.jeoloji_path = os.path.join(BASE_DIR, "database", "jeoloji")
        self.memory_file = os.path.join(BASE_DIR, "database", "shift_memory.json")

        # Canlı Web Arama Aracı
        self.web_search = None
        try:
            from langchain_community.tools import DuckDuckGoSearchRun
            self.web_search = DuckDuckGoSearchRun()
        except Exception as e:
            logger.warning(f"Web arama aracı pasif hale getirildi: {e}")

        def safe_load_chroma(path):
            try:
                db_file = os.path.join(path, "chroma.sqlite3")
                if os.path.exists(db_file):
                    return Chroma(persist_directory=path, embedding_function=self.embeddings)
            except Exception as e:
                logger.error(f"Chroma yükleme hatası ({path}): {e}")
            return None

        self.db_mevzuat = safe_load_chroma(self.mevzuat_path)
        self.db_kazalar = safe_load_chroma(self.kazalar_path)
        self.db_jeoloji = safe_load_chroma(self.jeoloji_path)
        self._init_memory_file()

    def _extract_domain(self, metin: str) -> str:
        match = re.search(r"\[Seçili Maden Tipi:\s*(.*?)\]", metin)
        if match:
            return match.group(1).strip()
        return "Kömür & Yeraltı Galerisi (Grizu / Havalandırma)"

    # --- HAFIZA (MEMORY) FONKSİYONLARI ---
    def _init_memory_file(self):
        try:
            os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
            if not os.path.exists(self.memory_file):
                with open(self.memory_file, "w", encoding="utf-8") as f:
                    json.dump({"shift_records": []}, f, indent=4)
        except Exception as e:
            logger.error(f"Hafıza dosyası oluşturma hatası: {e}")

    def save_to_memory(self, location_key: str, report_text: str, ch4_level: float = None):
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
            return "Hafıza okunamadı."

    def extract_metrics_from_report(self, report_text: str) -> float:
        match = re.search(r'(?:ch4|metan).*?(?:%)\s*(\d+\.?\d*)', report_text.lower())
        if not match:
            match = re.search(r'(?:%)\s*(\d+\.?\d*).*?(?:ch4|metan)', report_text.lower())
        
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return None

    # --- ARAÇ (TOOL) FONKSİYONLARI ---
    def canli_web_ara(self, sorgu: str) -> str:
        if not self.web_search:
            return "Canlı arama aracı yapılandırılamadı."
        try:
            logger.info(f"🌐 Canlı Web Taraması Başlatılıyor: '{sorgu}'")
            arama_sorgusu = f"site:mevzuat.gov.tr OR site:resmigazete.gov.tr maden ISG {sorgu}"
            sonuc = self.web_search.run(arama_sorgusu)
            return f"--- CANLI WEB TARAMA SONUÇLARI ---\n{sonuc}" if sonuc else "Canlı aramada sonuç bulunamadı."
        except Exception as e:
            return f"Canlı arama hatası: {e}"

    def hava_durumu_getir(self, lokasyon: str) -> str:
        """API Anahtarı gerektirmeyen wttr.in üzerinden hava durumu çeker."""
        try:
            logger.info(f"☁️ Hava Durumu Sorgulanıyor: '{lokasyon}'")
            url = f"https://wttr.in/{lokasyon}?format=%C+%t+%h+%p"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return f"{lokasyon} Anlık Hava Durumu (Durum/Sıcaklık/Nem/Yağış): {response.text.strip()}"
            else:
                return f"Hava durumu alınamadı. (HTTP {response.status_code})"
        except Exception as e:
            return f"Hava durumu API hatası: {e}"

    # --- RAG ARAMA FONKSİYONLARI ---
    def mevzuat_ara(self, sorgu: str, k: int = 8, score_threshold: float = 0.75) -> str:
        if not self.db_mevzuat:
            return self.canli_web_ara(sorgu)
        try:
            retriever = self.db_mevzuat.as_retriever(search_type="mmr", search_kwargs={"k": k, "fetch_k": 30, "lambda_mult": 0.7})
            docs = retriever.invoke(sorgu)
            if docs: return "\n\n".join([doc.page_content for doc in docs])
            
            sonuclar = self.db_mevzuat.similarity_search_with_score(sorgu, k=k)
            filtrelenmis = [doc.page_content for doc, score in sonuclar if score < score_threshold]
            return "\n\n".join(filtrelenmis) if filtrelenmis else self.canli_web_ara(sorgu)
        except Exception:
            return self.canli_web_ara(sorgu)

    def kaza_raporu_ara(self, sorgu: str, k: int = 6) -> str:
        if not self.db_kazalar: return "Kaza raporları veritabanı bulunamadı."
        try:
            sonuclar = self.db_kazalar.similarity_search(sorgu, k=k)
            return "\n\n".join([doc.page_content for doc in sonuclar]) if sonuclar else "İLGİLİ_KAZA_KAYDI_BULUNAMADI"
        except Exception: return "Hata"

    def jeoloji_ara(self, sorgu: str, k: int = 6) -> str:
        if not self.db_jeoloji: return "Jeoloji veritabanı bulunamadı."
        try:
            sonuclar = self.db_jeoloji.similarity_search(sorgu, k=k)
            return "\n\n".join([doc.page_content for doc in sonuclar]) if sonuclar else "İLGİLİ_JEOLOJİ_KAYDI_BULUNAMADI"
        except Exception: return "Hata"

    # ==========================================
    # 2. MÜNAZARA (DEBATE) DÖNGÜSÜ & FUNCTION CALLING
    # ==========================================
    def saha_raporu_analiz_et(self, vardiya_raporu: str) -> dict:
        if not self.client.api_key:
            return {"error": "⚠️ OPENAI_API_KEY eksik."}

        domain = self._extract_domain(vardiya_raporu)
        domain_context = DYNAMIC_RISK_DB.get(domain, DYNAMIC_RISK_DB["Kömür & Yeraltı Galerisi (Grizu / Havalandırma)"])

        ch4_level = self.extract_metrics_from_report(vardiya_raporu)
        shift_history = self.get_location_history(domain, limit=3)
        
        mevzuat_bg = self.mevzuat_ara(vardiya_raporu, k=6)
        kaza_bg = self.kaza_raporu_ara(vardiya_raporu, k=3)
        jeoloji_bg = self.jeoloji_ara(vardiya_raporu, k=3)
        
        birlesik_rag = f"--- MEVZUAT BİLGİLERİ ---\n{mevzuat_bg}\n\n--- JEOLOJİ VE MTA ---\n{jeoloji_bg}\n\n--- GEÇMİŞ KAZALAR ---\n{kaza_bg}"

        # --- ARAÇLARIN TANIMLANMASI (Function Calling + ISG Engine Araçları) ---
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "canli_web_ara",
                    "description": "Maden İSG mevzuatı veya iş güvenliği kuralları hakkında internette güncel arama yapar.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sorgu": {"type": "string", "description": "Aranacak anahtar kelimeler (Örn: 'mermer ocakları tel kesme makinesi güvenlik yönetmeliği')"}
                        },
                        "required": ["sorgu"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "hava_durumu_getir",
                    "description": "Özellikle açık ocak madenciliğinde şev stabilitesini etkileyen yağış, nem ve sıcaklık gibi anlık hava durumu verilerini getirir.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lokasyon": {"type": "string", "description": "Hava durumu sorgulanacak ilçe veya il (Örn: 'Söğüt, Bilecik')"}
                        },
                        "required": ["lokasyon"]
                    }
                }
            }
        ] + ARIN_TOOLS  # isg_engine.py içerisindeki l_tipi_matris, fine_kinney ve gurultu araçları dahil edildi

        # --- TUR 1: İSG AJANI (Araç Kullanma Yetkisiyle) ---
        prompt_isg = f"""
        LOKASYON BAZLI YAPISAL RİSKLER: {', '.join(domain_context['riskler'])}
        LOTO UYGULANABİLECEK EKİPMANLAR: {', '.join(domain_context['loto_ekipmanlari'])}
        
        GEÇMİŞ VARDİYA TRENDİ:
        {shift_history}
        
        RAG / MEVZUAT VERİSİ:
        {birlesik_rag}
        
        SAHA NOTU / SENSÖR VERİSİ:
        {vardiya_raporu}
        
        GÖREVİN: Güvenlik açısından en kötü senaryolara odaklan. 
        - Açık ocak (Mermer vb.) ise şev stabilitesi için hava durumu aracını tetikle.
        - Raporda desibel (dB), olasılık-şiddet veya frekans parametreleri varsa deterministik matematiksel araçları (l_tipi_matris, fine_kinney, gurultu_logaritmik_toplam) çağırarak kesin hesaplama yap.
        - Gerekirse işi durdurma talebini açıkça belirt.
        """

        messages_isg = [
            {"role": "system", "content": f"Sen tavizsiz bir Maden İSG Başdenetçisisin. Sektör: {domain}. Gerekirse mevzuat taraması, hava durumu veya matematiksel risk hesaplayıcı araçlarını tetikleyebilirsin."},
            {"role": "user", "content": prompt_isg}
        ]

        response_isg_initial = self.client.chat.completions.create(
            model="gpt-4o",
            messages=messages_isg,
            tools=tools,
            tool_choice="auto",
            temperature=0.2
        )

        isg_message = response_isg_initial.choices[0].message

        # Araç Çağrısı Kontrolü ve Yürütme Döngüsü
        if isg_message.tool_calls:
            messages_isg.append(isg_message)
            for tool_call in isg_message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                
                if func_name == "canli_web_ara":
                    sonuc = self.canli_web_ara(func_args.get("sorgu"))
                elif func_name == "hava_durumu_getir":
                    sonuc = self.hava_durumu_getir(func_args.get("lokasyon"))
                elif func_name == "l_tipi_matris":
                    sonuc = json.dumps(ISGRiskEngine.l_tipi_matris(func_args.get("ihtimal"), func_args.get("siddet")), ensure_ascii=False)
                elif func_name == "fine_kinney":
                    sonuc = json.dumps(ISGRiskEngine.fine_kinney(func_args.get("ihtimal"), func_args.get("frekans"), func_args.get("derece")), ensure_ascii=False)
                elif func_name == "gurultu_logaritmik_toplam":
                    sonuc = json.dumps(ISGRiskEngine.gurultu_logaritmik_toplam(func_args.get("db_degerleri")), ensure_ascii=False)
                else:
                    sonuc = "Fonksiyon bulunamadı veya geçersiz parametre."
                
                messages_isg.append({
                    "role": "tool", 
                    "tool_call_id": tool_call.id, 
                    "name": func_name, 
                    "content": str(sonuc)
                })
            
            # Araç sonuçlarıyla birlikte nihai İSG Raporunu oluştur
            res_isg = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages_isg,
                temperature=0.2
            ).choices[0].message.content
        else:
            res_isg = isg_message.content

        # --- TUR 2: ÜRETİM AJANI (Münazara ve İtiraz) ---
        prompt_uretim = f"""
        Sen hırslı bir Kıdemli Maden İşletme Müdürüsün. Sektör: {domain}.
        Amacın üretimin durmasını engellemek, hedefleri tutturmak ve gereksiz duruş maliyetlerini önlemektir.
        İSG Uzmanı az önce aşağıdaki raporu sundu. 
        Argümanlarını oku ve işi TAMAMEN DURDURMAK YERİNE (bypass, alanı daraltma, yedek ekipman) üretimi nasıl güvenli sürdürebileceğinizi savun.
        
        İSG UZMANI RAPORU:
        {res_isg}
        """

        res_uretim = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Üretim Müdürü Ajanı"},
                {"role": "user", "content": prompt_uretim}
            ],
            temperature=0.3
        ).choices[0].message.content

        # --- TUR 3: BAŞMÜHENDİS (Karar Makamı) ---
        prompt_basmuhendis = f"""
        Sen maden sahasının tek yetkilisi olan Başmühendissin (Karar Makamı). Sektör: {domain}.
        İSG Uzmanı mevzuat ve riskleri sundu, Üretim Müdürü ise operasyonu sürdürme planını anlattı.
        
        SAHADAKİ HAM BİLDİRİM: 
        "{vardiya_raporu}"
        
        İSG DENETÇİSİ GÖRÜŞÜ:
        {res_isg}
        
        ÜRETİM MÜDÜRÜ İTİRAZI:
        {res_uretim}
        
        GÖREVLERİN:
        Verilen bilgileri sentezleyerek tartışmaya kapalı nihai kararını ver. 
        Gerekliyse zorunlu ekipmanlar ({', '.join(domain_context['loto_ekipmanlari'])}) için LOTO talimatı oluştur.
        
        Çıktını EKSİKSİZ OLARAK ŞU BAŞLIKLARLA hazırla:
        
        ### ⚖️ Operasyonel Değerlendirme (İSG vs. Üretim)
        ### 🧮 Matematiksel Risk Skoru (Fine-Kinney & 5x5 Matris)
        - **Fine-Kinney Değeri:** [İhtimal (İ) x Frekans (F) x Derece (D) = Risk Skoru | Kategori (Örn: Kabul Edilebilir / Önemli / Yüksek Risk)]
        - **5x5 L-Tipi Matris:** [Olasılık x Şiddet = Skor | Renk / Seviye]
        ### 🛡️ Başmühendis Nihai Kararı ([ÜRETİM ACİL DURDURULMALI] / [ŞARTLI DEVAM] / [GÜVENLİ])
        ### 📋 Acil Aksiyon Planı ve LOTO Talimatları
        """

    # ==========================================
    # 3. YARDIMCI / ASİSTAN FONKSİYONLARI
    # ==========================================
    def _llm_ozetle(self, ham_metin: str, veri_tipi: str, sorgu: str = "", mod: str = "analiz") -> str:
        if not self.client.api_key: return "⚠️ API Anahtarı Eksik."
        
        prompt = f"""
        KULLANICI SORUSU: "{sorgu}"
        VERİTABANI KESİTLERİ:\n---\n{ham_metin}\n---
        GÖREVİN: Sağlanan veritabanı kesitlerini öncelikli baz alarak soruyu net bir şekilde yanıtla.
        """
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"⚠️ LLM Hatası ({e})."

    def mevzuat_ara_ozetli(self, sorgu: str, k: int = 8) -> str:
        return self._llm_ozetle(self.mevzuat_ara(sorgu, k=k), "maden mevzuatı", sorgu=sorgu)
        
    def soru_cevapla(self, user_q: str) -> str:
        try:
            return self.mevzuat_ara_ozetli(sorgu=user_q, k=6)
        except Exception as e:
            logger.error(f"Soru yanıtlama hatası: {e}")
            return f"Hata oluştu: {e}"