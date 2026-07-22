"""
Arın AI - Multi-Agent / CrewAI Ajan ve Araç Yapılandırması
Aethel Technologies - 2026
"""

import os
from dotenv import load_dotenv
from crewai import Agent, LLM
from crewai.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
from backend.rag_engine import RagEngine

load_dotenv()

# ==========================================
# 1. PERFORMANS VE STATİK NESNE BAŞLATMA
# ==========================================
# Motorlar dosya yüklendiğinde bir kez başlatılır.
# Her tool çağrısında tekrar veritabanı bağlantısı kurulması engellenmiştir.
rag_engine = RagEngine()
duckduckgo_tool = DuckDuckGoSearchRun()


# ==========================================
# 2. CREWAI TOOL (ARAÇ) TANIMLAMALARI
# ==========================================

@tool("Mevzuat Arama Aracı")
def mevzuat_ara_tool(sorgu: str) -> str:
    """Maden İş Sağlığı ve Güvenliği yönetmeliklerinde, 6331 sayılı kanunda ve yasal limitlerde arama yapar. 
    Havalandırma, metan, tahkimat, gaz ölçümü gibi teknik konular için doğrudan ilgili yönetmelik maddelerini getirir."""
    return rag_engine.mevzuat_ara(sorgu, k=8)

@tool("Canlı İnternet Mevzuat Taraması")
def canli_web_ara_tool(sorgu: str) -> str:
    """Mevzuat veritabanında bulunamayan veya en güncel Resmî Gazete / Mevzuat kararları için canlı web araması yapar."""
    search_query = f"site:mevzuat.gov.tr OR site:resmigazete.gov.tr maden ISG {sorgu}"
    try:
        sonuc = duckduckgo_tool.run(search_query)
        return f"--- CANLI WEB TARAMA SONUÇLARI ---\n{sonuc}" if sonuc else "Canlı aramada ilgili mevzuat maddesi bulunamadı."
    except Exception as e:
        return f"Canlı arama sırasında bir hata oluştu: {e}"

@tool("Tarihsel Kaza Analiz Aracı")
def kaza_ara_tool(sorgu: str) -> str:
    """Geçmiş maden kazalarının bilirkişi raporlarında, kök neden analizlerinde ve kaza geçmişlerinde arama yapar."""
    return rag_engine.kaza_raporu_ara(sorgu, k=6)

@tool("MTA ve Jeoloji Risk Taraması")
def jeoloji_ara_tool(sorgu: str) -> str:
    """MTA ve Jeoloji veritabanında formasyon yapısı, fay hatları, grizu patlama riski ve tavan kayacı dayanımını arar."""
    return rag_engine.jeoloji_ara(sorgu, k=6)


# ==========================================
# 3. AJAN (AGENT) SINIFI
# ==========================================

class MiningSefAgents:
    def __init__(self):
        self.llm = LLM(model="openai/gpt-4o-mini", temperature=0.2)

    def isg_mevzuat_uzmani_ajan(self) -> Agent:
        return Agent(
            role="Kıdemli Maden İSG ve Mevzuat Uzmanı",
            goal="Maden sahasından gelen verileri yasal mevzuata, yönetmeliklere ve 6331 sayılı kanuna göre denetleyip ihlalleri ilgili maddeleriyle birlikte tespit etmek. Yerel veritabanında bulamadığı durumlarda canlı internet aramasına başvurmak.",
            backstory=(
                "Yıllarca Maden İşleri Genel Müdürlüğü ve Çalışma Bakanlığı bünyesinde baş müfettişlik "
                "yapmış, Maden İşyerlerinde İSG Yönetmeliği'ni ezbere bilen bir teknik uzmansınız. "
                "Öncelikle yerel mevzuat veritabanını tararsınız. Aradığınız madde yerelde yoksa "
                "'Canlı İnternet Mevzuat Taraması' aracını kullanarak doğrudan mevzuat.gov.tr üzerinden güncel maddeleri çekersiniz."
            ),
            tools=[mevzuat_ara_tool, canli_web_ara_tool],  # <-- CANLI ARAMA TOOL'U EKLENDİ
            llm=self.llm,
            verbose=True
        )

    def kaza_tahmin_ve_risk_ajani(self) -> Agent:
        return Agent(
            role="Maden Kök Neden ve 5x5 Risk Matrisi Analisti",
            goal="Sahadaki riskleri geçmiş maden facialarıyla kıyaslamak, 5x5 Risk Matrisi metodolojisi ile nicel olarak puanlamak.",
            backstory=(
                "Büyük maden facialarının ardından kurulan bağımsız araştırma komisyonlarında görev almış "
                "bir veri bilimci ve maden mühendisisiniz. Sahadaki her tehlikeye Olasılık ve Şiddet "
                "değerleri vererek nicel bir risk değerlendirmesi yaparsınız."
            ),
            tools=[kaza_ara_tool, jeoloji_ara_tool],  # <-- JEOLOJİ TOOL'U DA EKLENEREK DESTEKLENDİ
            llm=self.llm,
            verbose=True
        )

    def bas_muhendis_raportor_ajan(self) -> Agent:
        return Agent(
            role="Maden Sahası Baş Mühendisi ve Proaktif Karar Destek Lideri",
            goal="Mevzuat uzmanı ve risk analistinden gelen verileri sentezleyerek; risk skorlarına göre önceliklendirilmiş, Düzeltici Önleyici Faaliyet (DÖF) içeren kararlı bir aksiyon raporu sunmak.",
            backstory=(
                "Maden sahalarında 20 yıldan fazla işletme müdürlüğü yapmış tecrübeli bir lider ve maden mühendisisiniz. "
                "Karmaşık teknik raporları, vardiya amirlerinin sahada anında uygulayabileceği net önlemlere dönüştürürsünüz. "
                "İhtiyaç duymanız halinde tüm veri araçlarına doğrudan erişim yetkiniz vardır."
            ),
            tools=[mevzuat_ara_tool, kaza_ara_tool, jeoloji_ara_tool], # <-- BAŞ MÜHENDİSE TAM ERİŞİM VERİLDİ
            llm=self.llm,
            verbose=True
        )