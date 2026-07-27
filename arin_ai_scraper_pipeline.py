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
import feedparser
from typing import List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

# SSL Uyarılarını Bastır
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Environment değişkenlerini yükle
load_dotenv()

# User-Agent ve Deprecation uyarılarını engellemek için ortam değişkeni
os.environ["USER_AGENT"] = "ArinAI_Bot/1.0"

# Logging yapılandırması
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ArinAI_Ingestion")

from langchain_community.document_loaders import PyPDFLoader, PyPDFDirectoryLoader, WebBaseLoader, DirectoryLoader, TextLoader
from langchain_community.document_loaders import PlaywrightURLLoader
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
        "sources": [
            {
                "id": "isg_kanunu_6331",
                "name": "6331 Sayılı İş Sağlığı ve Güvenliği Kanunu",
                "category": "Mevzuat/Kanun",
                "type": "pdf",
                "url": "https://www.mevzuat.gov.tr/MevzuatMetin/1.5.6331.pdf"
            }
        ]
    },
    {
        "domain": "kazalar",
        "local_dir": "./data/kazalar",
        "db_path": "database/kazalar",
        "category": "Kaza/İnceleme",
        "sources": []  # İhtiyaç halinde geçmiş kaza raporu PDF bağlantıları eklenebilir
    },
    {
        "domain": "jeoloji",
        "local_dir": "./data/jeoloji",
        "db_path": "database/jeoloji",
        "category": "MTA/Jeoloji",
        "sources": []  # İhtiyaç halinde MTA doğrudan bülten PDF/HTML bağlantıları eklenebilir
    }
]

# --- OTONOM TARAMA ---
def get_dynamic_mevzuat_sources():
    """
    İlgili kurumların RSS/Duyuru akışlarını tarayarak 
    sisteme eklenecek yeni bağlantıları otomatik keşfeder.
    """
    # Not: Aşağıdakiler temsilidir. Kurumların aktif RSS linkleri veya duyuru XML'leri eklenebilir.
    rss_feeds = [
        "https://www.resmigazete.gov.tr/rss",  # Resmî Gazete RSS
        "https://www.csgb.gov.tr/rss.xml"      # ÇSGB Duyuruları
    ]
    
    # Sistemin ilgileneceği anahtar kelimeler
    keywords = ["maden", "iş sağlığı", "güvenliği", "yönetmelik", "tebliğ", "isg", "tahkimat", "grizu"]
    dynamic_sources = []
    
    for feed_url in rss_feeds:
        try:
            logger.info(f"Otonom Tarama: {feed_url} dinleniyor...")
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries:
                title = entry.title.lower()
                
                # Eğer başlıkta madencilik ve İSG ile ilgili bir terim geçiyorsa
                if any(kw in title for kw in keywords):
                    # Linki hash'leyerek benzersiz bir ID oluştur
                    source_id = hashlib.md5(entry.link.encode()).hexdigest()[:10]
                    
                    dynamic_sources.append({
                        "id": f"dinamik_{source_id}",
                        "name": entry.title,
                        "category": "Dinamik/RSS Kesif",
                        "type": "html", # İlk etapta web sayfası olarak alıyoruz
                        "url": entry.link
                    })
        except Exception as e:
            logger.error(f"RSS Okuma Hatası ({feed_url}): {e}")
            
    return dynamic_sources

# --- 2. METİN TEMİZLEME ---
def clean_isg_text(text: str) -> str:
    """İSG, kaza ve jeoloji metinlerindeki gereksiz boşlukları ve sayfa numaralarını temizler."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'Sayfa \d+\s*(/|of)\s*\d+', '', text, flags=re.IGNORECASE)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return text.strip()


# --- 3. SCRAPER & INGESTION PIPELINE ---
class ArinAIIngestionPipeline:
    def __init__(self, db_path: str, local_dir: str, category_name: str, chunk_size: int = 600, chunk_overlap: int = 120):
        self.db_path = db_path
        self.local_dir = local_dir
        self.category_name = category_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Maddeler ve paragraf geçişleri için optimize splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\nMadde ", "\nMADDE ", "\nEK-", "\n\n", "\n", ". ", " "]
        )
        
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    def download_pdf_safely(self, url: str, temp_filename: str = "temp_download.pdf") -> str:
        """Güvenli HTTP isteği ile PDF indirir."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=25, verify=False)
        if response.status_code == 200:
            with open(temp_filename, "wb") as f:
                f.write(response.content)
            return temp_filename
        raise Exception(f"HTTP Error {response.status_code}")

    def fetch_local_documents(self) -> List[Document]:
        """Belirtilen yerel klasördeki PDF ve TXT dosyalarını okur."""
        if not os.path.exists(self.local_dir):
            os.makedirs(self.local_dir, exist_ok=True)
            logger.warning(f"'{self.local_dir}' klasörü oluşturuldu. Yerel dosya taranıyor...")
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

        # Metadata güncellemesi
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
        """Uzak URL kaynaklarını indirip okur."""
        logger.info(f"Uzak Kaynak Taranıyor: {source['name']} ({source['url']})")
        documents = []
        temp_file = None
        
        try:
            if source["type"] == "pdf":
                temp_file = self.download_pdf_safely(source["url"])
                loader = PyPDFLoader(temp_file)
                documents = loader.load()
            elif source["type"] == "html":
                # Eski WebBaseLoader yerine Playwright kullanıyoruz
                logger.info("Playwright ile JS tabanlı sayfa işleniyor...")
                loader = PlaywrightURLLoader(
                    urls=[source["url"]],
                    remove_selectors=["nav", "footer", "header", "script", "style", "aside"], # Menü ve altbilgileri filtrele
                    kwargs={"headless": True} # Arka planda sessiz çalış
                )
                documents = loader.load()
                
            for doc in documents:
                doc.page_content = clean_isg_text(doc.page_content)
                
            logger.info(f"Uzak kaynaktan {len(documents)} sayfa çekildi.")
        except Exception as e:
            logger.error(f"Uzak kaynak yükleme hatası ({source['name']}): {str(e)}")
        finally:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
            
        return documents

    def process_and_chunk(self, raw_documents: List[Document], source_info: Dict[str, Any] = None) -> List[Document]:
        if not raw_documents:
            return []
            
        chunks = self.text_splitter.split_documents(raw_documents)
        
        if source_info:
            for chunk in chunks:
                chunk.metadata.update({
                    "source_id": source_info["id"],
                    "source_name": source_info["name"],
                    "category": source_info["category"],
                    "url": source_info["url"],
                    "ingested_at": datetime.now().isoformat()
                })
            
        return chunks

    def update_vector_store(self, chunks: List[Document]):
        """Sadece yeni veya içeriği değişen belgeleri veritabanına ekler (SHA-256 Deduplication)."""
        if not chunks:
            logger.warning(f"[{self.db_path}] Eklenecek chunk bulunamadı, adım atlanıyor.")
            return

        logger.info(f"Veritabanına bağlanılıyor ({self.db_path})...")
        
        vectorstore = Chroma(
            persist_directory=self.db_path,
            embedding_function=self.embeddings
        )

        new_docs_to_add = []
        new_ids_to_add = []

        for chunk in chunks:
            source_name = chunk.metadata.get("source_name", chunk.metadata.get("file_name", "unknown_source"))
            content_to_hash = f"{source_name}::{chunk.page_content}"
            chunk_hash = hashlib.sha256(content_to_hash.encode("utf-8")).hexdigest()
            
            chunk.metadata["chunk_hash"] = chunk_hash
            new_docs_to_add.append(chunk)
            new_ids_to_add.append(chunk_hash)

        # Tekilleştirme
        unique_ids = []
        unique_docs = []
        seen_ids = set()

        for doc, doc_id in zip(new_docs_to_add, new_ids_to_add):
            if doc_id not in seen_ids:
                seen_ids.add(doc_id)
                unique_ids.append(doc_id)
                unique_docs.append(doc)

        existing_data = vectorstore.get(ids=unique_ids)
        existing_ids = set(existing_data["ids"]) if existing_data and "ids" in existing_data else set()

        final_docs = []
        final_ids = []

        for doc, doc_id in zip(unique_docs, unique_ids):
            if doc_id not in existing_ids:
                final_docs.append(doc)
                final_ids.append(doc_id)

        if final_docs:
            logger.info(f"[{self.db_path}] {len(final_docs)} adet YENİ veri tespit edildi, ekleniyor...")
            vectorstore.add_documents(documents=final_docs, ids=final_ids)
            logger.info(f"✅ [{self.db_path}] Güncelleme tamamlandı.")
        else:
            logger.info(f"[{self.db_path}] Tüm veriler GÜNCEL. Yeni kayıt eklenmedi.")

    def run_pipeline(self, target_sources: List[Dict[str, Any]]):
        all_chunks = []
        
        # 1. Yerel Dosyalar
        local_docs = self.fetch_local_documents()
        if local_docs:
            local_chunks = self.process_and_chunk(local_docs)
            all_chunks.extend(local_chunks)

        # 2. Uzak Web / PDF Kaynakları
        for source in target_sources:
            raw_docs = self.fetch_source_data(source)
            chunks = self.process_and_chunk(raw_docs, source)
            all_chunks.extend(chunks)

        # 3. ChromaDB Güncelleme
        self.update_vector_store(all_chunks)


def run_full_arin_ai_ingestion():
    logger.info("=== 🚀 ARIN AI TÜM VERİTABANI BESLEME DÖNGÜSÜ BAŞLADI ===")
    
    # 1. Dinamik bağlantıları (RSS) keşfet
    yeni_dinamik_kaynaklar = get_dynamic_mevzuat_sources()
    
    if yeni_dinamik_kaynaklar:
        logger.info(f"Otonom Keşif: {len(yeni_dinamik_kaynaklar)} adet yeni mevzuat/duyuru linki bulundu.")
    else:
        logger.info("Otonom Keşif: Gündemde yeni bir İSG/Maden mevzuat duyurusu yok.")

    # 2. Keşfedilen bağlantıları yapılandırmaya (PIPELINE_CONFIGS) dahil et
    for config in PIPELINE_CONFIGS:
        if config["domain"] == "mevzuat" and yeni_dinamik_kaynaklar:
            config["sources"].extend(yeni_dinamik_kaynaklar)
    
    # 3. Klasik işleme döngüsü
    for config in PIPELINE_CONFIGS:
        logger.info(f"\n--- [{config['domain'].upper()}] Alanı İşleniyor ---")
        pipeline = ArinAIIngestionPipeline(
            db_path=config["db_path"],
            local_dir=config["local_dir"],
            category_name=config["category"]
        )
        pipeline.run_pipeline(target_sources=config["sources"])
        
    logger.info("\n=== ✅ TÜM VERİTABANLARI GÜNCELLENDİ VE HAZIR ===")


if __name__ == "__main__":
    run_full_arin_ai_ingestion()