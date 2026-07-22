# rag_service.py
import sqlite3
import json
import numpy as np
from sentence_transformers import SentenceTransformer

class RAGService:
    def __init__(self, db_path="arin_knowledge.db"):
        self.db_path = db_path
        # Türkçe destekli, hafif ve güçlü gömme (embedding) modeli
        self.embedder = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        self.init_db()

    def init_db(self):
        """Veri tabanı tablolarını oluşturur ve şemayı günceller."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Metaveri esnekliği için TEXT tipinde 'metadata' kolonu ekliyoruz
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT, -- 'mevzuat' veya 'kaza_raporu'
                title TEXT,       -- Örn: 'Soma Raporu'
                content TEXT,     -- Doküman içeriği
                vector BLOB,      -- Matematiksel vektör (embedding)
                metadata TEXT     -- JSON formatında ekstra bilgiler (Filtreleme için)
            )
        """)
        conn.commit()
        conn.close()

    def add_document(self, source_type: str, title: str, content: str, metadata: dict = None):
        """Yeni bir dokümanı vektörü ve metaverileriyle birlikte kaydeder."""
        # Metnin 384 boyutlu vektör karşılığını hesapla
        vector = self.embedder.encode(content)
        vector_blob = vector.astype(np.float32).tobytes()

        # Metadata dict nesnesini SQLite'ta saklamak için JSON string'e dönüştür
        metadata_json = json.dumps(metadata if metadata else {}, ensure_ascii=False)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO knowledge_base (source_type, title, content, vector, metadata) VALUES (?, ?, ?, ?, ?)",
            (source_type, title, content, vector_blob, metadata_json)
        )
        conn.commit()
        conn.close()

    def _cosine_similarity(self, v1, v2):
        """İki vektör arasındaki anlamsal benzerliği hesaplar."""
        denom = np.linalg.norm(v1) * np.linalg.norm(v2)
        if denom == 0:
            return 0
        return np.dot(v1, v2) / denom

    def search(self, query: str, source_type_filter: str = None, limit: int = 3):
        """
        Kullanıcı sorgusuna en yakın kayıtları bulur.
        İstenirse 'mevzuat' veya 'kaza_raporu' olarak ön filtreleme yapabilir.
        """
        query_vector = self.embedder.encode(query).astype(np.float32)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Eğer filtre varsa sadece o kategoriye ait verileri çekerek hızı ve doğruluğu artırıyoruz
        if source_type_filter:
            cursor.execute(
                "SELECT id, source_type, title, content, vector, metadata FROM knowledge_base WHERE source_type = ?",
                (source_type_filter,)
            )
        else:
            cursor.execute("SELECT id, source_type, title, content, vector, metadata FROM knowledge_base")
            
        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            doc_id, source_type, title, content, vector_blob, metadata_json = row
            doc_vector = np.frombuffer(vector_blob, dtype=np.float32)
            
            # Benzerlik skorunu hesapla
            similarity = self._cosine_similarity(query_vector, doc_vector)
            
            # JSON string'i tekrar Python dict formatına geri döndür
            metadata_dict = json.loads(metadata_json) if metadata_json else {}
            
            results.append({
                "id": doc_id,
                "source_type": source_type,
                "title": title,
                "content": content,
                "metadata": metadata_dict,
                "score": float(similarity) # JSON serileştirme hatası almamak için float'a zorla
            })

        # Skorları en yüksekten düşüğe doğru sırala ve en iyi sonuçları dön
        results = sorted(results, key=lambda x: x["score"], reverse=True)
        return results[:limit]