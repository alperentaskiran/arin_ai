import math
from typing import Dict, Any, List

class ISGRiskEngine:
    """
    Arın AI - İSG Deterministik Risk Hesaplama ve Fiziksel Etken Motoru
    """

    @staticmethod
    def l_tipi_matris(ihtimal: int, siddet: int) -> Dict[str, Any]:
        """
        5x5 L Tipi Risk Matrisi (Olasılık x Şiddet) hesaplar.
        """
        if not (1 <= ihtimal <= 5 and 1 <= siddet <= 5):
            return {"error": "İhtimal ve Şiddet değerleri 1 ile 5 arasında olmalıdır."}

        skor = ihtimal * siddet

        if skor == 1:
            kategori, renk = "Önemsiz Risk", "Mavi"
            eylem = "İhmal edilebilir. Mevcut önlemler sürdürülebilir."
        elif 2 <= skor <= 6:
            kategori, renk = "Düşük / Katlanılabilir Risk", "Yeşil"
            eylem = "Acil tedbir gerekmeyebilir. Belirlenen önlemler takibe alınmalı."
        elif 8 <= skor <= 12:
            kategori, renk = "Orta Düzeyde Risk", "Sarı"
            eylem = "Eylem planına alınmalı, kontrol önlemleri gözden geçirilmeli."
        elif 15 <= skor <= 20:
            kategori, renk = "Önemli / Yüksek Risk", "Turuncu"
            eylem = "Kısa vadeli eylem planı hazırlanmalı, risk düşürülene kadar önlem alınmalı."
        else:
            kategori, renk = "Katlanılamaz / Tolere Edilemez Risk", "Kırmızı"
            eylem = "ÇALIŞMAYA DERHAL ARA VERİLMELİ! Risk kabul edilebilir seviyeye çekilmeden işe başlanamaz."

        return {
            "metot": "L Tipi (5x5) Matris",
            "ihtimal": ihtimal,
            "siddet": siddet,
            "risk_skoru": skor,
            "kategori": kategori,
            "renk_kodu": renk,
            "onerilen_eylem": eylem
        }

    @staticmethod
    def fine_kinney(ihtimal: float, frekans: float, derece: float) -> Dict[str, Any]:
        """
        Fine-Kinney Yöntemi (Risk = İhtimal x Frekans x Derece) hesaplar.
        """
        risk_degeri = ihtimal * frekans * derece

        if risk_degeri < 20:
            kategori, eylem, durum = "Kabul Edilebilir Risk", "Acil tedbir gerekmeyebilir.", "NORMAL"
        elif 20 <= risk_degeri < 70:
            kategori, eylem, durum = "Kesin Risk", "Eylem planına alınmalı.", "TAKİP"
        elif 70 <= risk_degeri < 200:
            kategori, eylem, durum = "Önemli Risk", "Dikkatle izlenmeli ve yıllık eylem planına alınarak giderilmeli.", "ÖNEMLİ"
        elif 200 <= risk_degeri < 400:
            kategori, eylem, durum = "Yüksek Risk", "Kısa vadeli eylem planına alınarak hızla giderilmeli.", "ACİL"
        else:
            kategori, eylem, durum = "Çok Yüksek Risk", "ÇALIŞMAYA DERHAL ARA VERİLMELİ! Derhal tedbir alınmalı.", "TEHLİKE"

        return {
            "metot": "Fine-Kinney",
            "ihtimal": ihtimal,
            "frekans": frekans,
            "derece": derece,
            "risk_degeri": round(risk_degeri, 2),
            "kategori": kategori,
            "durum_kodu": durum,
            "onerilen_eylem": eylem
        }

    @staticmethod
    def gurultu_logaritmik_toplam(db_degerleri: List[float]) -> Dict[str, Any]:
        """
        Sahadaki birden fazla gürültü kaynağının desibel (dB) cinsinden logaritmik toplamını hesaplar.
        """
        if not db_degerleri:
            return {"toplam_db": 0}

        toplam = 10 * math.log10(sum(10 ** (db / 10) for db in db_degerleri))
        toplam_db = round(toplam, 1)

        if toplam_db >= 115:
            uyari = "KRİTİK: 115 dB(A) üzerinde kesinlikle çalışılamaz!"
        elif toplam_db >= 85:
            uyari = "UYARI: 85 dB(A) eşiği aşıldı! 8 saatlik maruziyet sınırı, KKD kullanımı zorunlu."
        elif toplam_db >= 80:
            uyari = "BİLGİ: 80 dB(A) en düşük maruziyet etkin değeri, KKD hazır bulundurulmalı."
        else:
            uyari = "Normal çalışma seviyesi."

        return {
            "olculen_degerler": db_degerleri,
            "toplam_gurultu_db": toplam_db,
            "mevzuat_durumu": uyari,
            "yukumluluk_suresi": "6 Ay (Gürültülü işte en az 2 yıl, 85 dB üzerinde en az 30 gün çalışılmış olmalı)"
        }


# --- OPENAI / AGENT TOOL DEFINITIONS ---
# Ajanın hangi fonksiyonu ne zaman çağıracağını anlaması için şemalar:

ARIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "l_tipi_matris",
            "description": "5x5 L tipi risk matrisi hesabı yapar. İhtimal ve şiddet değerleri verilmelidir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ihtimal": {"type": "integer", "description": "1-5 arası ihtimal değeri"},
                    "siddet": {"type": "integer", "description": "1-5 arası şiddet/sonuç değeri"}
                },
                "required": ["ihtimal", "siddet"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fine_kinney",
            "description": "Fine-Kinney metoduna göre risk hesabı yapar (Risk = İhtimal x Frekans x Derece).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ihtimal": {"type": "number", "description": "İhtimal skalası değeri (0.1 - 10)"},
                    "frekans": {"type": "number", "description": "Frekans skalası değeri (0.5 - 10)"},
                    "derece": {"type": "number", "description": "Derece/Şiddet skalası değeri (1 - 100)"}
                },
                "required": ["ihtimal", "frekans", "derece"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gurultu_logaritmik_toplam",
            "description": "Birden fazla gürültü kaynağının desibel (dB) değerlerini logaritmik olarak toplar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "db_degerleri": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Ölçülen dB değerlerinin listesi (örn: [100, 100])"
                    }
                },
                "required": ["db_degerleri"]
            }
        }
    }
]