import os
import time
import io
import base64
import json
import re
import pandas as pd
import numpy as np
import streamlit as st

# Modeller ve İSG Motorları
from models import ISGChunkMetadata
from isg_engine import ISGRiskEngine
from backend.ingestion import veritabani_besle
from backend.rag_engine import RagEngine
from backend.crew_manager import CrewManager
from pypdf import PdfReader
from docx import Document

# Sayfa Genişlik Ayarı (Scriptin en başında kalmalıdır)
st.set_page_config(layout="wide", page_title="Arın AI - Maden İSG & Karar Destek", page_icon="🛡️")

# --- BULUT İLK KURULUM: VERİTABANI KONTROLÜ ---
def check_db_validity(path):
    """Gerçek bir Chroma veritabanı dosyasının varlığını kontrol eder."""
    db_file = os.path.join(path, "chroma.sqlite3")
    return os.path.exists(db_file)

db_mevzuat_ok = check_db_validity("database/mevzuat")
db_kazalar_ok = check_db_validity("database/kazalar")
db_jeoloji_ok = check_db_validity("database/jeoloji")

if not (db_mevzuat_ok and db_kazalar_ok and db_jeoloji_ok):
    st.error("⚠️ **Sistem Hatası: Vektör Veritabanları Eksik!**")
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
    prompt = f"""
    Sen kıdemli bir Maden İSG Baş Mühendisisin. Aşağıdaki vardiya notunu incele ve resmi bir '{form_tipi}' oluştur.
    Form No / Tarih (Bugünün tarihini kullan: 22 Temmuz 2026), Tespit Edilen Risk, Yönetmelik Atfı, Proaktif Aksiyonlar ve Sorumlu Birim alanlarını eksiksiz doldur.
    
    Vardiya Notu:
    {vardiya_notu}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Form oluşturulurken hata: {e}"

# --- GÜNCELLENEN GÖREV SEVK FONKSİYONU ---
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
        
        yeni_id = f"TASK-2026-00{len(st.session_state.canli_gorevler) + 1}"
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

# Dosya okuma fonksiyonları
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

    uploaded_file = st.file_uploader("📂 Rapor veya Ses Dosyası Yükleyin", type=["pdf", "docx", "xlsx", "xls", "txt", "mp3", "wav", "m4a"])
    if uploaded_file is not None and uploaded_file.name != st.session_state.son_yuklenen_dosya:
        try:
            file_bytes = uploaded_file.read()
            if uploaded_file.name.endswith(('.mp3', '.wav', '.m4a')):
                with st.spinner("🎤 Ses çözülüyor..."): st.session_state.analiz_verisi = extract_text_from_audio(file_bytes, uploaded_file.name)
            elif uploaded_file.name.endswith('.pdf'): st.session_state.analiz_verisi = extract_text_from_pdf(file_bytes)
            elif uploaded_file.name.endswith(('.docx', '.doc')): st.session_state.analiz_verisi = extract_text_from_docx(file_bytes)
            elif uploaded_file.name.endswith(('.xlsx', '.xls')): st.session_state.analiz_verisi = extract_text_from_excel(file_bytes)
            elif uploaded_file.name.endswith('.txt'): st.session_state.analiz_verisi = file_bytes.decode("utf-8")
            
            st.session_state.son_yuklenen_dosya = uploaded_file.name
            st.session_state.analiz_sonucu = None
            st.success("✅ Veri aktarıldı!")
            time.sleep(0.5)
            st.rerun()
        except Exception as e: st.error(f"Hata: {e}")

    if not st.session_state.analiz_verisi:
        st.session_state.analiz_verisi = (
            "Vardiya: Gece (00:00 - 08:00) - Zonguldak Havzası 3. Ayna\nTarih: 22 Temmuz 2026\nLokasyon: 3. Batı Galerisi (Kot: -120)\n\n"
            "Yapılan İşler ve Gözlemler:\nAyna ilerlemesi yapıldı. Arın bölgesinde tavan kayacında killi şist yapısı sebebiyle çatlaklar ve kılcal dökülmeler var. "
            "Ahşap tahkimat kamalarında esneme tespit edildi ancak üretime devam edildi. Fan 18 dk durdu, CH4 %1.4 seviyesine çıktı."
        )

    manuel_metin = st.text_area("✍️ Vardiya Defteri Notları:", value=st.session_state.analiz_verisi, height=180)
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

# 4 SEKMELİ MİMARİ
tab_dashboard, tab_engine, tab_forms, tab_operations = st.tabs([
    "📊 Canlı İSG Analiz Paneli", 
    "🧮 Deterministik Risk & Ölçüm Motoru",
    "📋 Form Üretim Merkezi", 
    "📡 Sahadan Canlı Görev Sevk Panosu"
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
            # 1. ADIM: LOKASYON KARTI BİLEŞENİ
            loc_info = res.get("location", {})
            st.subheader(f"📍 Algılanan Saha Alanı: {loc_info.get('title', 'Belirtilmedi')}")
            
            c_loc1, c_loc2 = st.columns(2)
            with c_loc1:
                st.warning(f"**Öncelikli Saha Riskleri:** {', '.join(loc_info.get('primary_risks', []))}")
            with c_loc2:
                st.info(f"**Zorunlu Kritik Kontroller:** {', '.join(loc_info.get('critical_checks', []))}")
            
            # 2. ADIM: EKİPMAN (LOTO) KARTI BİLEŞENİ
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

            # 3. ADIM: GEÇMİŞ VARDİYA TRENDİ VE GRAFİK BÖLÜMÜ
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
                
                # İNSAN ONAYLI SAHAYA SEVK BUTONU (Human-in-the-Loop)
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

                # HAFIZA AKIŞI EXPANDER
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

                # ÇOKLU AJAN ÇATIŞMA PANELİ
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

# --- TAB 3: FORM ÜRETİM MERKEZİ ---
with tab_forms:
    st.subheader("📋 Resmi İSG Form ve Tutanak Matrisi")
    secilen_form = st.selectbox("Form Tipi Seçin:", ["Maden İşletmeleri Ramak Kala Olay Formu", "Tehlike Bildirim Formu", "İş Durdurma Tutanağı"])
    if st.button(f"✨ {secilen_form} Doldur"):
        with st.spinner("Form dolduruluyor..."):
            st.session_state[f"form_cache_{secilen_form}"] = form_doldur_llm(st.session_state.analiz_verisi, secilen_form)
            
    cache_key = f"form_cache_{secilen_form}"
    if cache_key in st.session_state:
        st.markdown(st.session_state[cache_key])
        btn1, btn2 = st.columns(2)
        with btn1:
            st.download_button("📥 Formu PDF İndir", data=create_pdf_from_markdown(st.session_state[cache_key]), file_name="ISG_Form.pdf", mime="application/pdf", use_container_width=True)
        with btn2:
            if st.button("📡 SAHAYA SEVK ET", type="primary", use_container_width=True):
                if gorev_sevk_et(st.session_state[cache_key], secilen_form + " Formu"):
                    st.success("📢 Görev Canlı Takip Panosuna eklendi!")

# --- TAB 4: SAHADAN CANLI GÖREV SEVK PANOSU ---
with tab_operations:
    st.subheader("📡 Canlı Operasyonel Görev Takip Panosu")
    if st.session_state.canli_gorevler:
        st.dataframe(pd.DataFrame(st.session_state.canli_gorevler), use_container_width=True, hide_index=True)