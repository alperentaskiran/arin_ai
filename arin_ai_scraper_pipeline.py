"""
Arın AI - Otomatik İSG, Kaza & MTA Jeoloji Taraması ve Vektör Veritabanı Entegrasyon Modülü
Aethel Technologies - 2026
"""

import os
import re
import logging
import requests
import urllib3
import hashlib
import tempfile
import feedparser
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

# SSL Uyarılarını Bastır
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()
os.environ["USER_AGENT"] = "ArinAI_Bot/1.0"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ArinAI_Ingestion")

from langchain_community.document_loaders import PyPDFLoader, PyPDFDirectoryLoader, DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

# --- 1. HEDEF VERİTABANLARI VE KLASÖR YAPILANDIRMASI ---
PIPELINE_CONFIGS = [
    {
        "domain": "mevzuat",
        "local_dir": "./data/mevzuat",
        "db_path": "database/mevzuat",
        "category": "Mevzuat/Yönetmelik",
        "sources": []  # Yerel ./data/mevzuat klasörüne PDF atılması önerilir
    },
    {
        "domain": "kazalar",
        "local_dir": "./data/kazalar",
        "db_path": "database/kazalar",
        "category": "Kaza/İnceleme",
        "sources": []  # ./data/kazalar klasörüne geçmiş kaza raporları eklenebilir
    },
    {
        "domain": "jeoloji",
        "local_dir": "./data/jeoloji",
        "db_path": "database/jeoloji",
        "category": "MTA/Jeoloji",
        "sources": []  # ./data/jeoloji klasörüne şev/kaya mekaniği dokümanları eklenebilir
    }
]

# --- 2. OTONOM TARAMA (RSS) ---
def get_dynamic_mevzuat_sources() -> List[Dict[str, Any]]:
    """Resmi Gazete ve İSG duyurularını hafif yapıyla tarar."""
    rss_feeds = [
        "https://www.resmigazete.gov.tr/rss.xml",
    ]
    keywords = ["maden", "iş sağlığı", "güvenliği", "yönetmelik", "tebliğ", "isg", "tahkimat", "grizu", "şev"]
    dynamic_sources = []
    
    for feed_url in rss_feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                title = getattr(entry, "title", "").lower()
                link = getattr(entry, "link", "")
                if any(kw in title for kw in keywords) and link:
                    source_id = hashlib.md5(link.encode()).hexdigest()[:10]
                    dynamic_sources.append({
                        "id": f"dinamik_{source_id}",
                        "name": entry.title,
                        "category": "Dinamik/RSS Keşif",
                        "type": "html",
                        "url": link
                    })
        except Exception as e:
            logger.warning(f"RSS Okuma Atlandı ({feed_url}): {e}")
            
    return dynamic_sources

# --- 3. METİN TEMİZLEME ---
def clean_isg_text(text: str) -> str:
    """Metindeki gereksiz karakter ve boşlukları temizler."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'Sayfa \d+\s*(/|of)\s*\d+', '', text, flags=re.IGNORECASE)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return text.strip()

# --- 4. SCRAPER & INGESTION PIPELINE ---
class ArinAIIngestionPipeline:
    def __init__(self, db_path: str, local_dir: str, category_name: str, chunk_size: int = 800, chunk_overlap: int = 150):
        self.db_path = db_path
        self.local_dir = local_dir
        self.category_name = category_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\nMadde ", "\nMADDE ", "\nEK-", "\n\n", "\n", ". ", " "]
        )
        
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    def fetch_local_documents(self) -> List[Document]:
        """Yerel klasördeki PDF ve TXT dosyalarını okur."""
        if not os.path.exists(self.local_dir):
            os.makedirs(self.local_dir, exist_ok=True)
            return []

        logger.info(f"Yerel klasör taranıyor: {self.local_dir}")
        docs = []

        # 1. PDF Dosyaları
        try:
            pdf_loader = PyPDFDirectoryLoader(self.local_dir, glob="**/*.pdf", recursive=True)
            pdf_docs = pdf_loader.load()
            if pdf_docs:
                logger.info(f"[{self.local_dir}] PDF dosyalarından {len(pdf_docs)} sayfa okundu.")
                docs.extend(pdf_docs)
        except Exception as e:
            logger.error(f"PDF yükleme hatası ({self.local_dir}): {e}")

        # 2. TXT Dosyaları
        try:
            txt_loader = DirectoryLoader(
                self.local_dir, 
                glob="**/*.txt", 
                loader_cls=TextLoader, 
                loader_kwargs={"encoding": "utf-8"},
                recursive=True
            )
            txt_docs = txt_loader.load()
            if txt_docs:
                logger.info(f"[{self.local_dir}] TXT dosyalarından {len(txt_docs)} doküman okundu.")
                docs.extend(txt_docs)
        except Exception as e:
            logger.error(f"TXT yükleme hatası ({self.local_dir}): {e}")

        for doc in docs:
            doc.page_content = clean_isg_text(doc.page_content)
            file_name = os.path.basename(doc.metadata.get("source", "Yerel_Belge"))
            doc.metadata.update({
                "source_id": "local_file",
                "file_name": file_name,
                "category": self.category_name,
                "ingested_at": datetime.now().isoformat()
            })
            
        return docs

    def fetch_source_data(self, source: Dict[str, Any]) -> List[Document]:
        """Uzak URL kaynaklarını (HTML / PDF) güvenle çeker."""
        logger.info(f"Uzak Kaynak Çekiliyor: {source['name']}")
        documents = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        try:
            if source["type"] == "html":
                resp = requests.get(source["url"], headers=headers, timeout=15, verify=False)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for script in soup(["script", "style", "nav", "footer", "header"]):
                        script.decompose()
                    text_content = clean_isg_text(soup.get_text())
                    if len(text_content) > 100:
                        doc = Document(
                            page_content=text_content,
                            metadata={"source": source["url"], "title": source["name"]}
                        )
                        documents.append(doc)

            elif source["type"] == "pdf":
                resp = requests.get(source["url"], headers=headers, timeout=25, verify=False)
                if resp.status_code == 200:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
                        tf.write(resp.content)
                        temp_path = tf.name
                    
                    loader = PyPDFLoader(temp_path)
                    documents = loader.load()
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

        except Exception as e:
            logger.warning(f"Uzak kaynak atlandı ({source['name']}): {e}")
            
        return documents

    def process_and_chunk(self, raw_documents: List[Document], source_info: Dict[str, Any] = None) -> List[Document]:
        if not raw_documents:
            return []
            
        chunks = self.text_splitter.split_documents(raw_documents)
        if source_info:
            for chunk in chunks:
                chunk.metadata.update({
                    "source_id": source_info.get("id", "web_source"),
                    "source_name": source_info.get("name", "Uzak Kaynak"),
                    "category": source_info.get("category", self.category_name),
                    "url": source_info.get("url", ""),
                    "ingested_at": datetime.now().isoformat()
                })
        return chunks

    def update_vector_store(self, chunks: List[Document]):
        """ChromaDB'ye 50'şerli güvenli paketlerle (batching) veri yazar."""
        if not chunks:
            logger.info(f"[{self.db_path}] Eklenecek yeni veri bulunamadı.")
            return

        os.makedirs(self.db_path, exist_ok=True)
        vectorstore = Chroma(
            persist_directory=self.db_path,
            embedding_function=self.embeddings
        )

        new_docs_to_add = []
        new_ids_to_add = []

        for chunk in chunks:
            source_name = chunk.metadata.get("source_name", chunk.metadata.get("file_name", "doc"))
            content_to_hash = f"{source_name}::{chunk.page_content}"
            chunk_hash = hashlib.sha256(content_to_hash.encode("utf-8")).hexdigest()
            chunk.metadata["chunk_hash"] = chunk_hash
            
            new_docs_to_add.append(chunk)
            new_ids_to_add.append(chunk_hash)

        # Basit ID Tekilleştirme
        unique_map = {doc_id: doc for doc_id, doc in zip(new_ids_to_add, new_docs_to_add)}
        
        # Mevcut ID'leri kontrol et
        try:
            existing_data = vectorstore.get()
            existing_ids = set(existing_data["ids"]) if existing_data and "ids" in existing_data else set()
        except Exception:
            existing_ids = set()

        final_docs = [doc for doc_id, doc in unique_map.items() if doc_id not in existing_ids]
        final_ids = [doc_id for doc_id in unique_map.keys() if doc_id not in existing_ids]

        if final_docs:
            logger.info(f"[{self.db_path}] {len(final_docs)} adet YENİ chunk yükleniyor...")
            
            # API Token ve SQLite limitini korumak için 50'şerli paketleme
            batch_size = 50
            for i in range(0, len(final_docs), batch_size):
                b_docs = final_docs[i:i + batch_size]
                b_ids = final_ids[i:i + batch_size]
                vectorstore.add_documents(documents=b_docs, ids=b_ids)
                logger.info(f"  -> Paket {i // batch_size + 1} / {(len(final_docs) - 1) // batch_size + 1} eklendi.")
                
            logger.info(f"✅ [{self.db_path}] Başarıyla güncellendi.")
        else:
            logger.info(f"[{self.db_path}] Tüm veriler zaten güncel.")

    def run_pipeline(self, target_sources: List[Dict[str, Any]]):
        all_chunks = []
        
        # 1. Yerel Dosyalar
        local_docs = self.fetch_local_documents()
        if local_docs:
            all_chunks.extend(self.process_and_chunk(local_docs))

        # 2. Uzak Kaynaklar
        for source in target_sources:
            raw_docs = self.fetch_source_data(source)
            if raw_docs:
                all_chunks.extend(self.process_and_chunk(raw_docs, source))

        # 3. Veritabanına Yaz
        self.update_vector_store(all_chunks)


def run_full_arin_ai_ingestion():
    logger.info("=== 🚀 ARIN AI VEKTÖR VERİTABANI BESLEME BAŞLADI ===")
    
    yeni_dinamik_kaynaklar = get_dynamic_mevzuat_sources()
    
    for config in PIPELINE_CONFIGS:
        if config["domain"] == "mevzuat" and yeni_dinamik_kaynaklar:
            config["sources"].extend(yeni_dinamik_kaynaklar)
    
    for config in PIPELINE_CONFIGS:
        logger.info(f"\n--- [{config['domain'].upper()}] Alanı İşleniyor ---")
        pipeline = ArinAIIngestionPipeline(
            db_path=config["db_path"],
            local_dir=config["local_dir"],
            category_name=config["category"]
        )
        pipeline.run_pipeline(target_sources=config["sources"])
        
    logger.info("\n=== ✅ TÜM İŞLEM BAŞARIYLA TAMAMLANDI ===")


if __name__ == "__main__":
    run_full_arin_ai_ingestion()