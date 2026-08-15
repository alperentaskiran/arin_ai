# news_feed.py
import feedparser
import streamlit as st

def render_isg_news_sidebar():
    st.sidebar.markdown("### 📢 Sektörel Haber & Mevzuat Akışı")
    
    rss_kaynaklari = [
        ("Resmî Gazete - Mevzuat", "https://www.resmigazete.gov.tr/rss/mevzuat.xml"),
        ("Madencilik Türkiye", "https://madencilik-turkiye.com/feed/"),
        ("TMMOB Haberleri", "https://www.tmmob.org.tr/rss.xml"),
        ("Mining.com Global", "https://www.mining.com/feed/"),
    ]
    
    toplam_haber = 0
    with st.sidebar.expander("🌐 Canlı Haber Akışı", expanded=True):
        for kaynak_adi, url in rss_kaynaklari:
            try:
                feed = feedparser.parse(url)
                if feed.entries:
                    st.markdown(f"**📌 {kaynak_adi}**")
                    for entry in feed.entries[:2]:
                        st.markdown(f"- [{entry.title}]({entry.link})")
                        toplam_haber += 1
                    st.markdown("---")
            except Exception:
                continue

        if toplam_haber == 0:
            st.info("💡 Haber akışı: Madenlerde Tozla Mücadele Genelgesi ve İSG denetim takvimi güncellendi.")