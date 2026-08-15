"""
Arın AI Enterprise - Akademi ve İSG Oyun Modülü
Aethel Technologies - 2026
"""

import streamlit as st
import random
import time

def init_game_states():
    # Oyun 1 State
    if "g1_scenario_idx" not in st.session_state: st.session_state.g1_scenario_idx = 0
    if "g1_answered" not in st.session_state: st.session_state.g1_answered = False
    if "g1_score" not in st.session_state: st.session_state.g1_score = 0
    
    # Oyun 2 State
    if "g2_q_idx" not in st.session_state: st.session_state.g2_q_idx = 0
    if "g2_score" not in st.session_state: st.session_state.g2_score = 0
    if "g2_answered" not in st.session_state: st.session_state.g2_answered = False
    
    # Oyun 3 State
    if "g3_analyzed" not in st.session_state: st.session_state.g3_analyzed = False

def render_games_tab():
    init_game_states()
    
    st.markdown("## 🎮 Arın AI İSG Akademi & Karar Simülasyonları")
    st.caption("Sahadaki reflekslerinizi, mevzuat bilginizi ve kök neden analiz yeteneğinizi yapay zekaya karşı test edin.")
    
    tab1, tab2, tab3 = st.tabs([
        "⚔️ Oyun 1: Arın AI vs. Mühendis", 
        "🧠 Oyun 2: İSG Terim Avcısı", 
        "🔍 Oyun 3: Kök Neden Dedektifi"
    ])
    
    # ==========================================
    # OYUN 1: ARIN AI VS MÜHENDİS (KRİZ DÜELLOSU)
    # ==========================================
    with tab1:
        st.subheader("⚔️ Taktiksel Karar Düellosu: Kriz Anı")
        st.markdown("**Oyun Mantığı:** Ekrana acil bir saha olayı gelir. Kendi aksiyonunuzu seçin ve Arın AI'ın resmi mevzuata dayalı kararıyla yüzleşin!")
        
        scenarios = [
            {
                "title": "🚨 Yeraltı Kömür: Ana Fan Durdu!",
                "desc": "-150 kotunda ana emici havalandırma fanı arızalandı. Arın sensörleri metan (CH4) seviyesinin %1.2'ye tırmandığını raporluyor. Galeride 18 personel çalışıyor.",
                "options": [
                    "Üretime devam et, tali fanları tam kapasite çalıştır ve personeli uyar.",
                    "Derhal elektrikleri kes, tüm personeli temiz hava yolundan tahliye et.",
                    "Sadece patlatma ekibini tahliye et, kazı ekibi çalışmaya devam etsin.",
                    "Metan %2'yi geçene kadar bekle, %2 olursa tahliye başlat."
                ],
                "correct_idx": 1,
                "ai_decision": "Maden İşyerlerinde İSG Yönetmeliği Madde 10 Uyarınca: Havalandırma durduğu anda ve CH4 %1'i aştığında patlayıcı ortam riski oluşur. Tesisin elektriği derhal kesilmeli (ex-proof acil aydınlatma hariç) ve personel tahliye edilmelidir.",
                "ai_score": 100
            },
            {
                "title": "⚠️ Mermer Ocağı: Tel Kesme Güvenliği",
                "desc": "Doğu aynasında elmas tel kesme makinesi çalışıyor. Operatör, telin bir miktar aşındığını fark etti ancak kesimin bitmesine 2 saat kaldı. Sipariş acil.",
                "options": [
                    "Kopma riskine karşı makineyi durdur ve teli hemen değiştir.",
                    "Kesim hızını ve su basıncını düşürerek işlemi tamamla.",
                    "Koruyucu kafes takılıysa aynen devam et, kafes korur.",
                    "İşçileri 10 metre uzağa alıp makineyi maksimum devirde çalıştır."
                ],
                "correct_idx": 0,
                "ai_decision": "ISO 45001 Proaktif Yaklaşım: 'Ramak kala' ve ekipman yorgunluğu göz ardı edilemez. Tel koptuğunda oluşan 'kırbaç etkisi' (whiplash) kafesleri bile parçalayabilir. Üretim baskısı, can güvenliğinin önüne geçemez. İşlem derhal durdurulup tel değiştirilmelidir.",
                "ai_score": 100
            }
        ]
        
        s = scenarios[st.session_state.g1_scenario_idx]
        
        with st.container(border=True):
            st.error(f"**VAKA:** {s['title']}")
            st.info(f"**DURUM:** {s['desc']}")
            
            if not st.session_state.g1_answered:
                selected_opt = st.radio("Saha Başmühendisi olarak aksiyonunuz nedir?", s["options"], index=None)
                if st.button("🚀 Kararımı Ver ve Arın AI ile Yüzleş", type="primary"):
                    if selected_opt:
                        st.session_state.g1_user_choice = s["options"].index(selected_opt)
                        st.session_state.g1_answered = True
                        st.rerun()
                    else:
                        st.warning("Lütfen bir aksiyon seçin!")
            
            if st.session_state.g1_answered:
                user_correct = (st.session_state.g1_user_choice == s["correct_idx"])
                
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("### 🧑‍💼 Senin Kararın")
                    st.write(f"*{s['options'][st.session_state.g1_user_choice]}*")
                    if user_correct:
                        st.success("✅ **Kusursuz Karar!** Reflekslerin mevzuatla tam uyumlu.")
                    else:
                        st.error("❌ **Hatalı Karar!** Bu aksiyon büyük bir faciaya yol açabilirdi.")
                
                with c2:
                    st.markdown("### 🛡️ Arın AI Kararı")
                    st.info(f"**Yapay Zeka Hükmü:**\n\n{s['ai_decision']}")
                    st.metric("Arın AI Uygunluk Skoru", f"%{s['ai_score']}")
                
                if st.button("Sonraki Vaka ⏭️"):
                    st.session_state.g1_scenario_idx = (st.session_state.g1_scenario_idx + 1) % len(scenarios)
                    st.session_state.g1_answered = False
                    st.rerun()

    # ==========================================
    # OYUN 2: İSG TERİM AVCISI
    # ==========================================
    with tab2:
        st.subheader("🧠 Bilgi Arenası: Jeoloji ve Mevzuat")
        
        questions = [
            {
                "q": "Oksijensiz ortamda kömürün yavaş yanması veya maden yangınları sonucu oluşan, halk arasında 'Sessiz Katil' olarak bilinen gaz hangisidir?",
                "opts": ["Hidrojen Sülfür (H2S)", "Karbonmonoksit (CO)", "Grizu (CH4 + Hava)", "Radon"],
                "ans": "Karbonmonoksit (CO)",
                "hint": "Renksiz, kokusuzdur ve kandaki hemoglobine oksijenden 200 kat daha hızlı bağlanır."
            },
            {
                "q": "Açık ocak madenciliğinde, iş makinelerinin çalıştığı ve cevher/dekapaj alımının yapıldığı basamaklı yüzeylere ne ad verilir?",
                "opts": ["Galeri", "Şev", "Ayna", "Nefeslik"],
                "ans": "Ayna",
                "hint": "Işığı yansıtan objeye de bu isim verilir."
            },
            {
                "q": "6331 sayılı İSG Kanununa göre, çok tehlikeli sınıfta yer alan maden işyerlerinde risk değerlendirmesi kaç yılda bir tamamen yenilenmelidir?",
                "opts": ["2 Yılda Bir", "4 Yılda Bir", "6 Yılda Bir", "Her Yıl"],
                "ans": "2 Yılda Bir",
                "hint": "En kısa süreli periyottur."
            }
        ]
        
        q = questions[st.session_state.g2_q_idx]
        
        st.markdown(f"**Soru {st.session_state.g2_q_idx + 1}/{len(questions)}:**")
        st.info(f"### {q['q']}")
        
        if not st.session_state.g2_answered:
            with st.expander("🤖 Arın AI'dan İpucu İste (Puan Kırılmaz)"):
                st.caption(f"_{q['hint']}_")
                
            ans_cols = st.columns(2)
            for i, opt in enumerate(q['opts']):
                with ans_cols[i % 2]:
                    if st.button(opt, use_container_width=True, key=f"q_{st.session_state.g2_q_idx}_opt_{i}"):
                        st.session_state.g2_user_ans = opt
                        st.session_state.g2_answered = True
                        st.rerun()
        else:
            if st.session_state.g2_user_ans == q['ans']:
                st.success(f"🎉 Doğru Cevap! ({q['ans']})")
                if "g2_score_counted" not in st.session_state:
                    st.session_state.g2_score += 10
                    st.session_state.g2_score_counted = True
            else:
                st.error(f"❌ Yanlış Cevap. Seçtiğin: {st.session_state.g2_user_ans} | Doğrusu: {q['ans']}")
                
            if st.button("Sıradaki Soru ➡️"):
                st.session_state.g2_q_idx = (st.session_state.g2_q_idx + 1) % len(questions)
                st.session_state.g2_answered = False
                if "g2_score_counted" in st.session_state: del st.session_state.g2_score_counted
                st.rerun()
                
        st.metric("Skorun", st.session_state.g2_score)

    # ==========================================
    # OYUN 3: KÖK NEDEN DEDEKTİFİ
    # ==========================================
    with tab3:
        st.subheader("🔍 Müfettiş Masası: Kök Neden Avı")
        st.markdown("**Vaka Özeti:** Yeraltı kömür ocağında bant konveyör motorunda yangın çıktı. Sensörler CO artışını fark etti ancak tahliye 15 dakika gecikti. Can kaybı yok ama 3 işçi gazdan etkilendi.")
        
        st.markdown("Aşağıdaki **5 İnceleme Bulgusu'ndan** sence bu kazanın asıl **Kök Nedenlerini (Root Cause)** seç:")
        
        clues = {
            "Bant sensör kalibrasyonlarının 3 aydır yapılmamış olması": True,
            "İşçilerin bant motoru yakınında yanıcı atık (yağlı üstüpü) bırakması": True,
            "Tahliye sireninin hoparlör kablosunun bant sürtünmesiyle kopmuş olması": True,
            "İşçilerin kişisel gaz maskesi takmayı unutması": False, # Maske takmamak kök neden değil, sonuçtur
            "Oksijen ferdi kurtarıcılarının (OFK) ağır olması": False # Bahane, kök neden değil
        }
        
        selected_clues = st.multiselect("Kazanın Kök Nedenleri Nelerdir? (Çoklu Seçim Yapabilirsiniz)", list(clues.keys()))
        
        if st.button("Bilirkişi (Arın AI) Raporunu Onayla", type="primary"):
            st.session_state.g3_analyzed = True
            
        if st.session_state.g3_analyzed:
            st.markdown("---")
            st.markdown("### ⚖️ Arın AI Bilirkişi Hükmü")
            
            dogrular = [k for k, v in clues.items() if v]
            yanlislar = [k for k, v in clues.items() if not v]
            
            score = 0
            for sc in selected_clues:
                if sc in dogrular:
                    score += 1
                else:
                    score -= 1
                    
            if score == len(dogrular):
                st.success("🏆 Mükemmel Analiz! Kazanın arkasındaki gerçek yapısal/sistemsel sorunları nokta atışı buldun.")
            elif score > 0:
                st.warning("⚠️ Kısmen Doğru. İşçiyi suçlamak (maske takmamak) yerine sistemin neden alarm vermediğine (sensör/kablo) odaklanmalıyız. İSG'de insan hatası kök neden sayılmaz, sistemin bunu engelleyememesi kök nedendir.")
            else:
                st.error("🚨 Zayıf Analiz. Kök neden teorisinde asıl olay, yüzeydeki 'işçi unuttu' bahanesinin altındaki 'Sistem neden izin verdi?' sorusudur.")
                
            with st.expander("Resmi Kök Neden Raporunu Gör (Arın AI)"):
                st.markdown("""
                **Gerçek Kök Nedenler (Root Causes):**
                1. **Sensör Bakım İhmali:** Sistem yangını geç algıladı.
                2. **5S ve Tertip Düzen Eksikliği:** Bant çevresinde yanıcı madde bırakılması yangın yükünü artırdı.
                3. **Kablo Tesisat Hatası:** Siren kablolarının mekanik aşınmaya (bant sürtünmesi) maruz kalacak şekilde korunmasız çekilmesi tahliyeyi engelledi.
                """)
            
            if st.button("Dedektiflik Dosyasını Sıfırla"):
                st.session_state.g3_analyzed = False
                st.rerun()