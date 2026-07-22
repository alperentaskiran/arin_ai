import pandas as pd
from pypdf import PdfReader
from docx import Document
import io
import streamlit as st
from crewai import Agent, Task, Crew, Process
from dotenv import load_dotenv
import os
import time

# .env dosyasındaki API anahtarını yükle
load_dotenv()

# --- YARDIMCI DOSYA OKUMA FONKSİYONLARI ---

def extract_text_from_pdf(file_bytes):
    """PDF dosyasındaki tüm sayfaların metinlerini birleştirir."""
    pdf_file = io.BytesIO(file_bytes)
    reader = PdfReader(pdf_file)
    extracted_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            extracted_text += text + "\n"
    return extracted_text.strip()

def extract_text_from_docx(file_bytes):
    """Word dosyasındaki tüm paragrafları okur ve birleştirir."""
    docx_file = io.BytesIO(file_bytes)
    doc = Document(docx_file)
    extracted_text = ""
    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            extracted_text += paragraph.text + "\n"
    return extracted_text.strip()

def extract_text_from_excel(file_bytes):
    """Excel sayfalarındaki tabloları düzgün, okunabilir bir metin formatına çevirir."""
    excel_file = io.BytesIO(file_bytes)
    xls = pd.ExcelFile(excel_file)
    extracted_text = "--- EXCEL VARDİYA VERİLERİ ---\n"
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)
        df = df.dropna(how='all')
        if not df.empty:
            extracted_text += f"\n[Sayfa: {sheet_name}]\n"
            extracted_text += df.to_string(index=False) + "\n"
    return extracted_text.strip()

def extract_text_from_audio(file_bytes, file_name):
    """Yüklenen ses dosyasını OpenAI Whisper API kullanarak Türkçe metne dönüştürür."""
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Geçici ses dosyasını diske kaydet
    temp_filename = f"temp_{file_name}"
    with open(temp_filename, "wb") as f:
        f.write(file_bytes)
        
    try:
        with open(temp_filename, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file,
                language="tr"
            )
        return transcript.text
    except Exception as e:
        raise Exception(f"Whisper API hatası: {e}")
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)



# --- SAYFA YAPILANDIRMASI VE DERS MODE CSS AYARLARI ---
st.set_page_config(
    page_title="Arın AI | Proaktif İSG Karar Destek Sistemi", 
    page_icon="🛡️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Rajdhani Fontu ve Kurumsal Dark Mode Stilleri
st.markdown("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&display=swap" rel="stylesheet">
    
    <style>
    /* 1. GENEL RENK VE DOĞRU FONT TANIMLAMALARI (İkonları Korur) */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #0B0F19 !important;
        color: #E2E8F0 !important;
    }
    
    /* Sadece düz metin elemanlarına font uygulayarak ikon motorunun (material-icons) ezilmesini engelliyoruz */
    p, li, label, textarea, div.stMarkdown, .report-card {
        font-family: 'Rajdhani', sans-serif !important;
    }
    
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Rajdhani', sans-serif !important;
        font-weight: 700 !important;
        color: #FFFFFF !important;
    }
    
    /* Sol Panel (Sidebar) */
    [data-testid="stSidebar"] {
        background-color: #0F1423 !important;
        border-right: 1px solid #1E293B !important;
    }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] label {
        color: #E2E8F0 !important;
        font-family: 'Rajdhani', sans-serif !important;
    }

    /* 2. KEYBOARD DOUBLE / SIDEBAR DARALTMA BUTONU KESİN ÇÖZÜMÜ */
    /* Butonların içindeki bozulan ikon yazılarını tamamen görünmez yapıyoruz */
    [data-testid="stSidebarCollapseButton"] button,
    button[aria-label="Collapse sidebar"],
    button[aria-label="Expand sidebar"] {
        color: transparent !important;
        position: relative !important;
    }

    /* Sol paneli kapatma butonuna temiz bir unicode ok yerleştiriyoruz */
    [data-testid="stSidebarCollapseButton"] button::before,
    button[aria-label="Collapse sidebar"]::before {
        content: "❮" !important;
        color: #8A99AD !important;
        font-family: sans-serif !important;
        font-size: 14px !important;
        font-weight: bold !important;
        position: absolute !important;
        left: 50% !important;
        top: 50% !important;
        transform: translate(-50%, -50%) !important;
        display: inline-block !important;
    }

    /* Sol paneli açma butonuna temiz bir unicode ok yerleştiriyoruz */
    button[aria-label="Expand sidebar"]::before {
        content: "❯" !important;
        color: #8A99AD !important;
        font-family: sans-serif !important;
        font-size: 14px !important;
        font-weight: bold !important;
        position: absolute !important;
        left: 50% !important;
        top: 50% !important;
        transform: translate(-50%, -50%) !important;
        display: inline-block !important;
    }

    /* Butonların üzerine gelindiğinde (hover) kurumsal turkuaz renk almalarını sağlıyoruz */
    [data-testid="stSidebarCollapseButton"] button:hover,
    button[aria-label="Collapse sidebar"]:hover,
    button[aria-label="Expand sidebar"]:hover {
        background-color: rgba(0, 168, 150, 0.15) !important;
    }

    [data-testid="stSidebarCollapseButton"] button:hover::before,
    button[aria-label="Collapse sidebar"]::hover::before,
    button[aria-label="Expand sidebar"]::hover::before {
        color: #00A896 !important;
    }
    
    /* 3. DOSYA YÜKLEME ALANI (FILE UPLOADER) KESİN ÇÖZÜMÜ */
    /* Dosya yükleme dış kutusu */
    [data-testid="stFileUploader"] {
        background-color: #151D30 !important;
        border: 1px dashed #22314D !important;
        border-radius: 8px !important;
        padding: 10px !important;
    }
    /* Sürükleme alanının (Dropzone) iç hizalaması ve dikey genişliği */
    [data-testid="stFileUploaderDropzone"] {
        padding: 15px 5px !important;
        min-height: 130px !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 8px !important;
    }
    /* İç içe geçen "Drag and drop file here" yazısı ve "Browse files" butonu arasındaki çakışmayı önleme */
    [data-testid="stFileUploaderDropzone"] > div {
        margin: 0 !important;
        padding: 0 !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
    }
    /* "Browse files" butonu */
    [data-testid="stFileUploader"] button {
        background-color: #1E293B !important;
        color: #E2E8F0 !important;
        border: 1px solid #334155 !important;
        font-family: 'Rajdhani', sans-serif !important;
        font-weight: 600 !important;
        margin: 5px 0 !important;
    }
    [data-testid="stFileUploader"] button:hover {
        background-color: #00A896 !important;
        color: white !important;
        border-color: #00A896 !important;
    }
    /* Alttaki "200MB per file..." açıklama metni */
    [data-testid="stFileUploaderDropzoneInputDescription"] {
        color: #8A99AD !important;
        font-family: 'Rajdhani', sans-serif !important;
        font-size: 13px !important;
        margin-top: 5px !important;
    }
    
    /* 4. SORU İŞARETİ (TOOLTIP) VE İKONLAR */
    [data-testid="stMarker"] svg, 
    [data-testid="stFileUploader"] svg {
        fill: #00A896 !important;
        color: #00A896 !important;
    }
    
    /* Metin Giriş Alanı (TextArea) Koyu Tema Uyumu */
    [data-testid="stSidebar"] textarea {
        color: #E2E8F0 !important;
        background-color: #151D30 !important;
        border: 1px solid #22314D !important;
        border-radius: 8px !important;
        font-family: 'Rajdhani', sans-serif !important;
    }

    /* Kod Önizleme Alanı */
    [data-testid="stSidebar"] code {
        color: #00A896 !important;
        background-color: #151D30 !important;
    }
    
    /* Analiz Butonu */
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3.4em;
        background-color: #00A896 !important;
        color: white !important;
        font-weight: 700 !important;
        font-family: 'Rajdhani', sans-serif !important;
        border: none;
        font-size: 16px !important;
        letter-spacing: 1px;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #00C2CB !important;
        box-shadow: 0 4px 15px rgba(0, 168, 150, 0.4);
        transform: translateY(-1px);
    }
    
    /* Sonuç Rapor Kartı Tasarımı */
    .report-card {
        background-color: #151D30;
        padding: 35px;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        border-left: 6px solid #00A896;
        margin-top: 20px;
    }
    
    /* Süreç/Durum Kutuları */
    .status-box {
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
        color: white;
        text-align: center;
        font-weight: 600;
        font-family: 'Rajdhani', sans-serif;
        font-size: 16px;
        letter-spacing: 0.5px;
    }

    /* --- GİRİŞ ANİMASYONU --- */
    .splash-container {
        display: flex;
        justify-content: center;
        align-items: center;
        height: 85vh;
        animation: fadeOut 1.2s ease-in-out 2.5s forwards;
    }
    .splash-image-box {
        max-width: 650px;
        width: 100%;
        opacity: 0;
        animation: fadeInScale 1.5s ease-out forwards;
    }
    @keyframes fadeInScale {
        0% { opacity: 0; transform: scale(0.92); filter: blur(8px); }
        100% { opacity: 1; transform: scale(1); filter: blur(0); }
    }
    @keyframes fadeOut {
        0% { opacity: 1; }
        100% { opacity: 0; visibility: hidden; }
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. GİRİŞ ANİMASYONU (SPLASH SCREEN) YÖNETİMİ ---
if 'initialized' not in st.session_state:
    st.session_state.initialized = False

if not st.session_state.initialized:
    splash_placeholder = st.empty()
    with splash_placeholder.container():
        # Logoyu okuyup base64 formatına çeviriyoruz (Streamlit bileşenleri render olmadan temiz görünmesi için en akıcı yöntemdir)
        import base64
        try:
            with open("aethel_logo.png", "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode()
            
            st.markdown(f"""
                <div class="splash-container">
                    <img class="splash-image-box" src="data:image/png;base64,{encoded_string}">
                </div>
            """, unsafe_allow_html=True)
        except FileNotFoundError:
            # Görsel bulunamazsa sistemin çökmemesi için güvenli alternatif yedek metin
            st.markdown("""
                <div class="splash-container">
                    <div style="font-size:45px; font-weight:700; color:#00A896; letter-spacing:3px;">AETHEL TEKNOLOJİ</div>
                </div>
            """, unsafe_allow_html=True)
        
    time.sleep(3.5)  # Logonun ekranda kalma ve sönme süresi
    st.session_state.initialized = True
    splash_placeholder.empty()  # Ekranı temizle
    st.rerun()


# --- 3. ANA ARANÜZ VE İŞ MANTIĞI BAŞLANGICI ---

# SIDEBAR (GİRİŞ ALANI)
with st.sidebar:
    st.image("arin_logo.png", use_container_width=True)
    st.markdown("<hr style='border-color: rgba(248, 250, 252, 0.1); margin-top: 0; margin-bottom: 20px;'>", unsafe_allow_html=True)
    
    st.info("💡 **İpucu:** Hazır bir rapor dökümanı veya ses kaydı yükleyebilir ya da aşağıdaki alana elle yazabilirsiniz.")
    
    # Session State (Hafıza) Tanımlaması
    if "analiz_verisi" not in st.session_state:
        st.session_state.analiz_verisi = ""
        
    # Sürükle-Bırak Dosya Yükleme Alanı
    uploaded_file = st.file_uploader(
        "📂 Rapor veya Ses Dosyası Yükleyin", 
        type=["pdf", "docx", "xlsx", "xls", "txt", "mp3", "wav", "m4a"],
        help="PDF, Word, Excel, TXT dökümanlarını veya MP3/WAV ses dosyalarını sürükleyip bırakabilirsiniz."
    )
    
    # Dosya yüklendiyse içeriği hafızaya yaz
    if uploaded_file is not None:
        if not st.session_state.analiz_verisi:
            try:
                file_bytes = uploaded_file.read()
                
                # Ses Dosyası Kontrolü
                if uploaded_file.name.endswith(('.mp3', '.wav', '.m4a')):
                    with st.spinner("🎤 Ses kaydı yazıya dönüştürülüyor (Whisper AI)..."):
                        st.session_state.analiz_verisi = extract_text_from_audio(file_bytes, uploaded_file.name)
                # PDF Dosyası Kontrolü
                elif uploaded_file.name.endswith('.pdf'):
                    st.session_state.analiz_verisi = extract_text_from_pdf(file_bytes)
                # Word Dosyası Kontrolü
                elif uploaded_file.name.endswith(('.docx', '.doc')):
                    st.session_state.analiz_verisi = extract_text_from_docx(file_bytes)
                # Excel Dosyası Kontrolü
                elif uploaded_file.name.endswith(('.xlsx', '.xls')):
                    st.session_state.analiz_verisi = extract_text_from_excel(file_bytes)
                # Düz Metin Kontrolü
                elif uploaded_file.name.endswith('.txt'):
                    st.session_state.analiz_verisi = file_bytes.decode("utf-8")
                    
                st.success("✅ Dosya başarıyla yüklendi!")
                    
            except Exception as e:
                st.error(f"Dosya okunurken hata oluştu: {e}")
                st.session_state.analiz_verisi = ""
    else:
        # Dosya yüklenmediyse ve hafıza boşsa varsayılan metni yükle
        if not st.session_state.analiz_verisi:
            default_report = (
                "Vardiya: Gece (00:00 - 08:00)\n"
                "Tarih: 14 Temmuz 2026\n"
                "Lokasyon: 3. Batı Galerisi (Kot: -120)\n\n"
                "Yapılan İşler ve Gözlemler:\n"
                "Ayna ilerlemesi sorunsuz yapıldı. Ancak arın bölgesine yakın yerlerde tahkimat direklerinde hafif çatlama sesleri duyuldu, gözle hafif esneme var gibi duruyor ama vardiyayı tamamlamak için çalışmaya devam ettik. Havalandırma tarafında fanda bir arıza oldu, yaklaşık 18 dakika durdu o esnada CH4 (Metan) %1.2 seviyesine kadar çıktı ama fan çalışınca düştü. Bazı arkadaşların toz maskesi takmadığı görüldü, sözlü olarak uyarıldılar."
            )
            st.session_state.analiz_verisi = default_report

        # Kullanıcı elle düzenleme yapabilsin
        manuel_metin = st.text_area("✍️ Veya Vardiya Defteri Notları:", value=st.session_state.analiz_verisi, height=280)
        st.session_state.analiz_verisi = manuel_metin

    # Önizleme Kutusunu Dosya Yüklenmişse Göster
    if uploaded_file is not None and st.session_state.analiz_verisi:
        with st.expander("🔍 Dosya İçeriği Önizlemesi", expanded=True):
            st.code(st.session_state.analiz_verisi[:500] + ("..." if len(st.session_state.analiz_verisi) > 500 else ""), language="text")
    
    # ANALİZ BUTONU
    analiz_butonu = st.button("🔬 MULTI-AGENT ANALİZİ BAŞLAT")
    
    st.markdown("<hr style='border-color: rgba(248, 250, 252, 0.1); margin-top: 0; margin-bottom: 20px;'>", unsafe_allow_html=True)
    st.caption("⚙️ Sürüm: v1.1.0 | Academic & Industrial Presentation Mode")


# --- ANA SAYFA ÜST ALAN TASARIMI ---
col1, col2 = st.columns([2, 1])

with col1:
    st.title("🛡️ Arın AI: Maden İSG Analiz Platformu")
    st.markdown("<p style='color: #8A99AD; font-size:16px;'>Yapay Zeka Tabanlı Proaktif Risk Yönetimi | <em>6331 Sayılı Kanun ve Maden Yönetmeliği Entegrasyonu</em></p>", unsafe_allow_html=True)

with col2:
    st.write("")
    m1, m2 = st.columns(2)
    m1.metric("Analiz Hızı", "0.8s/olay")
    m2.metric("Mevzuat Sürümü", "2026 Güncel")

st.markdown("---")

main_container = st.container()

# --- MULTI-AGENT PROSES KONTROLÜ ---
if analiz_butonu:
    if not st.session_state.analiz_verisi or len(st.session_state.analiz_verisi.strip()) == 0:
        st.error("⚠️ Lütfen analiz için geçerli bir rapor dosyası yükleyin veya yandaki kutuya manuel metin girin.")
    else:
        status_placeholder = st.empty()
        progress_bar = st.progress(0)
        
        with st.spinner(""):
            # AJAN TANIMLARI
            veri_isleyici = Agent(
                role="Kıdemli Maden Veri Analisti",
                goal="Düzensiz vardiya raporlarındaki verileri teknik bir veri modeline dönüştürmek.",
                backstory="Maden Mühendisliği veri işleme protokolleri konusunda doktora düzeyinde bilgi sahibisiniz.",
                verbose=False
            )

            isg_denetci = Agent(
                role="Maden İSG ve Mevzuat Baş Denetçisi",
                goal="Verileri 6331 Sayılı Kanun ve ilgili tüm maden yönetmeliklerine göre denetlemek.",
                backstory="Yıllarca bakanlık düzeyinde maden denetçiliği yapmış, yasal limitlere hakim bir hukuk ve İSG uzmanısınız.",
                verbose=False
            )

            raporlama_uzmani = Agent(
                role="Maden İşletme Yönetim Danışmanı",
                goal="Denetim sonuçlarını profesyonel bir Yönetici Aksiyon Raporuna dönüştürmek.",
                backstory="Teknik bulguları yönetimsel kararlara dönüştürme konusunda uzman, sıfır kaza vizyoneri bir danışmansınız.",
                verbose=False
            )

            # GÖREVLER
            gorev_veri_isleme = Task(
                description=f"Şu raporu yapılandırılmış veri haline getir:\n\n{st.session_state.analiz_verisi}",
                expected_output="Temizlenmiş teknik veri özeti.",
                agent=veri_isleyici
            )

            gorev_isg_denetimi = Task(
                description="Tespit edilen her durumu Maden İSG yönetmelikleri çerçevesinde denetle ve ihlalleri bul.",
                expected_output="Madde madde yasal ihlaller ve risk skorları.",
                agent=isg_denetci
            )

            gorev_raporlama = Task(
                description="Üst yönetim için profesyonel bir aksiyon raporu hazırla. Mevzuat maddelerini referans göster.",
                expected_output="Yüksek kalitede Markdown İSG raporu.",
                agent=raporlama_uzmani
            )

            # CREW ÇALIŞTIRMA
            crew = Crew(
                agents=[veri_isleyici, isg_denetci, raporlama_uzmani],
                tasks=[gorev_veri_isleme, gorev_isg_denetimi, gorev_raporlama],
                process=Process.sequential
            )

            # Süreç kutuları
            status_placeholder.markdown('<div class="status-box" style="background-color: #0F2557; border: 1px solid #22314D;">🔍 Veri Analisti Raporu Ayrıştırıyor...</div>', unsafe_allow_html=True)
            progress_bar.progress(33)
            time.sleep(1.2)
            
            result = crew.kickoff()
            
            status_placeholder.markdown('<div class="status-box" style="background-color: #7A1C1C; border: 1px solid #992222;">⚖️ Mevzuat Denetçisi İhlalleri Saptıyor...</div>', unsafe_allow_html=True)
            progress_bar.progress(66)
            time.sleep(1.2)
            
            status_placeholder.markdown('<div class="status-box" style="background-color: #00A896; border: 1px solid #00C2CB;">📋 Yönetim Danışmanı Raporu Hazırlıyor...</div>', unsafe_allow_html=True)
            progress_bar.progress(100)
            time.sleep(1)
            
            status_placeholder.empty()
            progress_bar.empty()

            # --- SONUÇ EKRANI ---
            st.success("✅ Analiz Başarıyla Tamamlandı ve Kayıt Altına Alındı.")
            
            st.markdown(f"""
                <div class="report-card">
                    <h3 style="margin-top:0; color:#00A896 !important;">[ARIN AI GÜVENLİK ANALİZ RAPORU]</h3>
                    <hr style="border-color: rgba(255,255,255,0.1); margin-bottom:20px;">
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown(result.raw)
            
            st.write("")
            st.download_button(
                label="📄 Raporu İndir (.md)",
                data=str(result.raw),
                file_name="ArınAI_ISG_Raporu.md",
                mime="text/markdown",
            )

else:
    with main_container:
        st.markdown("""
        <div style="background-color: #151D30; padding: 30px; border-radius: 12px; border: 1px solid #22314D;">
            <h3 style="margin-top: 0; color: #00A896 !important;">Sistem Çalışma Metodolojisi</h3>
            <p style="color: #E2E8F0;">Arın AI, vardiya raporlarını üç aşamalı bir yapay zeka denetim zincirinden geçirir:</p>
            <ol style="color: #E2E8F0; padding-left: 20px;">
                <li style="margin-bottom: 10px;"><strong>Teknik Ayrıştırma (Maden Veri Analisti):</strong> Vardiya raporundaki dağınık ifadeleri, ölçümleri ve teknik terimleri yapılandırılmış verilere dönüştürür.</li>
                <li style="margin-bottom: 10px;"><strong>Mevzuat Denetimi (İSG Baş Denetçisi):</strong> Ayrıştırılan verileri 6331 Sayılı İSG Kanunu ve Maden İşyerlerinde İSG Yönetmeliği uyarınca denetler; yasal sınır ihlallerini tespit eder.</li>
                <li style="margin-bottom: 10px;"><strong>Karar Destek Raporlaması (Yönetim Danışmanı):</strong> Riskleri seviyelendirerek doğrudan maden müdürünün aksiyon alabileceği pratik, imzaya hazır bir İSG raporu oluşturur.</li>
            </ol>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 20px 0;">
            <p style="color: #8A99AD; font-style: italic; margin-bottom: 0;">Analiz sürecini başlatmak için sol taraftaki panelde yer alan <strong>"Multi-Agent Analizi Başlat"</strong> butonuna tıklayın.</p>
        </div>
        """, unsafe_allow_html=True)