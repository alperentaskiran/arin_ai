import os
from openai import OpenAI

class LLMService:
    def __init__(self):
        # OpenAI API Anahtarını işletim sistemi çevre değişkenlerinden alıyoruz
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY bulunamadı! Lütfen terminalde veya .env dosyasında API anahtarınızı tanımlayın."
            )
        self.client = OpenAI(api_key=api_key)
        # Kararlı, hızlı ve yapılandırılmış çıktı yeteneği yüksek olan gpt-4o-mini modelini kullanıyoruz
        self.model = "gpt-4o-mini"

    def generate_response(self, user_query: str, reference_docs: list) -> str:
        """
        Kullanıcı sorgusunu ve RAG'den gelen referans belgeleri birleştirerek 
        proaktif bir İSG analiz raporu oluşturur.
        """
        
        # 1. Referans Belgeleri Prompt İçin Metin Haline Getiriyoruz
        context_text = ""
        for i, doc in enumerate(reference_docs, 1):
            source_type = doc['source_type'].upper()
            context_text += f"\n--- REFERANS BELGE {i} ({source_type}) ---\n"
            context_text += f"Başlık: {doc['title']}\n"
            context_text += f"İçerik: {doc['content']}\n"
        
        # 2. Kurumsal ve Kesin Direktifler İçeren Sistem Talimatı (System Prompt)
        system_prompt = (
            "Sen, Aethel Technologies tarafından geliştirilen 'Arın AI' adında, "
            "maden sektörüne yönelik proaktif bir İş Sağlığı ve Güvenliği (İSG) Karar Destek Yapay Zekasısın.\n\n"
            "GÖREVİN:\n"
            "Kullanıcının sorduğu soruya veya kaza senaryosuna, sana aşağıda sağlanan 'REFERANS BELGELER' "
            "ışığında, son derece profesyonel, teknik ve akademik düzeyde bir analiz raporu hazırlamaktır.\n\n"
            "ANALİZ RAPORU KURALLARI:\n"
            "1. Yanıtını doğrudan profesyonel bir rapor formatında sun (Başlıklar, Önemli Uyarılar, Risk Değerlendirmesi vb.).\n"
            "2. Sana verilen mevzuat maddelerini ve kaza raporu referanslarını doğrudan kullan. Maddelere atıfta bulunurken "
            "kanun/yönetmelik isimlerini ve başlıklarını net belirt.\n"
            "3. Eğer kullanıcı bir risk veya senaryo soruyorsa, proaktif (önleyici) aksiyonları net bir liste halinde sun.\n"
            "4. Asla genel geçer, yuvarlak cümleler kurma; teknik limitleri (örneğin havalandırma hız limitleri, tahkimat sıklıkları vb.) "
            "ve resmi prosedürleri temel al.\n"
            "5. Tonun her zaman kurumsal, ciddi, yapıcı ve güven verici olmalıdır.\n"
            "6. Kaynaklarda yazmayan hiçbir bilgiyi 'kesin yasal zorunluluktur' şeklinde uydurma (halüsinasyon görme).\n"
            "7. KESİNTİ ÖNLEME KURALI: Ürettiğin raporun, tabloların veya listelerin yarım kalmamasına dikkat et. "
            "Cümleleri ve Markdown yapılarını (tablo çizgileri dahil) mutlaka kapatarak yanıtı düzgün bir şekilde sonlandır.\n"
        )

        # 3. Kullanıcıya Gönderilecek Mesaj İçeriği
        user_content = (
            f"KULLANICI SORGUSU: {user_query}\n\n"
            f"Sistem tarafından yerel veri tabanından çekilen en alakalı kaynaklar:\n"
            f"{context_text}\n"
            "Lütfen yukarıdaki kaynakları baz alarak kullanıcı sorgusuna yönelik detaylı ve proaktif İSG analiz raporunu oluştur."
        )

        try:
            # OpenAI API Çağrısı
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.3, # Daha kararlı, tutarlı ve teknik yanıtlar için düşük sıcaklık
                max_tokens=3500  # Çıktının kesilmesini önlemek için maksimum token limiti artırıldı
            )
            return response.choices[0].message.content
            
        except Exception as e:
            return f"❌ OpenAI API entegrasyonunda bir hata oluştu: {str(e)}"