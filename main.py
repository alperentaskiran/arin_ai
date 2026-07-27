import os
import time
import io
import base64
import json
import re
from datetime import datetime
import random
import sqlite3
import hashlib

# ==========================================
# CHROMA VE RUST KİLİTLENMELERİNİ ENGELLEYEN AYARLAR
# ==========================================
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_SERVER_NOFILE"] = "1"

import pandas as pd
import numpy as np

if not hasattr(np, "uint"): np.uint = np.uint64
if not hasattr(np, "int_"): np.int_ = np.int64
if not hasattr(np, "float_"): np.float_ = np.float64
import streamlit as st

try:
    import cv2
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    st.error("Lütfen terminalden şu kütüphaneleri yükleyin: pip install opencv-python pillow")

from isg_engine import ISGRiskEngine
from backend.rag_engine import RagEngine
from backend.crew_manager import CrewManager
from pypdf import PdfReader
from docx import Document

st.set_page_config(layout="wide", page_title="Arın AI - Maden İSG & Karar Destek", page_icon="🛡️")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .stButton>button { height: 3.2rem !important; font-size: 1.1rem !important; font-weight: bold !important; border-radius: 10px !important; }
    .saha-card { background-color: #1E293B; border-left: 6px solid #F97316; padding: 15px; border-radius: 8px; margin-bottom: 15px; }
    .feedback-card { background-color: #0F172A; border: 1px solid #334155; padding: 15px; border-radius: 8px; margin-top: 10px; }
    .sensor-critical { background-color: #7F1D1D; border: 2px solid #EF4444; padding: 15px; border-radius: 8px; color: white; margin-bottom: 10px; }
    .sensor-normal { background-color: #064E3B; border: 1px solid #10B981; padding: 15px; border-radius: 8px; color: white; margin-bottom: 10px; }
    .roi-card { background-color: #065F46; border-left: 6px solid #34D399; padding: 20px; border-radius: 10px; color: white; }
    </style>
""", unsafe_allow_html=True)

# --- SQLITE VERİTABANI BAŞLATMA ---
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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kullanicilar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kullanici_adi TEXT UNIQUE NOT NULL,
            sifre TEXT NOT NULL,
            ad_soyad TEXT NOT NULL,
            sicil_no TEXT UNIQUE NOT NULL,
            rol TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kurumsal_hafiza (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih TEXT NOT NULL,
            saha_durumu TEXT NOT NULL,
            ai_karari TEXT NOT NULL,
            basmuhendis_notu TEXT NOT NULL,
            onaylayan_kullanici TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS taseronlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_adi TEXT UNIQUE NOT NULL,
            hizmet_alani TEXT NOT NULL,
            calisan_sayisi INTEGER NOT NULL,
            isg_skoru INTEGER NOT NULL,
            son_denetim_tarihi TEXT NOT NULL,
            durum TEXT NOT NULL
        )
    """)
    
    cursor.execute("SELECT COUNT(*) FROM kullanicilar WHERE kullanici_adi = 'alperen.taskiran'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT OR IGNORE INTO kullanicilar (kullanici_adi, sifre, ad_soyad, sicil_no, rol) 
            VALUES (?, ?, ?, ?, ?)
        """, ("alperen.taskiran", "Aethel2026!", "Alperen Taşkıran", "SICIL-001", "Başmühendis"))
        
        varsayilan_saha = [
            ("isg_uzmani", "1234", "Aylin Yılmaz", "SICIL-002", "İSG Uzmanı"),
            ("vardiya1", "1234", "Ahmet Demir", "SICIL-003", "Vardiya Amiri"),
            ("elif.sila.akcay", "Aethel2026!", "Elif Sıla Akçay", "SICIL-000", "Başmühendis")
        ]
        cursor.executemany("INSERT OR IGNORE INTO kullanicilar (kullanici_adi, sifre, ad_soyad, sicil_no, rol) VALUES (?, ?, ?, ?, ?)", varsayilan_saha)

    cursor.execute("SELECT COUNT(*) FROM taseronlar")
    if cursor.fetchone()[0] == 0:
        ornek_taseronlar = [
            ("Atlas Hafriyat A.Ş.", "Galeri Kazı & Taşıma", 45, 92, "2026-07-15", "🟢 Uygun"),
            ("Toros Dinamit & Patlatma", "Patlatma Operasyonları", 12, 78, "2026-07-20", "🟡 Şartlı Uygun"),
            ("Kaya Sondaj Ltd.", "Sondaj & Enjeksiyon", 20, 64, "2026-07-01", "🔴 Riskli / Denetim Gerekli")
        ]
        cursor.executemany("INSERT INTO taseronlar (firma_adi, hizmet_alani, calisan_sayisi, isg_skoru, son_denetim_tarihi, durum) VALUES (?, ?, ?, ?, ?, ?)", ornek_taseronlar)
        
    conn.commit()
    conn.close()

init_db()

# --- BULUT İLK KURULUM ---
def check_db_validity(path):
    return os.path.exists(os.path.join(path, "chroma.sqlite3"))

if not (check_db_validity("database/mevzuat") and check_db_validity("database/kazalar") and check_db_validity("database/jeoloji")):
    st.warning("⚠️ **Sistem Uyarısı: Vektör Veritabanları Hazırlanıyor...**")
    try:
        from backend.ingestion import veritabani_besle
        veritabani_besle()
        st.success("✅ Veritabanları oluşturuldu!")
        st.rerun()
    except Exception as e:
        st.error(f"Veritabanı oluşturma hatası: {e}")
        st.stop()

# --- GLOBAL DURUM YÖNETİMİ ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user_role" not in st.session_state: st.session_state.user_role = None
if "user_name" not in st.session_state: st.session_state.user_name = None
if "analiz_basladi" not in st.session_state: st.session_state.analiz_basladi = False

if "canli_gorevler" not in st.session_state:
    st.session_state.canli_gorevler = [{
        "Gorev ID": "TASK-2026-001", "Kaynak Belge": "Sistem Açılış Testi",
        "Sorumlu Birim": "İSG Şefliği", "Aksiyon / İş Emri": "Arın AI Enterprise karar destek sistemi devreye alındı.",
        "Termin": "Tamamlandı", "Durum": "🟢 Aktif / Takipte"
    }]

# --- IoT CANLI SENSÖR SİMÜLATÖRÜ ---
def get_live_iot_data(anomaly_mode=False):
    if anomaly_mode:
        return {
            "ch4_percent": round(random.uniform(1.6, 2.4), 2),
            "co_ppm": random.randint(55, 120),
            "o2_percent": round(random.uniform(18.0, 19.2), 1),
            "temp_c": round(random.uniform(32.0, 38.5), 1),
            "humidity": random.randint(75, 95),
            "wearable_heart_rate": random.randint(115, 150),
            "wearable_fall_detected": random.choice([True, False])
        }
    else:
        return {
            "ch4_percent": round(random.uniform(0.1, 0.4), 2),
            "co_ppm": random.randint(5, 25),
            "o2_percent": round(random.uniform(20.5, 20.9), 1),
            "temp_c": round(random.uniform(21.0, 25.5), 1),
            "humidity": random.randint(45, 65),
            "wearable_heart_rate": random.randint(68, 88),
            "wearable_fall_detected": False
        }

# --- FONKSİYONLAR ---
def kullanici_dogrula(kullanici_adi, sifre):
    conn = sqlite3.connect("database/arin_ai_enterprise.db")
    cursor = conn.cursor()
    cursor.execute("SELECT ad_soyad, rol FROM kullanicilar WHERE kullanici_adi = ? AND sifre = ?", (kullanici_adi, sifre))
    user = cursor.fetchone()
    conn.close()
    return user

def sifre_guncelle(kullanici_adi, sicil_no, yeni_sifre):
    conn = sqlite3.connect("database/arin_ai_enterprise.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM kullanicilar WHERE kullanici_adi = ? AND sicil_no = ?", (kullanici_adi, sicil_no))
    if cursor.fetchone():
        cursor.execute("UPDATE kullanicilar SET sifre = ? WHERE kullanici_adi = ?", (yeni_sifre, kullanici_adi))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def yeni_kullanici_ekle(kullanici_adi, sifre, ad_soyad, sicil_no, rol):
    conn = sqlite3.connect("database/arin_ai_enterprise.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO kullanicilar (kullanici_adi, sifre, ad_soyad, sicil_no, rol) VALUES (?, ?, ?, ?, ?)", (kullanici_adi, sifre, ad_soyad, sicil_no, rol))
        conn.commit()
        return True
    except Exception: return False
    finally: conn.close()

def kullanici_listesi_getir():
    conn = sqlite3.connect("database/arin_ai_enterprise.db")
    df = pd.read_sql_query("SELECT id, kullanici_adi, ad_soyad, sicil_no, rol FROM kullanicilar", conn)
    conn.close()
    return df

def kurumsal_hafizaya_ekle(saha_durumu, ai_karari, basmuhendis_notu, onaylayan):
    conn = sqlite3.connect("database/arin_ai_enterprise.db")
    cursor = conn.cursor()
    tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO kurumsal_hafiza (tarih, saha_durumu, ai_karari, basmuhendis_notu, onaylayan_kullanici) VALUES (?, ?, ?, ?, ?)", (tarih, saha_durumu, ai_karari, basmuhendis_notu, onaylayan))
    conn.commit()
    conn.close()

def kurumsal_hafiza_getir():
    conn = sqlite3.connect("database/arin_ai_enterprise.db")
    df = pd.read_sql_query("SELECT * FROM kurumsal_hafiza ORDER BY id DESC", conn)
    conn.close()
    return df

def taseron_listesi_getir():
    conn = sqlite3.connect("database/arin_ai_enterprise.db")
    df = pd.read_sql_query("SELECT * FROM taseronlar", conn)
    conn.close()
    return df

# ==========================================
# GİRİŞ (LOGIN) EKRANI
# ==========================================
if not st.session_state.logged_in:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        try:
            st.image("arin_logo.png", use_container_width=True) # Arın AI Logosu
        except:
            pass
            
        st.markdown("<h1 style='text-align: center;'>🛡️ Arın AI Giriş Portalı</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: gray;'>Aethel Technologies Kurumsal Karar Destek Mimarisi</p>", unsafe_allow_html=True)
        
        tab_login, tab_reset = st.tabs(["🔑 Giriş Yap", "🔄 Şifremi Unuttum"])
        
        with tab_login:
            with st.form("login_form"):
                username = st.text_input("Kullanıcı Adı")
                password = st.text_input("Şifre", type="password")
                submit_button = st.form_submit_button("Sisteme Giriş Yap", use_container_width=True, type="primary")
                
                if submit_button:
                    user_data = kullanici_dogrula(username, password)
                    if user_data:
                        st.session_state.logged_in = True
                        st.session_state.user_name = user_data[0]
                        st.session_state.user_role = user_data[1]
                        st.success(f"Giriş başarılı! Hoş geldiniz, {user_data[0]}...")
                        st.balloons() # Giriş Animasyonu Geri Eklendi
                        time.sleep(1.5)
                        st.rerun()
                    else: st.error("Hatalı kullanıcı adı veya şifre!")

        with tab_reset:
            with st.form("reset_form"):
                r_username = st.text_input("Kullanıcı Adınız")
                r_sicil = st.text_input("Sicil Numaranız")
                r_new_pass = st.text_input("Yeni Şifreniz", type="password")
                reset_button = st.form_submit_button("Şifreyi Sıfırla", use_container_width=True)
                if reset_button:
                    if sifre_guncelle(r_username, r_sicil, r_new_pass): st.success("✅ Şifreniz değiştirildi!")
                    else: st.error("❌ Eşleşme başarısız.")
    st.stop() 

# ==========================================
# UYGULAMA ANA MOTORU
# ==========================================
def apply_kvkk_and_watermark(image_bytes):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        for (x, y, w, h) in faces:
            roi = img[y:y+h, x:x+w]
            img[y:y+h, x:x+w] = cv2.GaussianBlur(roi, (51, 51), 30)
            
        img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        raw_hash = hashlib.sha256(image_bytes).hexdigest()[:16]
        watermark_text = f"AETHEL AI - DIJITAL KANIT\nTarih: {timestamp}\nHash: {raw_hash}\n[KVKK Maskeleme Aktif]"
        draw.text((20, 20), watermark_text, fill=(255, 0, 0))
        buf = io.BytesIO()
        img_pil.save(buf, format="JPEG")
        return buf.getvalue()
    except Exception: return image_bytes

def analiz_et_gorsel(file_bytes, domain_prompt="Genel İSG Kuralları"):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    base64_image = base64.b64encode(file_bytes).decode('utf-8')
    prompt = f"Sen bir İSG denetçisisin. Uzmanlık: {domain_prompt}. Bu fotoğrafı incele, İSG ihlallerini ve ISO 45001 / MSHA uyumsuzluklarını tespit et."
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}],
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e: return f"Görsel analiz hatası: {e}"

def extract_text_from_audio(file_bytes, file_name):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    temp_filename = f"temp_{file_name}"
    with open(temp_filename, "wb") as f: f.write(file_bytes)
    try:
        with open(temp_filename, "rb") as audio_file: return client.audio.transcriptions.create(model="whisper-1", file=audio_file, language="tr").text
    finally:
        if os.path.exists(temp_filename): os.remove(temp_filename)

def create_pdf_from_markdown(markdown_text):
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('PDFTitle', parent=styles['Heading1'], fontSize=16, leading=20, textColor='#F97316')
    body_style = ParagraphStyle('PDFBody', parent=styles['BodyText'], fontSize=10, leading=14)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = [Paragraph("Arın AI Enterprise - Karar Raporu", title_style), Spacer(1, 10)]
    
    for line in str(markdown_text).split('\n'):
        if line.strip():
            story.append(Paragraph(line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), body_style))
            story.append(Spacer(1, 3))

    doc.build(story)
    return buffer.getvalue()

def form_doldur_llm(vardiya_notu, form_tipi):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = f"Sen kıdemli bir Maden İSG Baş Mühendisisin. Aşağıdaki vardiya notunu incele ve resmi bir '{form_tipi}' oluştur.\n\nVardiya Notu:\n{vardiya_notu}"
    try:
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], temperature=0.3)
        return response.choices[0].message.content
    except Exception as e: return f"Form oluşturulurken hata: {e}"

def gorev_sevk_et(girdi_metni, kaynak_belge):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = f"Aşağıdaki İSG analizinden 'Sorumlu Birim', 'Aksiyon' ve 'Termin' ayıkla. Format: Sorumlu Birim | Aksiyon | Termin\n\nMetin:\n{girdi_metni}"
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.1)
        veri = response.choices[0].message.content.split("|")
        yeni_id = f"TASK-{datetime.now().year}-{len(st.session_state.canli_gorevler) + 1:03d}"
        st.session_state.canli_gorevler.append({
            "Gorev ID": yeni_id, "Kaynak Belge": kaynak_belge, "Sorumlu Birim": veri[0].strip() if len(veri)>0 else "İSG",
            "Aksiyon / İş Emri": veri[1].strip() if len(veri)>1 else "Analiz aksiyonu", "Termin": veri[2].strip() if len(veri)>2 else "Derhal",
            "Durum": "🔴 Sahaya Gönderildi"
        })
        return True
    except: return False

@st.cache_resource
def get_backend_services(): return RagEngine(), CrewManager()

try: rag_engine, crew_manager = get_backend_services()
except Exception: rag_engine, crew_manager = None, None

# --- SIDEBAR ---
with st.sidebar:
    try:
        st.image("logo.png", use_container_width=True) # Logo eklentisi
    except:
        pass
        
    st.success(f"👤 **{st.session_state.user_name}**")
    st.caption(f"YETKİ: {st.session_state.user_role}")
    
    if st.button("🚪 Sistemden Çıkış Yap", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()
        
    st.markdown("---")
    st.title("🛡️ Arın AI Enterprise")
    
    st.subheader("🌐 Uluslararası İSG Standardı & Tesis Tipi")
    iso_msha_modu = st.checkbox("🌍 MSHA & ISO 45001 Standart Denetimini Aktif Et", value=True)
    
    maden_tipi = st.selectbox("Çalışılan Tesis Tipi:", [
        "Değerli Metal (Altın, Gümüş - Siyanür / Atık Barajı)",
        "Metalik Madencilik (Bakır, Demir - Patlatma & Ağır Metal)",
        "Nadir Toprak Elementleri & Endüstriyel (Kimyasal Risk)",
        "Mermer & Doğaltaş (Şev Stabilitesi & Tel Kesme)",
        "Kömür & Yeraltı Galerisi (Grizu / Havalandırma)"
    ])
    
    domain_prompt = f"Çalışılan Alan: {maden_tipi}."
    if iso_msha_modu:
        domain_prompt += " Ayrıca Türkiye İSG Mevzuatına ek olarak ABD MSHA standartlarına ve ISO 45001 maddelerine paralel kıyaslama yap."
    st.session_state.current_domain_prompt = domain_prompt

    st.markdown("---")
    st.subheader("🔴 IoT Sensör Simülasyonu")
    sim_anomali = st.toggle("🚨 Yapay Anomali / Gaz Sızıntısı Simüle Et", value=False)
    
    if "analiz_verisi" not in st.session_state: st.session_state.analiz_verisi = ""

# --- ANA EKRAN ---
st.title("🛡️ Arın AI Enterprise: Proaktif Maden İSG Platformu")
st.caption(f"Aethel Technologies — Oturum: {st.session_state.user_name} ({st.session_state.user_role})")

if st.session_state.user_role == "Vardiya Amiri":
    st.warning("📱 **Saha Tablet Modu Aktif**")
    col_cam, col_audio = st.columns(2)
    with col_cam:
        camera_photo = st.camera_input("📷 Fotoğraf Çek")
        if camera_photo:
            processed_img = apply_kvkk_and_watermark(camera_photo.getvalue())
            st.session_state.analiz_verisi = analiz_et_gorsel(processed_img, st.session_state.current_domain_prompt)
            st.image(processed_img, caption="✅ Maskelendi")
    with col_audio:
        audio_file = st.file_uploader("🎙️ Ses Dosyası", type=["mp3", "wav"])
        if audio_file:
            st.session_state.analiz_verisi = extract_text_from_audio(audio_file.read(), audio_file.name)
            st.success("Ses metne dönüştürüldü!")

    v_not = st.text_area("Saha Gözlemleriniz:", value=st.session_state.analiz_verisi, height=150)
    if st.button("📤 RAPORU MERKEZE İLET", type="primary", use_container_width=True):
        st.session_state.analiz_verisi = v_not
        st.success("✅ Rapor Merkeze İletildi!")

else:
    # 8 SEKMELİ TAM KURUMSAL PANEL (Asistan Eklendi)
    tab_dashboard, tab_assistant, tab_hafiza, tab_scada, tab_roi, tab_taseron, tab_engine, tab_operations = st.tabs([
        "📊 Canlı İSG Analiz Paneli", 
        "💬 Veritabanı Asistanı",
        "🧠 Geri Bildirimli Kurumsal Hafıza",
        "🔴 SCADA / IoT Sensör",
        "💰 ROI Simülatörü",
        "🏗️ Taşeron & Tedarikçi",
        "🧮 Risk Motoru & Formlar", 
        "📡 Görev Sevk Merkezi"
    ])

    # TAB 1: ANALİZ (Dosya Yükleme Genişletildi)
    with tab_dashboard:
        if "analiz_sonucu" not in st.session_state: st.session_state.analiz_sonucu = None
        iot_data = get_live_iot_data(sim_anomali)

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        with kpi1: 
            if iot_data["ch4_percent"] > 1.5 or iot_data["co_ppm"] > 50:
                st.metric(label="🚨 Anlık Saha Risk Skoru", value="%95 (KRİTİK)", delta="Acil Durum")
            else:
                st.metric(label="🚨 Anlık Saha Risk Skoru", value="%22 (DÜŞÜK)", delta="Normal")
        with kpi2: st.metric(label="🧪 CH4 Metan Gazı", value=f"%{iot_data['ch4_percent']}", delta="Kritik!" if iot_data["ch4_percent"]>1.5 else "Güvenli")
        with kpi3: st.metric(label="💨 CO Karbonmonoksit", value=f"{iot_data['co_ppm']} ppm", delta="Tehlike!" if iot_data["co_ppm"]>50 else "Normal")
        with kpi4: st.metric(label="⌚ Giyilebilir Baret / Nabız", value=f"{iot_data['wearable_heart_rate']} BPM", delta="Düşme Algılandı!" if iot_data["wearable_fall_detected"] else "Normal")
        
        if iot_data["ch4_percent"] > 1.5:
            st.error(f"🚨 **KRİTİK YERALTI GAZ UYARISI:** Metan seviyesi %{iot_data['ch4_percent']} değerine ulaştı! Grizu patlama eşiği aşıldı.")

        st.write("---")

        col_in, col_out_main = st.columns([1, 2])
        with col_in:
            st.markdown("### ✍️ Saha & Sensör Verisi İnceleme")
            
            # KAPSAMLI DOSYA YÜKLEYİCİ EKLENDİ
            uploaded_file = st.file_uploader("📂 Çoklu Dosya Yükle (Fotoğraf, PDF, TXT, Ses)", type=["png", "jpg", "jpeg", "pdf", "txt", "mp3", "wav"])
            if uploaded_file:
                if uploaded_file.name.endswith(("png", "jpg", "jpeg")):
                    processed_img = apply_kvkk_and_watermark(uploaded_file.getvalue())
                    st.image(processed_img, caption="✅ Yüklenen Görsel (Maskeli)")
                    if st.button("🖼️ Görseli Analiz Et"):
                        st.session_state.analiz_verisi = analiz_et_gorsel(processed_img, st.session_state.current_domain_prompt)
                elif uploaded_file.name.endswith("pdf"):
                    pdf_reader = PdfReader(uploaded_file)
                    st.session_state.analiz_verisi = "\n".join([page.extract_text() for page in pdf_reader.pages])
                    st.success("PDF Başarıyla Okundu!")
                elif uploaded_file.name.endswith("txt"):
                    st.session_state.analiz_verisi = uploaded_file.getvalue().decode("utf-8")
                    st.success("TXT Başarıyla Okundu!")
                elif uploaded_file.name.endswith(("mp3", "wav")):
                    if st.button("🎙️ Sesi Metne Çevir"):
                        st.session_state.analiz_verisi = extract_text_from_audio(uploaded_file.read(), uploaded_file.name)
            
            if st.button("📥 Canlı IoT Sensör Akışını Analize Ekle"):
                iot_text_summary = f"[CANLI SENSÖR VERİSİ - {datetime.now().strftime('%H:%M:%S')}]:\n- Metan (CH4): %{iot_data['ch4_percent']}\n- Karbonmonoksit (CO): {iot_data['co_ppm']} ppm\n- Oksijen (O2): %{iot_data['o2_percent']}\n- Sıcaklık: {iot_data['temp_c']} C\n- Personel Nabız: {iot_data['wearable_heart_rate']} BPM\n- Düşme Sensörü: {'DÜŞME TESPİT EDİLDİ!' if iot_data['wearable_fall_detected'] else 'Normal'}"
                st.session_state.analiz_verisi = iot_text_summary

            saha_metni = st.text_area("İncelenecek Vardiya/Saha Notu:", value=st.session_state.analiz_verisi, height=200)
            st.session_state.analiz_verisi = saha_metni
            
            if st.button("🚀 MULTI-AGENT ANALİZİ BAŞLAT", type="primary", use_container_width=True):
                hafiza_df = kurumsal_hafiza_getir()
                hafiza_baglami = ""
                if not hafiza_df.empty:
                    hafiza_baglami = "\n\n[ŞİRKETİN GEÇMİŞ BAŞMÜHENDİS ONAYLI KARARLARI]:\n" + hafiza_df.head(3).to_string()

                st.session_state.analiz_verisi_zengin = f"[Seçili Maden Tipi: {maden_tipi}]\n[Talimat: {st.session_state.current_domain_prompt}]{hafiza_baglami}\n\n{st.session_state.analiz_verisi}"
                st.session_state.analiz_basladi = True
                st.session_state.analiz_sonucu = None
                st.rerun()

        with col_out_main:
            if st.session_state.analiz_basladi and st.session_state.analiz_sonucu is None:
                try:
                    status = st.empty()
                    status.info("📍 Multi-Agent ve Sensör Verileri İşleniyor...")
                    if rag_engine:
                        hedef_metin = st.session_state.get("analiz_verisi_zengin", st.session_state.analiz_verisi)
                        st.session_state.analiz_sonucu = rag_engine.saha_raporu_analiz_et(hedef_metin)
                    status.empty()
                    st.session_state.analiz_basladi = False
                    st.rerun()
                except Exception as e:
                    st.error(f"Hata: {e}")
                    st.session_state.analiz_basladi = False

            if st.session_state.analiz_sonucu:
                res = st.session_state.analiz_sonucu
                if isinstance(res, dict):
                    loc_info = res.get("location", {})
                    st.subheader(f"📍 Saha Alanı: {loc_info.get('title', 'Belirtilmedi')}")
                    st.info(f"**Final Kararı:** {res.get('final_decision', '')}")
                    
                    st.markdown("<div class='feedback-card'>", unsafe_allow_html=True)
                    st.markdown("### 🎓 Human-in-the-Loop: Bu Kararı Kurumsal Hafızaya Öğret")
                    c_fb1, c_fb2 = st.columns([2, 1])
                    with c_fb1:
                        fb_not = st.text_input("Başmühendis Düzeltmesi / Notu:", placeholder="Örn: Sensör uyarısına paralel ikincil emiş fanları devreye alınmalı.")
                    with c_fb2:
                        if st.button("🧠 Kararı Onayla ve Hafızaya Kaydet", type="primary", use_container_width=True):
                            kurumsal_hafizaya_ekle(st.session_state.analiz_verisi, res.get('final_decision', ''), fb_not, st.session_state.user_name)
                            st.success("✅ Karar kaydedildi!")
                    st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown("<br>", unsafe_allow_html=True)
                    c_btn1, c_btn2 = st.columns(2)
                    with c_btn1:
                        pdf_data = create_pdf_from_markdown(res.get("final_decision", ""))
                        st.download_button("📥 PDF İndir", data=pdf_data, file_name="ArinAI_Karar.pdf", mime="application/pdf", use_container_width=True)
                    with c_btn2:
                        if st.button("📡 DÖF PLANINI SAHAYA SEVK ET", type="primary", use_container_width=True):
                            if gorev_sevk_et(res.get("final_decision", ""), "Başmühendis Karar Raporu"):
                                st.success("✅ DÖF Planı Canlı Takip Panosuna sevk edildi!")
                                time.sleep(1)
                                st.rerun()

    # TAB 2: VERİTABANI ASİSTANI (YENİDEN EKLENDİ)
    with tab_assistant:
        st.header("💬 İSG Mevzuat ve Kurumsal Hafıza Asistanı")
        st.caption("Uluslararası İSG standartları, eski kaza raporları veya şirket prosedürleri hakkında anında bilgi alın.")
        
        user_q = st.chat_input("İSG mevzuatı veya geçmiş kazalar hakkında bir soru sorun...")
        if user_q:
            st.chat_message("user").write(user_q)
            with st.spinner("Sektörel veritabanları taranıyor..."):
                if rag_engine:
                    cevap = rag_engine.soru_cevapla(user_q)
                    st.chat_message("assistant").write(cevap)
                else:
                    st.error("RAG Motoru aktif değil. Lütfen arkaplan servislerini kontrol edin.")

    # TAB 3: HAFIZA
    with tab_hafiza:
        st.subheader("🧠 Öğrenen Kurumsal Hafıza Veritabanı")
        hafiza_data = kurumsal_hafiza_getir()
        if not hafiza_data.empty: st.dataframe(hafiza_data, use_container_width=True)

    # TAB 4: SCADA / IoT
    with tab_scada:
        st.header("🔴 Canlı SCADA / IoT Sensör & Akıllı Baret Panosu")
        c_scada1, c_scada2 = st.columns(2)
        with c_scada1:
            st.subheader("📊 Yeraltı Galeri Sensörleri")
            if iot_data["ch4_percent"] > 1.5:
                st.markdown(f"<div class='sensor-critical'>🚨 <b>CH4 Metan Gazı: %{iot_data['ch4_percent']}</b><br>DURUM: KRİTİK / GRİZU RİSKİ</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='sensor-normal'>✅ <b>CH4 Metan Gazı: %{iot_data['ch4_percent']}</b><br>DURUM: Güvenli Limit</div>", unsafe_allow_html=True)
                
            if iot_data["co_ppm"] > 50:
                st.markdown(f"<div class='sensor-critical'>🚨 <b>CO Karbonmonoksit: {iot_data['co_ppm']} ppm</b><br>DURUM: TEHLİKELİ SIZINTI</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='sensor-normal'>✅ <b>CO Karbonmonoksit: {iot_data['co_ppm']} ppm</b><br>DURUM: Güvenli Limit</div>", unsafe_allow_html=True)

        with c_scada2:
            st.subheader("⌚ Personel Giyilebilir Teknoloji")
            st.write(f"**Personel Nabız:** {iot_data['wearable_heart_rate']} BPM")
            st.write(f"**Galeri Sıcaklığı:** {iot_data['temp_c']} °C")
            st.write(f"**Nem Oranı:** %{iot_data['humidity']}")
            if iot_data['wearable_fall_detected']:
                st.error("🚨 **AKILLI BARET ALARMI:** Personelde ani darbe/düşme tespit edildi! Konum: Galeri 3-B.")
            else:
                st.success("✅ Personel İvmeölçer: Hareket Normal")

    # TAB 5: FİNANSAL ROI & RİSK SİMÜLATÖRÜ
    with tab_roi:
        st.header("💰 Finansal Risk, Ceza / Kaza Engelleme & ROI Simülatörü")
        st.caption("Arın AI Enterprise sisteminin önlediği kaza riskleri ve sağladığı finansal ROI (Yatırım Getirisi) hesabı.")
        
        c_roi1, c_roi2 = st.columns([1, 2])
        with c_roi1:
            st.subheader("📊 Tesis Parametreleri")
            toplam_personel = st.number_input("Toplam Saha Çalışanı Sayısı:", value=250, step=10)
            yillik_dof_sayisi = st.number_input("Engellenen Yıllık Tehlikeli Durum (DÖF):", value=42, step=1)
            ortalama_is_gunu_kaybi = st.number_input("Olası Kaza Başına Gün Kaybı:", value=15, step=1)
            gunluk_isgucu_maliyeti = st.number_input("Çalışan Günlük Maliyeti (TL):", value=1500, step=100)
            
            # ROI HESABI
            engellenen_kaza_maliyeti = yillik_dof_sayisi * ortalama_is_gunu_kaybi * gunluk_isgucu_maliyeti
            tazminat_tasarrufu = yillik_dof_sayisi * 85000  # Olası tazminat/tedavi tasarruf tahmini
            toplam_finansal_kazanc = engellenen_kaza_maliyeti + tazminat_tasarrufu
            yazilim_maliyeti = 450000  # Enterprise Lisans Bedeli (Örnek)
            roi_orani = round(((toplam_finansal_kazanc - yazilim_maliyeti) / yazilim_maliyeti) * 100, 1)

        with c_roi2:
            st.markdown("<div class='roi-card'>", unsafe_allow_html=True)
            st.markdown(f"### 📈 Arın AI Tahmini Yıllık ROI: %{roi_orani}")
            st.markdown(f"* **Engellenen İş Gücü Kaybı Maliyeti:** {engellenen_kaza_maliyeti:,.0f} TL")
            st.markdown(f"* **Önlenen Tazminat / Ceza Risk Tasarrufu:** {tazminat_tasarrufu:,.0f} TL")
            st.markdown(f"## 💵 Net Tahmini Finansal Tasarruf: {toplam_finansal_kazanc:,.0f} TL / Yıl")
            st.markdown("</div>", unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.info("💡 **Yönetim Kurulu Notu:** Bu simülasyon, proaktif yapay zeka denetimlerinin sahada duruş sürelerini ve mevzuat cezalarını minimize etmesiyle hesaplanan net tasarrufu temsil eder.")

    # TAB 6: TAŞERON & TEDARİKÇİ UYUM YÖNETİMİ
    with tab_taseron:
        st.header("🏗️ Taşeron & Alt Yüklenici İSG Uyum Denetim Merkezi")
        st.caption("Maden sahasında faaliyet gösteren üçüncü taraf yüklenicilerin İSG skorları ve evrak takip panosu.")
        
        col_tas1, col_tas2 = st.columns([2, 1])
        with col_tas1:
            taseron_df = taseron_listesi_getir()
            if not taseron_df.empty:
                st.dataframe(taseron_df, use_container_width=True, hide_index=True)
        
        with col_tas2:
            st.subheader("➕ Yeni Taşeron Ekle")
            with st.form("taseron_ekle_form"):
                t_ad = st.text_input("Firma Adı:")
                t_hizmet = st.text_input("Hizmet Alanı:")
                t_sayi = st.number_input("Çalışan Sayısı:", value=10)
                t_skor = st.slider("İlk Denetim Skoru:", 0, 100, 85)
                if st.form_submit_button("Firmayı Kaydet", type="primary", use_container_width=True):
                    durum = "🟢 Uygun" if t_skor >= 80 else ("🟡 Şartlı Uygun" if t_skor >= 70 else "🔴 Riskli")
                    conn = sqlite3.connect("database/arin_ai_enterprise.db")
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO taseronlar (firma_adi, hizmet_alani, calisan_sayisi, isg_skoru, son_denetim_tarihi, durum) VALUES (?, ?, ?, ?, ?, ?)",
                                   (t_ad, t_hizmet, t_sayi, t_skor, datetime.now().strftime("%Y-%m-%d"), durum))
                    conn.commit()
                    conn.close()
                    st.success("Taşeron eklendi!")
                    st.rerun()

    # TAB 7: RİSK & FORMLAR (Genişletildi)
    with tab_engine:
        st.header("🧮 Risk Hesaplayıcıları & Form Hazırlayıcı")
        
        # Risk Matrisleri
        c1, c2 = st.columns(2)
        with c1:
            ihtimal_l = st.slider("İhtimal", 1, 5, 3, key="l_ihtimal")
            siddet_l = st.slider("Şiddet", 1, 5, 3, key="l_siddet")
            if st.button("L Tipi Skor Hesapla", type="primary"):
                res = ISGRiskEngine.l_tipi_matris(ihtimal_l, siddet_l)
                st.metric("Risk Skoru", res["risk_skoru"])
        with c2:
            fk_ihtimal = st.number_input("İhtimal", 0.1, 10.0, 3.0, 0.5)
            fk_frekans = st.number_input("Frekans", 0.5, 10.0, 6.0, 0.5)
            fk_derece = st.number_input("Derece", 1.0, 100.0, 7.0, 1.0)
            if st.button("Fine-Kinney Skor Hesapla", type="primary"):
                res_fk = ISGRiskEngine.fine_kinney(fk_ihtimal, fk_frekans, fk_derece)
                st.metric("Risk Değeri", res_fk["risk_degeri"])
                
        st.markdown("---")
        
        # Form Merkezi
        st.subheader("📋 Resmi İSG Form Merkezi")
        secilen_form = st.selectbox("Belge Tipi:", [
            "Tehlike Bildirim Formu", 
            "İş Durdurma Tutanağı",
            "Ramak Kala Raporu",
            "Kök Neden Analizi (5 Neden)",
            "Günlük Saha Denetim Listesi"
        ])
        if st.button(f"✨ {secilen_form} Üret"):
            st.session_state[f"form_cache_{secilen_form}"] = form_doldur_llm(st.session_state.analiz_verisi, secilen_form)
        
        cache_key = f"form_cache_{secilen_form}"
        if cache_key in st.session_state: 
            st.markdown(st.session_state[cache_key])

    # TAB 8: GÖREV & KULLANICI YÖNETİMİ
    with tab_operations:
        st.subheader("📡 Canlı Operasyonel Görev Takip Panosu & Kullanıcı Yönetimi")
        sub_t1, sub_t2 = st.tabs(["📋 Canlı DÖF İş Emri Panosu", "👥 Kullanıcı Hesap Yönetimi"])
        
        with sub_t1:
            if st.session_state.canli_gorevler:
                st.dataframe(pd.DataFrame(st.session_state.canli_gorevler), use_container_width=True, hide_index=True)
        
        with sub_t2:
            st.dataframe(kullanici_listesi_getir(), use_container_width=True)