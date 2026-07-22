from pydantic import BaseModel
from typing import List, Optional

class ISGChunkMetadata(BaseModel):
    kategori: str                  # Fiziksel, Kimyasal, Ergonomik vb.
    tehlike_turu: str              # Gürültü, Titreşim, Toz vb.
    ilgili_mevzuat: Optional[str] = None  # Yönetmelik / Tüzük adı
    koruma_tipi: Optional[str] = None     # Toplu Koruma / KKD

class RiskMatrisiAnalizi(BaseModel):
    tehlike_tanimi: str
    olasilik: int                  # 1-5
    siddet: int                    # 1-5
    risk_skoru: int                # olasilik * siddet
    risk_seviyesi: str             # Düşük, Orta, Yüksek, Acil
    ilgili_mevzuat_maddesi: Optional[str] = None
    dof_onerisi: str               # Düzeltici Önleyici Faaliyet