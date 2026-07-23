import os
import time
import io
import base64
import json
import re
from datetime import datetime
import random
import sqlite3

# ==========================================
# CHROMA VE RUST KİLİTLENMELERİNİ ENGELLEYEN AYARLAR
# ==========================================
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_SERVER_NOFILE"] = "1"

import pandas as pd
import numpy as np

# NumPy 2.0+ uyumluluk yaması (ChromaDB için)
if not hasattr(np, "uint"):
    np.uint = np.uint64
if not hasattr(np, "int_"):
    np.int_ = np.int64
if not hasattr(np, "float_"):
    np.float_ = np.float64
import streamlit as st

# Modeller ve İSG Motorları Güvenli İçe Aktarma
try:
    from backend.models import ISGChunkMetadata
except ImportError:
    try:
        from models import ISGChunkMetadata
    except ImportError:
        ISGChunkMetadata = None

from isg_engine import ISGRiskEngine
from backend.rag_engine import RagEngine
from backend.crew_manager import CrewManager
from pypdf import PdfReader
from docx import Document

# Sayfa Genişlik Ayarı (Scriptin en başında kalmalıdır)
st.set_page_config(layout="wide", page_title="Arın AI - Maden İSG & Karar Destek", page_icon="🛡️")

# --- SQLITE PERSONEL VERİTABANI BAŞLATMA ---
def init_db():
    os.makedirs("database", exist_ok=True)
    conn = sqlite3.connect("database/arin_ai_enterprise.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS personel_matrisi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_soyad TEXT NOT NULL,
            sicil_no TEXT UNIQUE NOT NULL,
            gorev TEXT NOT NULL,
            saglik_raporu_tarihi TEXT,
            myk_belge_durumu TEXT,
            vardiya TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- BULUT İLK KURULUM: VERİTABANI KONTROLÜ ---
def check_db_validity(path):
    """Gerçek bir Chroma veritabanı dosyasının varlığını kontrol eder."""
    db_file = os.path.join(path, "chroma.sqlite3")
    return os.path.exists(db_file)

db_mevzuat_ok = check_db_validity("database/mevzuat")
db_kazalar_ok = check_db_validity("database/kazalar")
db_jeoloji_ok = check_db_validity("database/jeoloji")

if not (db_mevzuat_ok and db_kazalar_ok and db_jeoloji_ok):
    st.warning("⚠️ **Sistem Uyarı: Vektör Veritabanları Hazırlanıyor...**")
    try:
        from backend.ingestion import veritabani_besle
        veritabani_besle()
        st.success("✅ Veritabanları başarıyla oluşturuldu!")
        st.rerun()
    except Exception as e:
        st.error(f"Veritabanı oluşturma hatası: {e}")
        st.stop()

# --- GLOBAL DURUM YÖNETİMİ (SESSION STATE) ---
if "analiz_basladi" not in st.session_state:
    st.session_state.analiz_basladi = False

if "canli_gorevler" not in st.session_state:
    st.session_state.canli_gorevler = [
        {
            "Gorev ID": "TASK-2026-001",
            "Kaynak Belge": "Sistem Açılış Testi",
            "Sorumlu Birim": "İSG Şefliği",
            "Aksiyon / İş Emri": "Arın AI Enterprise karar destek sistemi maden genelinde devreye alındı.",
            "Termin": "Tamamlandı",
            "Durum": "🟢 Aktif / Takipte"
        }
    ]

if "quick_question" not in st.session_state:
    st.session_state.quick_question = ""

# --- YARDIMCI FONKSİYONLAR ---
def personel_ekle(ad_soyad, sicil_no, gorev, saglik_tarihi, myk_durumu, vardiya):
    conn = sqlite3.connect("database/arin_ai_enterprise.db")
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO personel_matrisi (ad_soyad, sicil_no, gorev, saglik_raporu_tarihi, myk_belge_durumu, vardiya)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (ad_soyad, sicil_no, gorev, saglik_tarihi, myk_durumu, vardiya))
        conn.commit()
        return True
    except Exception as e:
        return False
    finally:
        conn.close()

def personel_listesi_getir():
    conn = sqlite3.connect("database/arin_ai_enterprise.db")
    df = pd.read_sql_query("SELECT * FROM personel_matrisi", conn)
    conn.close()
    return df

def ses_kaydini_metne_cevir(audio_file):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        transcript = client.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_file,
            language="tr" 
        )
        return transcript.text
    except Exception as e:
        return f"Ses işleme hatası: {e}"
    
def predictive_bakim_ve_loto_uret(ekipman_notu):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = f"""
    Sen kıdemli bir Maden Bakım Şefi ve İSG Uzmanısın. Aşağıdaki ekipman arıza veya bakım notunu incele:
    "{ekipman_notu}"
    
    Şu başlıklar altında kurumsal bir 'Predictive Maintenance ve LOTO İş Emri' raporu hazırla:
    1. Riskli Ekipman ve Arıza Tanımı
    2. Gerekli Adımsal LOTO (Kilitleme/Etiketleme) Prosedürü
    3. Kullanılacak Yedek Parça / Bakım İhtiyacı
    4. Sorumlu Birim (Örn: Elektrik Bakım Şefliği / Mekanik Bakım Atölyesi)
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Bakım iş emri oluşturulurken hata: {e}"

# --- OFFLINE KONTROL VE KUYRUK YÖNETİMİ ---
OFFLINE_QUEUE_FILE = "database/offline_queue.json"

def get_offline_queue():
    if os.path.exists(OFFLINE_QUEUE_FILE):
        try:
            with open(OFFLINE_QUEUE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_to_offline_queue(item):
    queue = get_offline_queue()
    queue.append(item)
    os.makedirs(os.path.dirname(OFFLINE_QUEUE_FILE), exist_ok=True)
    with open(OFFLINE_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)

def clear_offline_queue():
    if os.path.exists(OFFLINE_QUEUE_FILE):
        os.remove(OFFLINE_QUEUE_FILE)

def get_image_base64(path):
    if os.path.exists(path):
        with open(path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    return ""

def create_pdf_from_markdown(markdown_text):
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    
    try:
        pdfmetrics.registerFont(TTFont('Roboto', 'Roboto-Regular.ttf'))
        pdfmetrics.registerFont(TTFont('Roboto-Bold', 'Roboto-Bold.ttf'))
        font_regular = 'Roboto'
        font_bold = 'Roboto-Bold'
    except Exception:
        font_regular = 'Helvetica'
        font_bold = 'Helvetica-Bold'

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('PDFTitle', parent=styles['Heading1'], fontName=font_bold, fontSize=18, leading=22, textColor='#F97316', spaceAfter=15)
    h2_style = ParagraphStyle('PDFH2', parent=styles['Heading2'], fontName=font_bold, fontSize=13, leading=16, textColor='#1E3A8A', spaceBefore=12, spaceAfter=6)
    body_style = ParagraphStyle('PDFBody', parent=styles['BodyText'], fontName=font_regular, fontSize=10, leading=14, textColor='#1E293B', spaceAfter=6)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []

    for line in str(markdown_text).split('\n'):
        cleaned_line = line.strip()
        if not cleaned_line:
            continue
        if cleaned_line.startswith('# '):
            story.append(Paragraph(cleaned_line[2:], title_style))
        elif cleaned_line.startswith('## ') or cleaned_line.startswith('### '):
            story.append(Paragraph(cleaned_line.lstrip('# '), h2_style))
        else:
            text = cleaned_line.replace('<br>', ' ').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            while '**' in text:
                text = text.replace('**', '<b>', 1).replace('**', '</b>', 1)
            if '|' in text:
                text = text.replace('|', '   ').strip()
                if '---' in text:
                    continue
            if text.strip():
                story.append(Paragraph(text, body_style))
                story.append(Spacer(1, 3))

    doc.build(story)
    return buffer.getvalue()

def form_doldur_llm(vardiya_notu, form_tipi):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    bugun = datetime.now().strftime("%d %m %Y") 
    
    prompt = f"""
    Sen kıdemli bir Maden İSG Baş Mühendisisin. Aşağıdaki vardiya notunu incele ve resmi bir '{form_tipi}' oluştur.
    Form No / Tarih (Bugünün tarihini kullan: {bugun}), Tespit Edilen Risk, Yönetmelik Atfı, Proaktif Aksiyonlar ve Sorumlu Birim alanlarını eksiksiz doldur.
    
    Vardiya Notu/Verisi:
    {vardiya_notu}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Form oluşturulurken hata: {e}"

def gorev_sevk_et(girdi_metni, kaynak_belge):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = f"""
    Aşağıdaki İSG analiz veya form metninden 'Sorumlu Birim', 'Alınması Gereken Proaktif Aksiyon / İş Emri' ve 'Termin Süresi' bilgilerini ayıkla.
    Eğer birden fazla aksiyon varsa en kritik olanı özetle.
    Çıktıyı SADECE şu formatta tek satır ver: Sorumlu Birim | Aksiyon Kısa Özeti | Termin Süresi

    Metin:
    {girdi_metni}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        veri = response.choices[0].message.content.split("|")
        sorumlu = veri[0].strip() if len(veri) > 0 else "Belirlenemedi"
        aksiyon = veri[1].strip() if len(veri) > 1 else "Aksiyon emri çıkarılamadı"
        termin = veri[2].strip() if len(veri) > 2 else "Derhal"
        
        yeni_id = f"TASK-{datetime.now().year}-{len(st.session_state.canli_gorevler) + 1:03d}"
        st.session_state.canli_gorevler.append({
            "Gorev ID": yeni_id,
            "Kaynak Belge": kaynak_belge,
            "Sorumlu Birim": sorumlu,
            "Aksiyon / İş Emri": aksiyon,
            "Termin": termin,
            "Durum": "🔴 Sahaya Gönderildi / Yanıt Bekleniyor"
        })
        return True
    except:
        return False

# --- GÖRSEL İSG ANALİZ MOTORU ---
def analiz_et_gorsel(file_bytes):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    base64_image = base64.b64encode(file_bytes).decode('utf-8')
    
    prompt = "Sen bir İSG denetçisisin. Bu maden sahası/ekipman fotoğrafını incele. Olası İSG ihlallerini (baret/maske eksikliği, hatalı tahkimat, açık kablo vb.) tespit et ve ilgili maden mevzuatı maddeleriyle eşleştir. Sadece bulguları ve önerileri yaz."
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Görsel analiz hatası: {e}"

def extract_text_from_pdf(file_bytes):
    reader = PdfReader(io.BytesIO(file_bytes))
    return "\n".join([page.extract_text() for page in reader.pages if page.extract_text()]).strip()

def extract_text_from_docx(file_bytes):
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join([p.text for p in doc.paragraphs if p.text.strip()]).strip()

def extract_text_from_excel(file_bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    out = ""
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet).dropna(how='all')
        if not df.empty: out += df.to_string(index=False) + "\n"
    return out.strip()

def extract_text_from_audio(file_bytes, file_name):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    temp_filename = f"temp_{file_name}"
    with open(temp_filename, "wb") as f: f.write(file_bytes)
    try:
        with open(temp_filename, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(model="whisper-1", file=audio_file, language="tr")
        return transcript.text
    finally:
        if os.path.exists(temp_filename): os.remove(temp_filename)

@st.cache_resource
def get_backend_services():
    return RagEngine(), CrewManager()

try:
    rag_engine, crew_manager = get_backend_services()
except Exception as e:
    rag_engine, crew_manager = None, None

# --- SİNEMATİK GİRİŞ ANİMASYONU ---
if 'splash_completed' not in st.session_state:
    st.session_state.splash_completed = False

if not st.session_state.splash_completed:
    splash_placeholder = st.empty()
    aethel_base64 = get_image_base64("aethel_logo.png")
    with splash_placeholder.container():
        if aethel_base64:
            st.markdown(f"""
                <style>
                @keyframes cinematicFade {{
                    0% {{ opacity: 0; transform: scale(0.92); }}
                    50% {{ opacity: 1; transform: scale(1); }}
                    100% {{ opacity: 0; }}
                }}
                .splash-bg {{
                    position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                    background-color: #0F172A; display: flex; justify-content: center;
                    align-items: center; z-index: 9999999;
                }}
                .splash-logo {{ max-width: 450px; animation: cinematicFade 2.0s forwards; }}
                </style>
                <div class="splash-bg"><img class="splash-logo" src="data:image/png;base64,{aethel_base64}"></div>
            """, unsafe_allow_html=True)
            time.sleep(2.0)
    st.session_state.splash_completed = True
    splash_placeholder.empty()
    st.rerun()

# --- SIDEBAR ---
with st.sidebar:
    if os.path.exists("arin_logo.png"):
        st.image("arin_logo.png", use_container_width=True)
    else:
        st.title("🛡️ Arın AI Enterprise")
        
    st.markdown("---")
    if "analiz_verisi" not in st.session_state: st.session_state.analiz_verisi = ""
    if "son_yuklenen_dosya" not in st.session_state: st.session_state.son_yuklenen_dosya = None

    # --- OFFLINE MOD ANAHTARI ---
    st.sidebar.markdown("### 📡 Saha Bağlantı Modu")
    is_offline = st.sidebar.toggle("🚫 Yeraltı Çevrimdışı (Offline) Mod", value=False)
    
    if is_offline:
        st.sidebar.warning("⚡ Yeraltındasınız: Veriler yerel hafızaya kaydedilecek, internete bağlanınca analiz edilecek.")
        offline_note = st.sidebar.text_area("✍️ Offline Vardiya Notu / Taslak:", key="off_note")
        if st.sidebar.button("💾 Taslağı Yeraltı Hafızasına Kaydet"):
            if offline_note.strip():
                save_to_offline_queue({
                    "tarih": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "not": offline_note.strip()
                })
                st.sidebar.success("✅ Taslak yerel belleğe kaydedildi!")
            else:
                st.sidebar.error("Metin boş olamaz.")
    
    # KUYRUKTA BEKLEYEN TASLAKLARI SENKRONİZE ETME
    current_queue = get_offline_queue()
    if current_queue:
        st.sidebar.info(f"📥 Senkronize Edilmeyi Bekleyen: **{len(current_queue)} adet taslak** var.")
        if st.sidebar.button("🔄 Yerüstüne Çıkıldı: Taslakları Senkronize Et & Analiz Et", type="primary"):
            birlestirilmis_notlar = "\n\n--- OFFLINE TOPLANAN VARDİYA KAYITLARI ---\n"
            for idx, q in enumerate(current_queue, 1):
                birlestirilmis_notlar += f"\n[{q['tarih']}] Kayıt #{idx}:\n{q['not']}\n"
            
            st.session_state.analiz_verisi = birlestirilmis_notlar
            clear_offline_queue()
            st.sidebar.success("✅ Tüm offline veriler ana sisteme aktarıldı ve temizlendi!")
            st.rerun()

    st.markdown("---")

    # GÜNCELLENMİŞ UPLOADER
    st.sidebar.markdown("### 🎙️ Telsiz Ses Kaydı veya Belge/Fotoğraf Yükle")
    uploaded_file = st.file_uploader("📂 Rapor, Telsiz Kaydı veya Fotoğraf Yükleyin", type=["pdf", "docx", "xlsx", "xls", "txt", "mp3", "wav", "m4a", "png", "jpg", "jpeg"])
    if uploaded_file is not None and uploaded_file.name != st.session_state.son_yuklenen_dosya:
        try:
            file_bytes = uploaded_file.read()
            if uploaded_file.name.endswith(('.mp3', '.wav', '.m4a')):
                st.audio(file_bytes, format=f"audio/{uploaded_file.name.split('.')[-1]}")
                with st.spinner("🎙️ Whisper AI: Telsiz ses kaydı metne dönüştürülüyor..."): 
                    st.session_state.analiz_verisi = extract_text_from_audio(file_bytes, uploaded_file.name)
            elif uploaded_file.name.endswith(('.png', '.jpg', '.jpeg')):
                with st.spinner("👁️ Görsel İSG Motoru analiz ediyor..."):
                    st.session_state.analiz_verisi = analiz_et_gorsel(file_bytes)
            elif uploaded_file.name.endswith('.pdf'): st.session_state.analiz_verisi = extract_text_from_pdf(file_bytes)
            elif uploaded_file.name.endswith(('.docx', '.doc')): st.session_state.analiz_verisi = extract_text_from_docx(file_bytes)
            elif uploaded_file.name.endswith(('.xlsx', '.xls')): st.session_state.analiz_verisi = extract_text_from_excel(file_bytes)
            elif uploaded_file.name.endswith('.txt'): st.session_state.analiz_verisi = file_bytes.decode("utf-8")
            
            st.session_state.son_yuklenen_dosya = uploaded_file.name
            st.session_state.analiz_sonucu = None
            st.success("✅ Veri çözümlendi ve aktarıldı!")
            time.sleep(0.5)
            st.rerun()
        except Exception as e: st.error(f"Hata: {e}")

    if not st.session_state.analiz_verisi:
        st.session_state.analiz_verisi = (
            f"Vardiya: Gece (00:00 - 08:00) - Zonguldak Havzası 3. Ayna\nTarih: {datetime.now().strftime('%d %m %Y')}\nLokasyon: 3. Batı Galerisi (Kot: -120)\n\n"
            "Yapılan İşler ve Gözlemler:\nAyna ilerlemesi yapıldı. Arın bölgesinde tavan kayacında killi şist yapısı sebebiyle çatlaklar ve kılcal dökülmeler var. "
            "Ahşap tahkimat kamalarında esneme tespit edildi ancak üretime devam edildi. Fan 18 dk durdu, CH4 %1.4 seviyesine çıktı."
        )

    manuel_metin = st.text_area("✍️ Vardiya Defteri / Bulgular:", value=st.session_state.analiz_verisi, height=180)
    st.session_state.analiz_verisi = manuel_metin

    if st.button("🚀 MULTI-AGENT ANALİZİ BAŞLAT", type="primary", use_container_width=True):
        st.session_state.analiz_basladi = True
        st.session_state.analiz_sonucu = None
        st.session_state.mevzuat_kaynaklari = ""
        st.session_state.kaza_kaynaklari = ""
        st.session_state.jeoloji_kaynaklari = ""
        st.rerun()

# --- ANA SÜRÜM ÜST PANEL ---
st.title("🛡️ Arın AI Enterprise: Proaktif Maden İSG & Saha Yönetim Platformu")
st.caption("Aethel Technologies — Multi-Agent RAG, Jeoloji & Operasyonel Karar Destek Mimarisi")

# 6 SEKMELİ YENİ MİMARİ
tab_dashboard, tab_engine, tab_forms, tab_operations, tab_scada, tab_personel = st.tabs([
    "📊 Canlı İSG Analiz Paneli", 
    "🧮 Deterministik Risk & Ölçüm Motoru",
    "📋 Form & Kök Neden Merkezi", 
    "📡 Sahadan Canlı Görev Sevk Panosu",
    "🔴 SCADA & GIS (Sensör ve Harita)",
    "👷‍♂️ Personel & Vardiya Matrisi"
])

# --- TAB 1: CANLI ANALİZ PANELİ ---
with tab_dashboard:
    if "analiz_sonucu" not in st.session_state: st.session_state.analiz_sonucu = None
    if "mevzuat_kaynaklari" not in st.session_state: st.session_state.mevzuat_kaynaklari = ""
    if "kaza_kaynaklari" not in st.session_state: st.session_state.kaza_kaynaklari = ""
    if "jeoloji_kaynaklari" not in st.session_state: st.session_state.jeoloji_kaynaklari = ""

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1: st.metric(label="🚨 Risk Skoru", value="%78" if st.session_state.analiz_sonucu else "%25", delta="Kritik" if st.session_state.analiz_sonucu else "Normal")
    with kpi2: st.metric(label="⚠️ Tespit Edilen İhlal", value="3 Adet" if st.session_state.analiz_sonucu else "0 Adet")
    with kpi3: st.metric(label="📚 Taranan Veritabanları", value="Mevzuat + Kaza + MTA")
    with kpi4: st.metric(label="🕒 Veri Akışı", value="Canlı / 360° RAG + Memory")
    st.write("---")

    if st.session_state.analiz_basladi and st.session_state.analiz_sonucu is None:
        try:
            status = st.empty()
            progress = st.progress(0)
            
            status.info("📍 Saha Lokasyon Mimarisi ve Geçmiş Vardiya Hafızası çekiliyor...")
            progress.progress(20)
            
            status.info("📚 RAG: Mevzuat, Kaza ve MTA Jeoloji Veritabanı taranıyor...")
            progress.progress(50)
            if rag_engine:
                st.session_state.mevzuat_kaynaklari = rag_engine.mevzuat_ara_ozetli(st.session_state.analiz_verisi)
                st.session_state.kaza_kaynaklari = rag_engine.kaza_raporu_ara_ozetli(st.session_state.analiz_verisi)
                st.session_state.jeoloji_kaynaklari = rag_engine.jeoloji_ara_ozetli(st.session_state.analiz_verisi)
            
            status.info("⚖️ Multi-Agent Çatışma Simülasyonu (İSG Denetçisi vs Üretim Mühendisi vs Başmühendis)...")
            progress.progress(85)
            
            if rag_engine:
                res_dict = rag_engine.saha_raporu_analiz_et(st.session_state.analiz_verisi)
                st.session_state.analiz_sonucu = res_dict
            
            progress.progress(100)
            status.empty()
            progress.empty()
            st.session_state.analiz_basladi = False
            st.rerun()
        except Exception as e:
            st.error(f"Hata: {e}")
            st.session_state.analiz_basladi = False

    if st.session_state.analiz_sonucu:
        res = st.session_state.analiz_sonucu
        
        if isinstance(res, dict) and "error" in res:
            st.error(res["error"])
        elif isinstance(res, dict):
            loc_info = res.get("location", {})
            st.subheader(f"📍 Algılanan Saha Alanı: {loc_info.get('title', 'Belirtilmedi')}")
            
            c_loc1, c_loc2 = st.columns(2)
            with c_loc1:
                st.warning(f"**Öncelikli Saha Riskleri:** {', '.join(loc_info.get('primary_risks', []))}")
            with c_loc2:
                st.info(f"**Zorunlu Kritik Kontroller:** {', '.join(loc_info.get('critical_checks', []))}")
            
            equipment_info = res.get("equipment", {})
            if equipment_info:
                st.markdown("<br>", unsafe_allow_html=True)
                st.subheader("🚜 Tespit Edilen Kritik Ekipman & LOTO Durumu")
                for eq_key, eq_data in equipment_info.items():
                    with st.container():
                        c_eq1, c_eq2 = st.columns([1, 2])
                        with c_eq1:
                            st.error(f"**Ekipman:** {eq_data['name']}")
                            st.write(f"**Spesifik Riskler:** {', '.join(eq_data['risks'])}")
                        with c_eq2:
                            st.success(f"**🔒 Zorunlu LOTO Prosedürü:** {eq_data['loto_protocol']}")
            st.write("---")

            st.subheader("📈 Saha Vardiyalar Arası Gaz Trend Grafiği (Memory)")
            try:
                if os.path.exists("database/shift_memory.json"):
                    with open("database/shift_memory.json", "r", encoding="utf-8") as f:
                        mem_data = json.load(f)
                    records = mem_data.get("shift_records", [])
                    ch4_vals = [r["ch4_level"] for r in records if r.get("ch4_level") is not None]
                    
                    if len(ch4_vals) > 0:
                        chart_df = pd.DataFrame({"Vardiya Kayıtları": range(1, len(ch4_vals) + 1), "Metan (CH4 %)": ch4_vals})
                        st.line_chart(chart_df.set_index("Vardiya Kayıtları"))
                    else:
                        st.caption("Grafik için henüz yeterli sayısal CH4 verisi birikmedi.")
            except Exception as e:
                st.caption(f"Trend grafiği yüklenemedi: {e}")

            st.write("---")

            col_out, col_ref = st.columns([2, 1])
            with col_out:
                st.subheader("🤖 Başmühendis Final Kararı ve DÖF Planı")
                st.info(res.get("final_decision", ""))
                
                c_btn1, c_btn2 = st.columns(2)
                with c_btn1:
                    pdf_data = create_pdf_from_markdown(res.get("final_decision", ""))
                    st.download_button("📥 Karar Raporunu PDF İndir", data=pdf_data, file_name="ArinAI_Basmuhendis_Karari.pdf", mime="application/pdf", use_container_width=True)
                with c_btn2:
                    if st.button("📡 DÖF PLANINI ONAYLA VE SAHAYA SEVK ET", type="primary", use_container_width=True):
                        with st.spinner("İş emirleri sahaya sevk ediliyor..."):
                            if gorev_sevk_et(res.get("final_decision", ""), "Başmühendis Karar Raporu"):
                                st.success("✅ DÖF Planı onaylandı ve Canlı Görev Takip Panosuna sevk edildi!")
                                time.sleep(1)
                                st.rerun()

                with st.expander("⏳ Lokasyon Geçmiş Vardiya Akışı (Saha Hafızası)", expanded=False):
                    raw_history = res.get("history", "")
                    if raw_history and raw_history != "Geçmiş kayıt bulunamadı.":
                        lines = [line.strip() for line in raw_history.split("\n") if line.strip()]
                        for line in lines:
                            if line.startswith("---") or line.startswith("==="):
                                continue
                            
                            if line.startswith("["):
                                try:
                                    parts = line.split("|")
                                    idx_date = parts[0].strip()
                                    ch4_info = parts[1].strip()
                                    summary = parts[2].replace("Özet:", "").strip() if len(parts) > 2 else ""

                                    ch4_val = float(ch4_info.split("%")[-1].strip()) if "%" in ch4_info else 0.0
                                    
                                    if ch4_val >= 2.0:
                                        badge = f"🔴 **{ch4_info}** (KRİTİK)"
                                    elif ch4_val >= 1.0:
                                        badge = f"🟠 **{ch4_info}** (UYARI)"
                                    else:
                                        badge = f"🟢 **{ch4_info}** (NORMAL)"

                                    with st.container():
                                        st.markdown(f"**{idx_date}** &nbsp;|&nbsp; Gaz Seviyesi: {badge}", unsafe_allow_html=True)
                                        st.caption(f"📝 {summary}")
                                        st.divider()
                                except Exception:
                                    st.write(line)
                            else:
                                st.write(line)
                    else:
                        st.info("Bu lokasyon için henüz geçmiş vardiya kaydı bulunmuyor.")

                with st.expander("👷 İSG Denetim Ajanı Görüşü (Tavizsiz Güvenlik)", expanded=False):
                    st.error(res.get("isg_agent", ""))
                    
                with st.expander("⛏️ Üretim Mühendisi Ajanı Görüşü (Operasyonel Devamlılık)", expanded=False):
                    st.warning(res.get("uretim_agent", ""))

            with col_ref:
                st.subheader("📚 360° RAG Kanıtları")
                with st.expander("⚖️ Eşleşen Kanun Maddeleri", expanded=True): st.success(st.session_state.mevzuat_kaynaklari)
                with st.expander("🌋 MTA & Jeoloji Formasyon Bilgisi", expanded=True): st.info(st.session_state.jeoloji_kaynaklari)
                with st.expander("💥 Tarihsel Benzer Kazalar", expanded=True): st.warning(st.session_state.kaza_kaynaklari)
        else:
            st.info(str(res))

    st.markdown("---")
    st.subheader("🔍 İnteraktif Maden & Jeoloji Asistanı")
    kullanici_sorusu = st.text_input("💬 Sorunuzu Giriniz (Mevzuat, Kaza veya Saha/Jeoloji Sorgusu):", value=st.session_state.quick_question)
    
    if st.button("🔍 Veritabanlarında Ara") and kullanici_sorusu:
        if rag_engine:
            with st.spinner("Mevzuat, Kaza ve MTA Jeoloji veritabanları taranıyor..."):
                mevzuat_sonuc = rag_engine.mevzuat_ara_ozetli(kullanici_sorusu)
                kaza_sonuc = rag_engine.kaza_raporu_ara_ozetli(kullanici_sorusu)
                jeoloji_sonuc = rag_engine.jeoloji_ara_ozetli(kullanici_sorusu)
                
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown("### 📜 Mevzuat Yanıtı")
                    st.info(mevzuat_sonuc)
                with c2:
                    st.markdown("### 🌋 MTA & Jeoloji")
                    st.info(jeoloji_sonuc)
                with c3:
                    st.markdown("### 💥 Tarihsel Kazalar")
                    st.warning(kaza_sonuc)

# --- TAB 2: DETERMINISTIK HESAPLAMA MOTORLARI ---
with tab_engine:
    st.header("🧮 Deterministik İSG Risk & Ölçüm Hesaplayıcıları")
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("1. L Tipi (5x5) Risk Matrisi")
        ihtimal_l = st.slider("İhtimal (Olasılık)", 1, 5, 3, key="l_ihtimal")
        siddet_l = st.slider("Şiddet / Sonuç", 1, 5, 3, key="l_siddet")
        if st.button("L Tipi Skor Hesapla", type="primary"):
            res = ISGRiskEngine.l_tipi_matris(ihtimal_l, siddet_l)
            st.metric("Risk Skoru", res["risk_skoru"])
            st.info(f"**Kategori:** {res['kategori']}")
            st.warning(f"**Eylem:** {res['onerilen_eylem']}")

    with c2:
        st.subheader("2. Fine-Kinney Analizi")
        fk_ihtimal = st.number_input("İhtimal (0.1 - 10)", 0.1, 10.0, 3.0, 0.5)
        fk_frekans = st.number_input("Frekans (0.5 - 10)", 0.5, 10.0, 6.0, 0.5)
        fk_derece = st.number_input("Derece / Şiddet (1 - 100)", 1.0, 100.0, 7.0, 1.0)
        if st.button("Fine-Kinney Skor Hesapla", type="primary"):
            res_fk = ISGRiskEngine.fine_kinney(fk_ihtimal, fk_frekans, fk_derece)
            st.metric("Fine-Kinney Risk Değeri", res_fk["risk_degeri"])
            st.info(f"**Kategori:** {res_fk['kategori']} ({res_fk['durum_kodu']})")
            st.warning(f"**Eylem:** {res_fk['onerilen_eylem']}")

    st.markdown("---")
    st.subheader("3. Logaritmik Gürültü Toplama Engine")
    gurultu_input = st.text_input("Gürültü Değerleri (dB) - Virgülle ayırın:", value="85, 90")
    if st.button("Gürültü Toplamını Hesapla"):
        try:
            db_list = [float(x.strip()) for x in gurultu_input.split(",") if x.strip()]
            res_db = ISGRiskEngine.gurultu_logaritmik_toplam(db_list)
            st.metric("Bileşke Gürültü Seviyesi", f"{res_db['toplam_gurultu_db']} dB(A)")
            if "KRİTİK" in res_db["mevzuat_durumu"]: st.error(res_db["mevzuat_durumu"])
            else: st.warning(res_db["mevzuat_durumu"])
        except ValueError:
            st.error("Lütfen geçerli sayısal değerler girin.")

    st.markdown("---")
    st.subheader("4. Jeoteknik RMR (Rock Mass Rating) Hesaplayıcı")
    st.caption("Bieniawski (1989) parametrelerine göre yeraltı tahkimat önerisi.")
    
    r_col1, r_col2, r_col3 = st.columns(3)
    with r_col1:
        ucs = st.selectbox("Tek Eksenli Basınç Dayanımı", ["Çok Düşük (<5 MPa) [1p]", "Düşük (5-25 MPa) [2p]", "Orta (25-50 MPa) [4p]", "Yüksek (50-100 MPa) [7p]", "Çok Yüksek (>100 MPa) [12p]"])
        rqd = st.slider("RQD (Kaya Kalite Göstergesi) %", 0, 100, 75)
    with r_col2:
        spacing = st.selectbox("Eklem Aralığı", ["< 60 mm [5p]", "60 - 200 mm [8p]", "200 - 600 mm [10p]", "0.6 - 2.0 m [15p]", "> 2.0 m [20p]"])
        condition = st.selectbox("Eklem Durumu", ["Çok Zayıf (Yumuşak dolgulu) [0p]", "Zayıf (Sürekli, >5mm açık) [10p]", "Orta (Hafif pürüzlü, <1mm) [20p]", "Çok İyi (Kapalı, sert) [30p]"])
    with r_col3:
        water = st.selectbox("Yeraltı Suyu Durumu", ["Akan (Sürekli Su) [0p]", "Damlatan [4p]", "Nemli [10p]", "Tamamen Kuru [15p]"])

    if st.button("RMR Skoru ve Tahkimat Sınıfını Hesapla", type="primary"):
        def get_point(text):
            match = re.search(r'\[(\d+)p\]', text)
            return int(match.group(1)) if match else 0
        
        rqd_puan = int(rqd / 5)
        total_rmr = get_point(ucs) + rqd_puan + get_point(spacing) + get_point(condition) + get_point(water)
        
        st.metric("Toplam RMR Skoru", f"{total_rmr} / 100")
        
        if total_rmr > 80: st.success("**Sınıf I (Çok İyi Kaya):** Tahkimata gerek yoktur, lokal saplama yeterlidir.")
        elif total_rmr > 60: st.info("**Sınıf II (İyi Kaya):** Seyrek kaya saplaması (R=2.5m) ve lokal tel kafes.")
        elif total_rmr > 40: st.warning("**Sınıf III (Orta Kaya):** Sistematik kaya saplaması, 50-100mm püskürtme beton.")
        elif total_rmr > 20: st.error("**Sınıf IV (Zayıf Kaya):** Yoğun saplama, çelik hasırlı 100-150mm püskürtme beton ve çelik iksa (TH/I).")
        else: st.error("🚨 **Sınıf V (Çok Zayıf Kaya):** Derhal çelik iksa, ağır püskürtme beton ve tavan aynası sürgüsü zorunludur!")

# --- TAB 3: FORM & KÖK NEDEN MERKEZİ ---
with tab_forms:
    st.subheader("📋 Resmi İSG Form, Kök Neden & Bakım Matrisi")
    secilen_form = st.selectbox("Üretilecek Belge Tipini Seçin:", [
        "Maden İşletmeleri Ramak Kala Olay Formu", 
        "Tehlike Bildirim Formu", 
        "İş Durdurma Tutanağı",
        "Kök Neden Analizi (5 Neden - 5 Whys)",
        "Predictive Maintenance & LOTO İş Emri"
    ])
    
    if st.button(f"✨ {secilen_form} Üret"):
        with st.spinner("AI Belgeyi Hazırlıyor..."):
            if "Kök Neden" in secilen_form:
                from openai import OpenAI
                client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                prompt = f"Şu olayın/vardiya notunun '5 Neden (5 Whys)' analizini yap. En sonda Kök Nedeni (Root Cause) ve Düzeltici Önleyici Faaliyeti (DÖF) belirt.\n\nOlay: {st.session_state.analiz_verisi}"
                resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                st.session_state[f"form_cache_{secilen_form}"] = resp.choices[0].message.content
            elif "Predictive Maintenance" in secilen_form:
                st.session_state[f"form_cache_{secilen_form}"] = predictive_bakim_ve_loto_uret(st.session_state.analiz_verisi)
            else:
                st.session_state[f"form_cache_{secilen_form}"] = form_doldur_llm(st.session_state.analiz_verisi, secilen_form)
            
    cache_key = f"form_cache_{secilen_form}"
    if cache_key in st.session_state:
        st.markdown(st.session_state[cache_key])
        btn1, btn2 = st.columns(2)
        with btn1:
            st.download_button("📥 Belgeyi PDF İndir", data=create_pdf_from_markdown(st.session_state[cache_key]), file_name=f"{secilen_form.replace(' ', '_')}.pdf", mime="application/pdf", use_container_width=True)
        with btn2:
            if st.button("📡 SAHAYA SEVK ET (BAKIM İŞ EMRİ)", type="primary", use_container_width=True):
                if gorev_sevk_et(st.session_state[cache_key], secilen_form):
                    st.success("📢 Bakım iş emri Canlı Takip Panosuna sevk edildi!")

# --- TAB 4: SAHADAN CANLI GÖREV SEVK PANOSU ---
with tab_operations:
    st.subheader("🔄 Vardiya Teslim (Handover) Zekası")
    
    col_handover, col_report = st.columns([1, 1])
    
    with col_handover:
        if st.button("Geçmiş 24 Saati Özetle ve Açık Riskleri Raporla", type="secondary", use_container_width=True):
            with st.spinner("Hafızadaki vardiyalar birleştiriliyor..."):
                from openai import OpenAI
                client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                
                ornek_gecmis = "Gece vardiyası: 3. batı galerisinde su geliri arttı. Gündüz vardiyası: Aynı bölgede fan arızalandı, %1.2 CH4 ölçüldü, onarım beklemede."
                prompt = f"Aşağıdaki geçmiş 24 saatlik maden notlarını incele. Yeni gelen amir için 'DEVREDİLEN AÇIK RİSKLER' adında 3 maddelik acil bir brifing hazırla.\n\nVeri: {ornek_gecmis}"
                
                resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                st.warning("⚠️ **Yeni Vardiya Amirinin Dikkatine (Açık Riskler):**")
                st.markdown(resp.choices[0].message.content)

    with col_report:
        # FİNAL ADIMI: KAPSAMLI PDF RAPOR OLUŞTURUCU
        if st.button("📑 Kapsamlı Vardiya Kapanış Raporu Oluştur (PDF)", type="primary", use_container_width=True):
            with st.spinner("Tüm sistem verileri toplanıyor ve Kurumsal Rapor hazırlanıyor..."):
                rapor_metni = f"# ARIN AI ENTERPRISE - VARDİYA KAPANIŞ RAPORU\n\n"
                rapor_metni += f"**Tarih / Saat:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                rapor_metni += f"**Sistem Modu:** Çoklu Ajan Karar Destek Aktif\n\n"
                rapor_metni += "---\n\n"
                
                rapor_metni += "## 1. SON ANALİZ VE SAHA BULGULARI\n"
                if st.session_state.analiz_sonucu and isinstance(st.session_state.analiz_sonucu, dict):
                    loc = st.session_state.analiz_sonucu.get("location", {}).get("title", "Belirtilmedi")
                    rapor_metni += f"**İncelenen Lokasyon:** {loc}\n\n"
                    rapor_metni += f"**Başmühendis Kararı:**\n{st.session_state.analiz_sonucu.get('final_decision', 'Analiz edilmedi.')}\n\n"
                else:
                    rapor_metni += "Bu vardiyada tam kapsamlı AI risk analizi yürütülmedi.\n\n"
                
                rapor_metni += "## 2. AÇIK İŞ EMİRLERİ VE DÖF (Düzeltici Önleyici Faaliyetler)\n"
                if st.session_state.canli_gorevler:
                    for idx, task in enumerate(st.session_state.canli_gorevler, 1):
                        rapor_metni += f"**{idx}. [ID: {task['Gorev ID']}]** - {task['Aksiyon / İş Emri']}\n"
                        rapor_metni += f"Sorumlu: {task['Sorumlu Birim']} | Termin: {task['Termin']} | Durum: {task['Durum']}\n\n"
                else:
                    rapor_metni += "Bu vardiyada atanmış aktif bir görev bulunmamaktadır.\n\n"
                
                rapor_metni += "## 3. İSG PERSONEL & UYUMLULUK İHLALLERİ\n"
                try:
                    df_personel = personel_listesi_getir()
                    bugun = datetime.now().strftime("%Y-%m-%d")
                    riskli_personel = df_personel[(df_personel['myk_belge_durumu'] != "Geçerli / Aktif") | (df_personel['saglik_raporu_tarihi'] < bugun)]
                    
                    if not riskli_personel.empty:
                        for _, row in riskli_personel.iterrows():
                            rapor_metni += f"⚠️ **{row['ad_soyad']} (Sicil: {row['sicil_no']})** - {row['gorev']}\n"
                            rapor_metni += f"Durum: MYK ({row['myk_belge_durumu']}) | Sağlık Raporu ({row['saglik_raporu_tarihi']})\n\n"
                    else:
                        rapor_metni += "✅ Tüm personelin İSG belgeleri ve sağlık raporları günceldir.\n\n"
                except Exception as e:
                    rapor_metni += f"Personel verisi çekilemedi: {e}\n\n"
                
                rapor_metni += "---\n*Bu belge Aethel Technologies - Arın AI Sistemi tarafından otomatik oluşturulmuştur.*"
                
                # PDF'i oluştur ve Session State'e at
                pdf_bytes = create_pdf_from_markdown(rapor_metni)
                st.session_state.kapanis_raporu = pdf_bytes
                st.success("✅ Rapor başarıyla oluşturuldu!")

    # Rapor oluştuysa indirme butonunu göster
    if "kapanis_raporu" in st.session_state:
        st.download_button(
            label="📥 Oluşturulan Kapanış Raporunu İndir (PDF)",
            data=st.session_state.kapanis_raporu,
            file_name=f"Vardiya_Kapanis_Raporu_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True
        )

    st.write("---")
    st.subheader("📡 Canlı Operasyonel Görev Takip Panosu")
    if st.session_state.canli_gorevler:
        st.dataframe(pd.DataFrame(st.session_state.canli_gorevler), use_container_width=True, hide_index=True)

# --- TAB 5: SCADA & GIS (LIVE SENSORS & MAP) ---
with tab_scada:
    st.header("🔴 Anlık Sensör Verileri & Kestirimci Anomali Tahmini (Predictive AI)")
    st.caption("IoT Sensör Akışı, Trend Analizi ve Erken Uyarı Mimarisi")
    
    sc1, sc2, sc3, sc4 = st.columns(4)
    
    if "ch4_history" not in st.session_state:
        st.session_state.ch4_history = [0.4, 0.6, 0.8, 1.1, 1.35]
    
    ch4_val = st.session_state.ch4_history[-1]
    co_val = random.randint(10, 45)
    temp_val = round(random.uniform(25.0, 32.0), 1)
    air_val = round(random.uniform(0.5, 2.0), 2)
    
    with sc1:
        st.metric("Metan (CH4) Mevcut", f"%{ch4_val}", delta=f"+%{round(ch4_val - st.session_state.ch4_history[-2], 2)} (Yükselişte)", delta_color="inverse")
    with sc2:
        st.metric("Karbonmonoksit (CO)", f"{co_val} ppm", delta="Uyarı" if co_val > 30 else "İyi", delta_color="inverse")
    with sc3:
        st.metric("Ortam Sıcaklığı", f"{temp_val} °C", "Normal")
    with sc4:
        st.metric("Hava Hızı", f"{air_val} m/s", "-0.1 m/s (Düşüş)")

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("📈 Kestirimci Gaz Eğrisi ve Erken Uyarı (Predictive Trend Analysis)")
    
    c_chart, c_predict = st.columns([2, 1])
    
    x = np.array(range(len(st.session_state.ch4_history)))
    y = np.array(st.session_state.ch4_history)
    slope, intercept = np.polyfit(x, y, 1) 
    
    future_x = np.array([5, 6, 7])
    future_ch4 = slope * future_x + intercept
    tahmini_kritik_sure = int((1.5 - ch4_val) / (slope if slope > 0 else 0.01) * 5) 
    
    with c_chart:
        df_chart = pd.DataFrame({
            "Geçmiş Ölçümler": st.session_state.ch4_history + [None, None, None],
            "AI Tahmin Eğrisi (Gelecek)": [None]*4 + [ch4_val] + list(np.round(future_ch4, 2))
        })
        st.line_chart(df_chart)

    with c_predict:
        st.markdown("#### 🔮 AI Tahmin Raporu")
        if slope > 0.1:
            st.error(f"🚨 **ANOMALİ TESPİT EDİLDİ!**\n\nGaz seviyesinde ivmeli bir artış var (Eğim: +{round(slope, 2)}).")
            if tahmini_kritik_sure > 0:
                st.warning(f"⏳ **Kritik Eşik Uyarısı:** Tahmini **{tahmini_kritik_sure} dakika içinde** metan oranı %1.5 kritik patlama threshold'unu aşacak!")
            st.info("💡 **Proaktif Tavsiye:** Ana havalandırma fan devrini %20 artırın ve 3. Batı Galerisi'ndeki patlatmaları durdurun.")
        else:
            st.success("🟢 Gaz yükseliş trendi stabil. Anomali riski tespit edilmedi.")

    st.write("---")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🔄 Sensör Verisini Yenile (Anlık Akış)"):
            new_val = round(min(2.0, max(0.2, st.session_state.ch4_history[-1] + random.uniform(-0.1, 0.25))), 2)
            st.session_state.ch4_history.pop(0)
            st.session_state.ch4_history.append(new_val)
            st.rerun()
            
    with col_btn2:
        if st.button("⚠️ Yapay Anomali Tetikle (Test)"):
            st.session_state.ch4_history = [0.5, 0.7, 0.95, 1.2, 1.45]
            st.rerun()

    st.write("---")
    
    st.subheader("🗺️ Maden GIS ve Risk Haritası")
    
    harita_tipi = st.radio("Harita Modunu Seçin:", ["⛏️ Yeraltı Kat Planı (Galeri Krokisi)", "🛰️ Açık Ocak / Yerüstü (Uydu GIS)"], horizontal=True)
    
    if harita_tipi == "⛏️ Yeraltı Kat Planı (Galeri Krokisi)":
        try:
            import plotly.graph_objects as go
            
            galeriler = ["Ana Desandre", "1. Doğu Galerisi", "2. Batı Galerisi", "3. Ayna (Aktif)"]
            x_coords = [0, 50, -50, -70]
            y_coords = [0, -100, -150, -250]
            risk_levels = [1, 2, 2, 5 if ch4_val >= 1.4 else 3] 
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=x_coords, y=y_coords, mode='lines', line=dict(color='gray', width=4), name='Galeri Hatları'))
            
            fig.add_trace(go.Scatter(
                x=x_coords, y=y_coords, text=galeriler, mode='markers+text', textposition="top center",
                marker=dict(size=[r*10 for r in risk_levels], color=risk_levels, colorscale='Reds', showscale=True),
                name='Risk Noktaları'
            ))
            
            fig.update_layout(title="Yeraltı Maden Kot Planı (Kuşbakışı)", xaxis_title="Batı - Doğu Ekseni", yaxis_title="Derinlik / Yön Ekseni", template="plotly_dark", height=450)
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.warning("Yeraltı haritası için terminalden 'pip install plotly' kurmanız gereklidir.")
            
    else:
        try:
            import folium
            from streamlit_folium import st_folium
            
            merkez_enlem, merkez_boylam = 39.9056, 30.0381 
            m = folium.Map(location=[merkez_enlem, merkez_boylam], zoom_start=13, tiles="OpenStreetMap")
            
            folium.Marker(
                [39.9100, 30.0400],
                popup="Pasa Döküm Alanı - Şev Kayması Riski",
                tooltip="Uyarı: Sarı Risk",
                icon=folium.Icon(color="orange", icon="info-sign")
            ).add_to(m)
            
            folium.Marker(
                [39.9000, 30.0350],
                popup="Açık Ocak Arın Bölgesi - Patlatma Sonrası Çatlak",
                tooltip="Kritik: Kırmızı Risk",
                icon=folium.Icon(color="red", icon="warning-sign")
            ).add_to(m)
            
            folium.Marker(
                [39.9056, 30.0381],
                popup="Ana Tesis ve Kantar - Sorun Yok",
                tooltip="Normal",
                icon=folium.Icon(color="green", icon="ok-circle")
            ).add_to(m)
            
            st.caption("Açık ocak sahası yerüstü izleme modülü.")
            st_folium(m, width=900, height=450, returned_objects=[])
        except ImportError:
            st.warning("Yerüstü haritası için terminalden 'pip install folium streamlit-folium' kurmanız gereklidir.")

# --- TAB 6: PERSONEL & VARDİYA MATRİSİ ---
with tab_personel:
    st.subheader("👷‍♂️ Personel Yetkinlik, Sağlık & MYK Uyumluluk Matrisi")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("### ➕ Yeni Personel Kaydı")
        with st.form("personel_formu", clear_on_submit=True):
            p_ad = st.text_input("Ad Soyad:")
            p_sicil = st.text_input("Sicil No:")
            p_gorev = st.selectbox("Görevi / Unvanı:", ["Tarakçı / Kazıcı", "Dinamitçi / Patlatma Uzmanı", "Makinist", "Gaz Ölçüm Elemanı", "Ayna Çavuşu", "Elektrik / Mekanik Bakımcı"])
            p_saglik = st.date_input("Sağlık Raporu Bitiş Tarihi:")
            p_myk = st.selectbox("MYK Yetki Belgesi Durumu:", ["Geçerli / Aktif", "Süresi Doldu", "Eksik / Yok"])
            p_vardiya = st.selectbox("Atandığı Vardiya:", ["Gündüz (08:00 - 16:00)", "Pasa (16:00 - 00:00)", "Gece (00:00 - 08:00)"])
            
            if st.form_submit_button("Personeli Sisteme Kaydet", type="primary", use_container_width=True):
                if p_ad and p_sicil:
                    if personel_ekle(p_ad, p_sicil, p_gorev, str(p_saglik), p_myk, p_vardiya):
                        st.success(f"{p_ad} personeli veritabanına başarıyla eklendi!")
                        st.rerun()
                    else:
                        st.error("Hata: Sicil numarası zaten kayıtlı olabilir.")
                else:
                    st.warning("Lütfen Ad Soyad ve Sicil No alanlarını doldurun.")

    with col2:
        st.markdown("### 📋 Kayıtlı Personel Listesi ve Risk Uyarıları")
        personeller = personel_listesi_getir()
        
        if not personeller.empty:
            bugun = datetime.now().strftime("%Y-%m-%d")
            
            def durum_isle(row):
                if row['myk_belge_durumu'] != "Geçerli / Aktif" or row['saglik_raporu_tarihi'] < bugun:
                    return "❌ UYGUNSUZ / RİSKLİ"
                return "✅ UYGUN"

            personeller['İSG Uyumluluk Statusu'] = personeller.apply(durum_isle, axis=1)
            
            st.dataframe(
                personeller[['sicil_no', 'ad_soyad', 'gorev', 'saglik_raporu_tarihi', 'myk_belge_durumu', 'vardiya', 'İSG Uyumluluk Statusu']],
                use_container_width=True
            )
            
            riskli_sayisi = len(personeller[personeller['İSG Uyumluluk Statusu'] == "❌ UYGUNSUZ / RİSKLİ"])
            if riskli_sayisi > 0:
                st.error(f"⚠️ DİKKAT: Vardiyalarda çalışmaya engel veya belgeleri eksik/süresi dolmuş **{riskli_sayisi} personel** tespit edildi!")
        else:
            st.info("Henüz sisteme kayıtlı personel bulunmamaktadır.")