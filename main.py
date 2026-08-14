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
import tempfile

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

# --- CUSTOM CSS (Arın AI Logo Renk Paleti Entegrasyonu) ---
st.markdown("""
    <style>
    /* Genel Zemin ve Yazı Renkleri */
    .stApp { background-color: #0F172A !important; color: #F8FAFC !important; }
    .stSidebar { background-color: #1E293B !important; color: #F8FAFC !important; border-right: 1px solid #334155; }
    
    /* Ana Buton Stilleri */
    .stButton>button { 
        height: 3.2rem !important; 
        font-size: 1.1rem !important; 
        font-weight: bold !important; 
        border-radius: 10px !important; 
    }
    
    /* Özel Kart Tasarımları (Arın AI Logo Kurumsal Renkleri) */
    .saha-card { background-color: #1E293B; border-left: 6px solid #F97316; padding: 15px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }
    .feedback-card { background-color: #1E293B; border: 1px solid #334155; border-left: 5px solid #06B6D4; padding: 15px; border-radius: 8px; margin-top: 10px; }
    .sensor-critical { background-color: #450A0A; border: 2px solid #EF4444; padding: 15px; border-radius: 8px; color: #FEE2E2; margin-bottom: 10px; font-weight: bold; }
    .sensor-normal { background-color: #064E3B; border: 1px solid #10B981; padding: 15px; border-radius: 8px; color: #ECFDF5; margin-bottom: 10px; font-weight: bold; }
    .roi-card { background-color: #1E293B; border-left: 6px solid #F97316; border-right: 2px solid #06B6D4; padding: 20px; border-radius: 10px; color: #F8FAFC; }
    
    /* Input ve Textarea Alanları */
    .stTextArea textarea {
        background-color: #1E293B !important;
        color: #06B6D4 !important;
        border: 1px solid #334155 !important;
        font-family: 'Courier New', monospace !important;
    }
    h1, h2, h3, h4, h5, h6, p, span { color: #F8FAFC !important; }
    </style>
""", unsafe_allow_html=True)

# --- ÖRNEK VARDIYA RAPORLARI SÖZLÜĞÜ ---
ORNEK_RAPORLAR = {
    "Değerli Metal (Altın, Gümüş - Siyanür / Atık Barajı)": """[VARDİYA RAPORU - ALTIN & GÜMÜŞ İŞLETME]
Tarih: 14.08.2026 | Vardiya: 08:00 - 16:00
Bölge: Liç Sahası ve Atık Barajı 2. Terfi Merkezi
1. Atık barajı savak seviyesi kot 412.50 m olarak ölçüldü, kritik doluluk eşiğinin 30 cm altında.
2. Liç pompaları çevresindeki sabit HCN (Hidrojen Siyanür) dedektörleri 3 ppm seviyesinde stabil.
3. 2 No'lu kostik yıkama tankı çevresinde göz duşu su basıncı düşük bulundu, bakım ekibine bildirim yapıldı.""",

    "Mermer & Doğaltaş (Şev Stabilitesi & Tel Kesme)": """[VARDİYA RAPORU - DOĞALTAŞ & MERMER OCAĞI]
Tarih: 14.08.2026 | Vardiya: 08:00 - 16:00
Bölge: Doğu Ayna - 3. Basamak Tel Kesme Alanı
1. Elmas tel kesme makinesinin koruma kafesinde gevşeme tespit edildi, operatör uyarılarak sabitlendi.
2. Ayna arkası şev çatlağında inklinometre hareketi 0.4 mm/gün (stabil aralıkta).
3. L90 yükleyici iş makinesinin geri vites sesli ikaz sistemi kontrol edildi, faal durumda.""",

    "Kömür & Yeraltı Galerisi (Grizu / Havalandırma)": """[VARDİYA RAPORU - YERALTI KÖMÜR OCAĞI]
Tarih: 14.08.2026 | Vardiya: 08:00 - 16:00
Bölge: -150 Kotu Ana Nakliyat Galerisi
1. Ana emici havalandırma fanı debisi 42 m³/sn olarak kaydedildi.
2. CH4 (Metan) arın seviyesinde %0.3, nakliyat bandında CO 12 ppm seviyesinde ölçüldü.
3. Tahkimat arkası hava kaçağı giderildi, personel giyilebilir baret sensörleri aktif sinyal iletiyor.""",

    "Metalik Madencilik (Bakır, Demir - Patlatma & Ağır Metal)": """[VARDİYA RAPORU - AÇIK OCAK BAKIR İŞLETMESİ]
Tarih: 14.08.2026 | Vardiya: 08:00 - 16:00
Bölge: Batı Pano Patlatma ve Yükleme Sahası
1. Delik delme tamamlandı, 18 No'lu patlatma basamağında emniyet şeridi 500 m yarıçapa çekildi.
2. Toz bastırma arazözleri yükleme güzergahında periyodik olarak çalıştırıldı (PM10: 42 µg/m³).
3. Yükleyici ekskavatör basamak altı tavan kontrolü yapıldı, askıda kaya parçası düşürüldü.""",

    "Nadir Toprak Elementleri & Endüstriyel (Kimyasal Risk)": """[VARDİYA RAPORU - KİMYASAL İŞLEME & AYRIŞTIRMA]
Tarih: 14.08.2026 | Vardiya: 08:00 - 16:00
Bölge: Asit Liçi ve Çözücü Ekstraksiyon Tesisi
1. Sülfürik asit besleme hattı sızdırmazlık contaları kontrol edildi, sızıntı tespit edilmedi.
2. Tesis içi ortam radyasyon dozu 0.18 µSv/h (doğal arka plan seviyesinde).
3. Havalandırma kuleleri gaz yıkayıcı (scrubber) pH değeri 8.2 olarak nötralize edildi."""
}

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
    
    # Kullanıcıları tek tek INSERT OR IGNORE ile ekle (Şarta bağlı kalmadan)
    varsayilan_kullanicilar = [
        ("alperen.taskiran", "Aethel2026!", "Alperen Taşkıran", "SICIL-001", "Başmühendis"),
        ("demo", "arin2026", "Misafir Araştırmacı", "DEMO-001", "İSG Denetçisi (Demo)"),
        ("isg_uzmani", "1234", "Aylin Yılmaz", "SICIL-002", "İSG Uzmanı"),
        ("vardiya1", "1234", "Ahmet Demir", "SICIL-003", "Vardiya Amiri"),
        ("elif.sila.akcay", "Aethel2026!", "Elif Sıla Akçay", "SICIL-000", "Başmühendis")
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO kullanicilar (kullanici_adi, sifre, ad_soyad, sicil_no, rol) 
        VALUES (?, ?, ?, ?, ?)
    """, varsayilan_kullanicilar)

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

# --- BULUT İLK KURULUM ---
def check_db_validity(path):
    return os.path.exists(os.path.join(path, "chroma.sqlite3"))

if not (check_db_validity("database/mevzuat") and check_db_validity("database/kazalar") and check_db_validity("database/jeoloji")):
    st.warning("⚠️ **Sistem Uyarısı: Vektör Veritabanları Hazırlanıyor...**")
    try:
        from backend.arin_ai_scraper_pipeline import run_full_arin_ai_ingestion # type: ignore
        run_full_arin_ai_ingestion()
        st.success("✅ Veritabanları oluşturuldu ve güncellendi!")
        st.rerun()
    except Exception as e:
        st.error(f"Veritabanı oluşturma hatası: {e}")
        st.stop()

# --- GLOBAL DURUM YÖNETİMİ ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user_role" not in st.session_state: st.session_state.user_role = None
if "user_name" not in st.session_state: st.session_state.user_name = None
if "sicil_no" not in st.session_state: st.session_state.sicil_no = None
if "analiz_basladi" not in st.session_state: st.session_state.analiz_basladi = False
if "splash_shown" not in st.session_state: st.session_state.splash_shown = False 

if "canli_gorevler" not in st.session_state:
    st.session_state.canli_gorevler = [{
        "Gorev ID": "TASK-2026-001", "Kaynak Belge": "Sistem Açılış Testi",
        "Sorumlu Birim": "İSG Şefliği", "Aksiyon / İş Emri": "Arın AI Enterprise karar destek sistemi devreye alındı.",
        "Termin": "Tamamlandı", "Durum": "🟢 Aktif / Takipte"
    }]

# --- DİNAMİK TESİS TİPİ IOT SENSÖR SİMÜLATÖRÜ ---
def get_live_iot_data(anomaly_mode=False, tesis_tipi="Kömür & Yeraltı Galerisi (Grizu / Havalandırma)"):
    base_data = {
        "ch4_percent": round(random.uniform(1.6, 2.4) if anomaly_mode else random.uniform(0.1, 0.4), 2),
        "co_ppm": random.randint(55, 120) if anomaly_mode else random.randint(5, 25),
        "o2_percent": round(random.uniform(18.0, 19.2) if anomaly_mode else random.uniform(20.5, 20.9), 1),
        "temp_c": round(random.uniform(32.0, 38.5) if anomaly_mode else random.uniform(21.0, 25.5), 1),
        "humidity": random.randint(75, 95) if anomaly_mode else random.randint(45, 65)
    }

    if "Mermer" in tesis_tipi:
        base_data["custom_label"] = "📐 Şev İnklinometre (Kayma)"
        base_data["custom_value"] = f"{random.uniform(4.5, 8.2):.1f} mm/gün" if anomaly_mode else f"{random.uniform(0.1, 0.6):.1f} mm/gün"
        base_data["custom_delta"] = "Kritik Deformasyon!" if anomaly_mode else "Stabil"
        base_data["scada_title"] = "📐 Şev Stabilitesi ve Tel Gerilimi"
        base_data["scada_detail"] = f"Elmas Tel Titreşim İvmesi: {'7.8 m/s² (AŞIRI)' if anomaly_mode else '1.2 m/s² (Normal)'}"
    elif "Değerli Metal" in tesis_tipi:
        base_data["custom_label"] = "🧪 HCN Siyanür Gazı"
        base_data["custom_value"] = f"{random.randint(14, 28)} ppm" if anomaly_mode else f"{random.randint(1, 4)} ppm"
        base_data["custom_delta"] = "Eşik Aşıldı!" if anomaly_mode else "Güvenli"
        base_data["scada_title"] = "🧪 Liç ve Atık Barajı İzleme"
        base_data["scada_detail"] = f"Atık Barajı Piezometre Basıncı: {'4.2 Bar (YÜKSEK)' if anomaly_mode else '1.8 Bar (Stabil)'}"
    elif "Metalik" in tesis_tipi:
        base_data["custom_label"] = "💨 PM10 Toz Yoğunluğu"
        base_data["custom_value"] = f"{random.randint(180, 320)} µg/m³" if anomaly_mode else f"{random.randint(35, 65)} µg/m³"
        base_data["custom_delta"] = "Toz Eşiği Aşıldı!" if anomaly_mode else "Normal"
        base_data["scada_title"] = "💥 Patlatma Sismik & Toz Analizi"
        base_data["scada_detail"] = f"Sismik Titreşim (PPV): {'18.4 mm/s (KRİTİK)' if anomaly_mode else '3.1 mm/s (Güvenli)'}"
    elif "Nadir Toprak" in tesis_tipi:
        base_data["custom_label"] = "☢️ Radyasyon Dozu"
        base_data["custom_value"] = f"{random.uniform(2.5, 5.0):.2f} µSv/h" if anomaly_mode else f"{random.uniform(0.12, 0.22):.2f} µSv/h"
        base_data["custom_delta"] = "Doz Limiti Aşıldı!" if anomaly_mode else "Normal"
        base_data["scada_title"] = "☢️ Radyolojik & Asit Reaktör Takibi"
        base_data["scada_detail"] = f"Asit Buharı Skrubber Basıncı: {'350 Pa (Tıkalı)' if anomaly_mode else '120 Pa (Normal)'}"
    else:
        # Kömür & Yeraltı Varsayılan
        base_data["wearable_heart_rate"] = random.randint(115, 150) if anomaly_mode else random.randint(68, 88)
        base_data["wearable_fall_detected"] = random.choice([True, False]) if anomaly_mode else False
        base_data["custom_label"] = "⌚ Giyilebilir Baret / Nabız"
        base_data["custom_value"] = f"{base_data['wearable_heart_rate']} BPM"
        base_data["custom_delta"] = "Düşme Algılandı!" if base_data["wearable_fall_detected"] else "Normal"
        base_data["scada_title"] = "⌚ Personel Giyilebilir Teknoloji"
        base_data["scada_detail"] = f"Personel Nabız: {base_data['wearable_heart_rate']} BPM | {'🚨 Düşme Alarmı!' if base_data['wearable_fall_detected'] else 'Hareket Normal'}"

    return base_data

# --- FONKSİYONLAR ---
def kullanici_dogrula(kullanici_adi, sifre):
    if not kullanici_adi or not sifre:
        return None
        
    kullanici_adi = str(kullanici_adi).strip()
    sifre = str(sifre).strip()
    
    # 1. Demo Kullanıcı için Doğrudan Garantili Giriş
    if kullanici_adi.lower() == "demo" and sifre == "arin2026":
        return ("Misafir Araştırmacı", "İSG Denetçisi (Demo)", "DEMO-001")
        
    # 2. Veritabanı Kontrolü (Diğer kullanıcılar için)
    try:
        conn = sqlite3.connect("database/arin_ai_enterprise.db")
        cursor = conn.cursor()
        cursor.execute("SELECT ad_soyad, rol, sicil_no FROM kullanicilar WHERE LOWER(kullanici_adi) = LOWER(?) AND sifre = ?", (kullanici_adi, sifre))
        user = cursor.fetchone()
        conn.close()
        return user
    except Exception as e:
        print(f"Giriş hatası: {e}")
        return None

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
# GİRİŞ (LOGIN) EKRANI & SPLASH SCREEN
# ==========================================
if not st.session_state.logged_in:
    if not st.session_state.splash_shown:
        splash = st.empty()
        with splash.container():
            st.markdown("<br><br><br><br><br>", unsafe_allow_html=True)
            sc1, sc2, sc3 = st.columns([1, 2, 1])
            with sc2:
                try:
                    st.image("aethel_logo.png", use_container_width=True)
                except:
                    pass
        time.sleep(2)
        st.session_state.splash_shown = True
        st.rerun()
    
    else:
        st.markdown("<br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            try:
                st.image("arin_logo.png", use_container_width=True) 
            except:
                pass
                
            st.markdown("<h1 style='text-align: center;'>🛡️ Arın AI Giriş Portalı</h1>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #06B6D4;'>Aethel Technologies Kurumsal Karar Destek Mimarisi</p>", unsafe_allow_html=True)
            
            st.info("💡 **Hızlı Test / Demo Girişi:**\n* **Kullanıcı Adı:** `demo`\n* **Şifre:** `arin2026`")
            
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
                            st.session_state.sicil_no = user_data[2]
                            st.success(f"Giriş başarılı! Hoş geldiniz, {user_data[0]}...")
                            time.sleep(1.2)
                            st.rerun()
                        else: 
                            st.error("Hatalı kullanıcı adı veya şifre!")

            with tab_reset:
                with st.form("reset_form"):
                    r_username = st.text_input("Kullanıcı Adınız")
                    r_sicil = st.text_input("Sicil Numaranız")
                    r_new_pass = st.text_input("Yeni Şifreniz", type="password")
                    reset_button = st.form_submit_button("Şifreyi Sıfırla", use_container_width=True)
                    if reset_button:
                        if sifre_guncelle(r_username, r_sicil, r_new_pass): 
                            st.success("✅ Şifreniz başarıyla değiştirildi!")
                        else: 
                            st.error("❌ Bilgiler eşleşmedi.")
        st.stop() 

# ==========================================
# UYGULAMA ANA MOTORU
# ==========================================
def apply_kvkk_and_watermark(image_bytes):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        cascade_frontal = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        cascade_profile = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_profileface.xml')
        cascade_plate = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_russian_plate_number.xml')
        
        faces_frontal = cascade_frontal.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
        faces_profile = cascade_profile.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
        plates = cascade_plate.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 10))
        
        all_targets = list(faces_frontal) + list(faces_profile) + list(plates)
        
        for (x, y, w, h) in all_targets:
            roi = img[y:y+h, x:x+w]
            img[y:y+h, x:x+w] = cv2.GaussianBlur(roi, (99, 99), 30)
            
        img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        raw_hash = hashlib.sha256(image_bytes).hexdigest()[:16]
        watermark_text = f"AETHEL AI - DIJITAL KANIT\nTarih: {timestamp}\nHash: {raw_hash}\n[KVKK Maskeleme Aktif]"
        draw.text((20, 20), watermark_text, fill=(255, 0, 0))
        
        buf = io.BytesIO()
        img_pil.save(buf, format="JPEG")
        return buf.getvalue()
    except Exception as e:
        return image_bytes

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

def rapor_pdf_olustur(rapor_metni):
    try:
        from fpdf import FPDF
    except ImportError:
        return b"Lutfen terminalden su kutuphaneyi yukleyin: pip install fpdf2"
        
    class PDFReport(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 14)
            self.cell(0, 10, 'Arin AI Enterprise - Karar Destek & Is Guvenligi Raporu', border=False, ln=True, align='C')
            self.ln(3)
            self.line(10, 22, 200, 22)
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.cell(0, 10, f'Aethel Technologies - Dijital Kanit & Raporlama | Sayfa {self.page_no()}', align='C')

    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font('Helvetica', '', 10)
    
    # Türkçe Karakter ve Markdown Temizliği (PDF bozulmasını kesin engeller)
    metin = str(rapor_metni)
    metin = metin.replace('**', '').replace('### ', '\n').replace('## ', '\n').replace('# ', '\n')
    
    tr_map = {
        'ı': 'i', 'İ': 'I', 'ğ': 'g', 'Ğ': 'G',
        'ü': 'u', 'Ü': 'U', 'ş': 's', 'Ş': 'S',
        'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C'
    }
    for tr_char, eng_char in tr_map.items():
        metin = metin.replace(tr_char, eng_char)
    
    # Paragrafları düzgün ekle
    for satir in metin.split('\n'):
        satir = satir.strip()
        if not satir:
            pdf.ln(3)
            continue
        
        # Başlık benzeri satırları koyu yap
        if satir.startswith(('1.', '2.', '3.', '4.', '5.', '⚖️', '🛡️', '📋', '📍', 'FINAL', 'KARAR')):
            pdf.set_font('Helvetica', 'B', 10)
            pdf.multi_cell(0, 6, satir.encode('latin-1', 'replace').decode('latin-1'))
            pdf.set_font('Helvetica', '', 10)
        else:
            pdf.multi_cell(0, 5, satir.encode('latin-1', 'replace').decode('latin-1'))
        pdf.ln(1)
    
    # Geçici dosya kilidine girmeden doğrudan RAM (byte) üzerinden çıktı alma
    try:
        # fpdf2 için:
        pdf_bytes = bytes(pdf.output())
    except TypeError:
        # Eski pyfpdf için fallback:
        pdf_bytes = pdf.output(dest='S').encode('latin-1')
        
    return pdf_bytes

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
        st.image("arin_logo.png", use_container_width=True) 
    except:
        pass
        
    st.success(f"👤 **{st.session_state.user_name}**")
    st.caption(f"YETKİ: {st.session_state.user_role} | {st.session_state.get('sicil_no', '')}")
    
    if st.button("🚪 Sistemden Çıkış Yap", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

    st.markdown("---")
    st.title("🛡️ Arın AI Enterprise")
    
    # --- ULUSLARARASI İSG STANDARDI & TESİS TİPİ ---
    st.subheader("🌐 Uluslararası İSG Standardı & Tesis Tipi")
    st.info("✅ **MSHA & ISO 45001** denetimi daimi olarak aktiftir.", icon="🛡️")
    
    maden_tipi = st.selectbox("Çalışılan Tesis Tipi:", [
        "Kömür & Yeraltı Galerisi (Grizu / Havalandırma)",
        "Mermer & Doğaltaş (Şev Stabilitesi & Tel Kesme)",
        "Değerli Metal (Altın, Gümüş - Siyanür / Atık Barajı)",
        "Metalik Madencilik (Bakır, Demir - Patlatma & Ağır Metal)",
        "Nadir Toprak Elementleri & Endüstriyel (Kimyasal Risk)"
    ])
    
    domain_prompt = f"Çalışılan Alan: {maden_tipi}. Ayrıca Türkiye İSG Mevzuatına ek olarak ABD MSHA standartlarına ve ISO 45001 maddelerine paralel kıyaslama yap."
    st.session_state.current_domain_prompt = domain_prompt

    st.markdown("---")
    
    # --- IOT SENSÖR SİMÜLASYONU ---
    st.subheader("🔴 IoT Sensör Simülasyonu")
    with st.container(border=True):
        st.caption("Sistemin risk tepkisini test etmek için canlı veri akışında yapay bir anomali oluşturun.")
        sim_anomali = st.toggle("🚨 Yapay Anomali / Risk Simüle Et", value=False)
        
        if sim_anomali:
            st.warning("⚠️ Anomali Devrede! Sensör değerleri tehlikeli eşiklerde üretiliyor.")
    
    if "analiz_verisi" not in st.session_state: 
        st.session_state.analiz_verisi = ""

# --- ANA EKRAN ---
st.title("🛡️ Arın AI Enterprise: Proaktif Maden İSG Platformu")
st.caption(f"Aethel Technologies — Aktif Oturum: {st.session_state.user_name} ({st.session_state.user_role})")

if st.session_state.user_role == "Vardiya Amiri":
    st.warning("📱 **Saha Tablet Modu Aktif**")
    col_cam, col_audio = st.columns(2)
    with col_cam:
        camera_photo = st.camera_input("📷 Fotoğraf Çek")
        if camera_photo:
            processed_img = apply_kvkk_and_watermark(camera_photo.getvalue())
            st.image(processed_img, caption="✅ Maskelendi")
            gorsel_sonuc = analiz_et_gorsel(processed_img, st.session_state.current_domain_prompt)
            st.info(gorsel_sonuc)
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

    # Canlı Dinamik Sensör Verilerini Çek
    iot_data = get_live_iot_data(sim_anomali, maden_tipi)

    # TAB 1: ANALİZ
    with tab_dashboard:
        if "analiz_sonucu" not in st.session_state: st.session_state.analiz_sonucu = None

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        with kpi1: 
            if sim_anomali or iot_data["ch4_percent"] > 1.5 or iot_data["co_ppm"] > 50:
                st.metric(label="🚨 Anlık Saha Risk Skoru", value="%95 (KRİTİK)", delta="Acil Durum")
            else:
                st.metric(label="🚨 Anlık Saha Risk Skoru", value="%22 (DÜŞÜK)", delta="Normal")
        with kpi2: 
            st.metric(label="🧪 CH4 Metan Gazı", value=f"%{iot_data['ch4_percent']}", delta="Kritik!" if iot_data["ch4_percent"]>1.5 else "Güvenli")
        with kpi3: 
            st.metric(label="💨 CO Karbonmonoksit", value=f"{iot_data['co_ppm']} ppm", delta="Tehlike!" if iot_data["co_ppm"]>50 else "Normal")
        with kpi4: 
            st.metric(label=iot_data["custom_label"], value=iot_data["custom_value"], delta=iot_data["custom_delta"])
        
        if iot_data["ch4_percent"] > 1.5:
            st.error(f"🚨 **KRİTİK YERALTI GAZ UYARISI:** Metan seviyesi %{iot_data['ch4_percent']} değerine ulaştı! Grizu patlama eşiği aşıldı.")

        st.write("---")

        col_in, col_out_main = st.columns([1, 2])
        with col_in:
            st.markdown("### ✍️ Saha & Sensör Verisi İnceleme")
            
            # --- ÖRNEK RAPOR DOLDURMA BUTONU ---
            if st.button("📋 Seçili Tesise Uygun Örnek Raporu Doldur", use_container_width=True):
                st.session_state.analiz_verisi = ORNEK_RAPORLAR.get(maden_tipi, "")
                st.rerun()

            uploaded_file = st.file_uploader("📂 Çoklu Dosya Yükle (Fotoğraf, PDF, TXT, Ses)", type=["png", "jpg", "jpeg", "pdf", "txt", "mp3", "wav"])
            if uploaded_file:
                if uploaded_file.name.endswith(("png", "jpg", "jpeg")):
                    processed_img = apply_kvkk_and_watermark(uploaded_file.getvalue())
                    st.image(processed_img, caption="✅ Yüklenen Görsel (Maskeli)")
                    
                    if st.button("🖼️ Sadece Görseli Analiz Et"):
                        with st.spinner("Görsel detaylı olarak inceleniyor..."):
                            gorsel_sonuc = analiz_et_gorsel(processed_img, st.session_state.current_domain_prompt)
                            st.info(f"**Görsel İnceleme Sonucu:**\n\n{gorsel_sonuc}")
                            
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
                        st.success("Ses deşifre edildi!")
            
            if st.button("📥 Canlı IoT Sensör Akışını Analize Ekle"):
                iot_text_summary = f"\n\n[CANLI SENSÖR VERİSİ - {datetime.now().strftime('%H:%M:%S')}]:\n- Tesis Tipi: {maden_tipi}\n- Metan (CH4): %{iot_data['ch4_percent']}\n- Karbonmonoksit (CO): {iot_data['co_ppm']} ppm\n- Oksijen (O2): %{iot_data['o2_percent']}\n- Sıcaklık: {iot_data['temp_c']} °C\n- {iot_data['custom_label']}: {iot_data['custom_value']}"
                st.session_state.analiz_verisi += iot_text_summary

            st.text_area("İncelenecek Vardiya/Saha Notu:", key="analiz_verisi", height=200)
            
            if st.button("🚀 MULTI-AGENT ANALİZİ BAŞLAT", type="primary", use_container_width=True):
                hafiza_df = kurumsal_hafiza_getir()
                hafiza_baglami = ""
                if not hafiza_df.empty:
                    hafiza_baglami = "\n\n[ŞİRKETİN GEÇMİŞ BAŞMÜHENDİS ONAYLI KARARLARI]:\n" + hafiza_df.head(3).to_string()

                ek_baglam = ""
                if uploaded_file and uploaded_file.name.endswith(("png", "jpg", "jpeg")):
                    gorsel_metni = analiz_et_gorsel(apply_kvkk_and_watermark(uploaded_file.getvalue()), st.session_state.current_domain_prompt)
                    ek_baglam = f"\n\n[ARKA PLAN GÖRSEL ANALİZİ]:\n{gorsel_metni}"
                    
                st.session_state.analiz_verisi_zengin = f"""[Seçili Maden Tipi: {maden_tipi}]
[Talimat: {st.session_state.current_domain_prompt}]
{hafiza_baglami}

[SİSTEM EMRİ KESİN KURAL]: AŞAĞIDAKİ VARDİYA NOTU / SENSÖR VERİSİ SAHANIN GÜNCEL DURUMUDUR. SADECE BU DEĞERLERE ODAKLAN! EĞER DEĞERLER NORMAL LİMİTLER İÇİNDEYSE DURUMUN GÜVENLİ OLDUĞUNU BELİRT. ASLA GEÇMİŞ KAZALARI VEYA İLGİSİZ ARIZA SENARYOLARINI UYDURMA.

[VARDİYA NOTU]:
{st.session_state.analiz_verisi}{ek_baglam}
"""
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
                        pdf_data = rapor_pdf_olustur(res.get("final_decision", ""))
                        st.download_button("📥 PDF İndir", data=pdf_data, file_name="ArinAI_Karar.pdf", mime="application/pdf", use_container_width=True)
                    with c_btn2:
                        if st.button("📡 DÖF PLANINI SAHAYA SEVK ET", type="primary", use_container_width=True):
                            if gorev_sevk_et(res.get("final_decision", ""), "Başmühendis Karar Raporu"):
                                st.success("✅ DÖF Planı Canlı Takip Panosuna sevk edildi!")
                                time.sleep(1)
                                st.rerun()

    # TAB 2: VERİTABANI ASİSTANI
    with tab_assistant:
        st.header("💬 İSG Mevzuat ve Kurumsal Hafıza Asistanı")
        
        st.markdown("""
        <style>
        .chat-name-user { font-size: 0.8rem; color: #06B6D4; font-weight: 600; margin-bottom: 5px; letter-spacing: 0.5px; }
        .chat-name-bot { font-size: 0.8rem; color: #F97316; font-weight: 600; margin-bottom: 5px; letter-spacing: 0.5px; }
        </style>
        """, unsafe_allow_html=True)
        
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []
            
        chat_container = st.container(height=500, border=False)
        
        with chat_container:
            for msg in st.session_state.chat_history:
                if msg["role"] == "user":
                    with st.chat_message("user", avatar="👤"):
                        st.markdown(f"<div class='chat-name-user'>Siz ({st.session_state.user_name})</div>", unsafe_allow_html=True)
                        st.markdown(msg["content"])
                else:
                    with st.chat_message("assistant", avatar="🛡️"):
                        st.markdown("<div class='chat-name-bot'>Arın AI</div>", unsafe_allow_html=True)
                        st.markdown(msg["content"])

        user_q = st.chat_input("İSG mevzuatı veya geçmiş kazalar hakkında bir soru sorun...")
        
        if user_q:
            st.session_state.chat_history.append({"role": "user", "content": user_q})
            with chat_container:
                with st.chat_message("user", avatar="👤"):
                    st.markdown(f"<div class='chat-name-user'>Siz ({st.session_state.user_name})</div>", unsafe_allow_html=True)
                    st.markdown(user_q)
                with st.chat_message("assistant", avatar="🛡️"):
                    st.markdown("<div class='chat-name-bot'>Arın AI</div>", unsafe_allow_html=True)
                    with st.spinner("Sektörel veritabanları taranıyor..."):
                        if rag_engine:
                            cevap = rag_engine.soru_cevapla(user_q)
                            st.markdown(cevap)
                            st.session_state.chat_history.append({"role": "assistant", "content": cevap})
                        else:
                            st.error("RAG Motoru aktif değil.")

    # TAB 3: HAFIZA
    with tab_hafiza:
        st.subheader("🧠 Öğrenen Kurumsal Hafıza Veritabanı")
        hafiza_data = kurumsal_hafiza_getir()
        if not hafiza_data.empty: st.dataframe(hafiza_data, use_container_width=True)

    # TAB 4: SCADA / IoT
    with tab_scada:
        st.header("🔴 Canlı SCADA / IoT Sensör Paneli")
        c_scada1, c_scada2 = st.columns(2)
        with c_scada1:
            st.subheader("📊 Ortam & Gaz Sensörleri")
            if iot_data["ch4_percent"] > 1.5:
                st.markdown(f"<div class='sensor-critical'>🚨 <b>CH4 Metan Gazı: %{iot_data['ch4_percent']}</b><br>DURUM: KRİTİK / GRİZU RİSKİ</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='sensor-normal'>✅ <b>CH4 Metan Gazı: %{iot_data['ch4_percent']}</b><br>DURUM: Güvenli Limit</div>", unsafe_allow_html=True)
                
            if iot_data["co_ppm"] > 50:
                st.markdown(f"<div class='sensor-critical'>🚨 <b>CO Karbonmonoksit: {iot_data['co_ppm']} ppm</b><br>DURUM: TEHLİKELİ SIZINTI</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='sensor-normal'>✅ <b>CO Karbonmonoksit: {iot_data['co_ppm']} ppm</b><br>DURUM: Güvenli Limit</div>", unsafe_allow_html=True)

        with c_scada2:
            st.subheader(iot_data["scada_title"])
            st.write(f"**Ortam Sıcaklığı:** {iot_data['temp_c']} °C")
            st.write(f"**Nem Oranı:** %{iot_data['humidity']}")
            st.write(f"**Özel Parametre:** {iot_data['scada_detail']}")

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
            
            engellenen_kaza_maliyeti = yillik_dof_sayisi * ortalama_is_gunu_kaybi * gunluk_isgucu_maliyeti
            tazminat_tasarrufu = yillik_dof_sayisi * 85000 
            toplam_finansal_kazanc = engellenen_kaza_maliyeti + tazminat_tasarrufu
            yazilim_maliyeti = 450000 
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

# TAB 7: RİSK & FORMLAR
    with tab_engine:
        st.header("🧮 Risk Hesaplayıcıları & Form Hazırlayıcı")
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**5x5 L Tipi Risk Matrisi**")
            ihtimal_l = st.slider("İhtimal", 1, 5, 3, key="l_ihtimal")
            siddet_l = st.slider("Şiddet", 1, 5, 3, key="l_siddet")
            if st.button("L Tipi Skor Hesapla", type="primary", use_container_width=True):
                res = ISGRiskEngine.l_tipi_matris(ihtimal_l, siddet_l)
                st.metric("Risk Skoru", res["risk_skoru"], delta=res["kategori"])
                
        with c2:
            st.markdown("**Fine-Kinney Risk Skalası**")
            # Standart İSG Fine-Kinney Katsayıları
            fk_ihtimal_secim = st.selectbox("İhtimal (İ)", [
                (0.2, "0.2 - Pratik Olarak İmkânsız"),
                (0.5, "0.5 - Zayıf İhtimal"),
                (1.0, "1.0 - Beklenmeyen / Düşük"),
                (3.0, "3.0 - Mümkün / Nadir"),
                (6.0, "6.0 - Kuvvetle Muhtemel"),
                (10.0, "10.0 - Kaçınılmaz / Çok Yüksek")
            ], format_func=lambda x: x[1], index=3)
            
            fk_frekans_secim = st.selectbox("Frekans (F)", [
                (0.5, "0.5 - Çok Nadir (Yılda Bir)"),
                (1.0, "1.0 - Nadir (Yılda Birkaç)"),
                (2.0, "2.0 - Bazen (Ayda Bir)"),
                (3.0, "3.0 - Ara Sıra (Haftada Bir)"),
                (6.0, "6.0 - Sık (Günlük)"),
                (10.0, "10.0 - Sürekli / Kesintisiz")
            ], format_func=lambda x: x[1], index=4)
            
            fk_derece_secim = st.selectbox("Derece / Şiddet (D)", [
                (1.0, "1 - Hafif Yaralanma / İlk Yardım"),
                (3.0, "3 - Önemli Yaralanma / İş Günü Kaybı"),
                (7.0, "7 - Ciddi Yaralanma / Uzuv Kaybı"),
                (15.0, "15 - Çok Ciddi / Tekli Ölüm"),
                (40.0, "40 - Felaket / Birden Fazla Ölüm"),
                (100.0, "100 - Büyük Felaket / Çok Sayıda Ölüm")
            ], format_func=lambda x: x[1], index=2)
            
            if st.button("Fine-Kinney Skor Hesapla", type="primary", use_container_width=True):
                res_fk = ISGRiskEngine.fine_kinney(fk_ihtimal_secim[0], fk_frekans_secim[0], fk_derece_secim[0])
                st.metric("Risk Değeri (R = İ x F x D)", f"{res_fk['risk_degeri']} ({res_fk['durum_kodu']})", delta=res_fk['kategori'])
                
        st.markdown("---")
        
        st.subheader("📋 Resmi İSG Form Merkezi")
        secilen_form = st.selectbox("Belge Tipi:", [
            "Tehlike Bildirim Formu", 
            "İş Durdurma Tutanağı",
            "Ramak Kala Raporu",
            "Kök Neden Analizi (5 Neden)",
            "Günlük Saha Denetim Listesi"
        ])
        if st.button(f"✨ {secilen_form} Üret"):
            with st.spinner("Yapay Zeka Formu Dolduruyor..."):
                st.session_state[f"form_cache_{secilen_form}"] = form_doldur_llm(st.session_state.analiz_verisi, secilen_form)
        
        cache_key = f"form_cache_{secilen_form}"
        if cache_key in st.session_state: 
            st.markdown(st.session_state[cache_key])
            st.markdown("---")
            
            # PDF Çıktı Butonu
            pdf_data = rapor_pdf_olustur(st.session_state[cache_key])
            st.download_button(
                label="📄 PDF Olarak İndir",
                data=pdf_data,
                file_name=f"{secilen_form.replace(' ', '_').lower()}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        if st.button(f"✨ {secilen_form} Üret"):
            with st.spinner("Yapay Zeka Formu Dolduruyor..."):
                st.session_state[f"form_cache_{secilen_form}"] = form_doldur_llm(st.session_state.analiz_verisi, secilen_form)
        
        cache_key = f"form_cache_{secilen_form}"
        if cache_key in st.session_state: 
            st.markdown(st.session_state[cache_key])
            st.markdown("---")
            
            pdf_data = rapor_pdf_olustur(st.session_state[cache_key])
            st.download_button(
                label="📄 PDF Olarak İndir",
                data=pdf_data,
                file_name=f"{secilen_form.replace(' ', '_').lower()}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

    # TAB 8: GÖREV & KULLANICI YÖNETİMİ
    with tab_operations:
        st.subheader("📡 Canlı Operasyonel Görev Takip Panosu & Kullanıcı Yönetimi")
        sub_t1, sub_t2 = st.tabs(["📋 Canlı DÖF İş Emri Panosu", "👥 Kullanıcı Hesap Yönetimi"])
        
        with sub_t1:
            if st.session_state.canli_gorevler:
                st.dataframe(pd.DataFrame(st.session_state.canli_gorevler), use_container_width=True, hide_index=True)
        
        with sub_t2:
            st.dataframe(kullanici_listesi_getir(), use_container_width=True)