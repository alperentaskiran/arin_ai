import os
import sys
import shutil
import time

# ==========================================
# CHROMA VE RUST KİLİTLENMELERİNİ ENGELLEYEN AYARLAR
# ==========================================
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_SERVER_NOFILE"] = "1"

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from langchain_community.document_loaders import PyPDFDirectoryLoader, DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

# Modül import yolunu güvenli hale getirme
try:
    from backend.models import ISGChunkMetadata
except ImportError:
    try:
        from models import ISGChunkMetadata
    except ImportError:
        ISGChunkMetadata = None


def safe_remove_dir(dir_path: str):
    """Windows dosya kilitleri ve izin hatalarına karşı güvenli klasör silme fonksiyonu."""
    if os.path.exists(dir_path):
        try:
            shutil.rmtree(dir_path)
            print(f"🧹 Eski veritabanı temizlendi: {os.path.basename(dir_path)}")
        except PermissionError:
            print(f"⚠️ İkaz: '{os.path.basename(dir_path)}' dosyası kilitli! Arka plandaki Python/Streamlit sürecini kapatın.")
        except Exception as e:
            print(f"⚠️ Klasör silinirken hata: {e}")


def load_documents_from_folder(folder_path: str):
    docs = []
    if not os.path.exists(folder_path):
        return docs

    try:
        pdf_loader = PyPDFDirectoryLoader(folder_path, glob="**/*.pdf")
        pdf_docs = pdf_loader.load()
        docs.extend(pdf_docs)
        print(f"  -> '{os.path.basename(folder_path)}': {len(pdf_docs)} sayfa PDF yüklendi.")
    except Exception as e:
        print(f"  -> PDF yükleme hatası ({folder_path}): {e}")

    try:
        txt_loader = DirectoryLoader(
            folder_path,
            glob="**/*.txt",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"}
        )
        txt_docs = txt_loader.load()
        docs.extend(txt_docs)
        print(f"  -> '{os.path.basename(folder_path)}': {len(txt_docs)} TXT dokümanı yüklendi.")
    except Exception as e:
        print(f"  -> TXT yükleme hatası ({folder_path}): {e}")

    return docs


def veritabani_besle():
    if not os.environ.get("OPENAI_API_KEY"):
        print("Hata: OPENAI_API_KEY ortam değişkeni bulunamadı!")
        return

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=250,
        separators=[
            "\nMADDE ",
            "\nMadde ",
            "\nEK-",
            "\n\n",
            "\n", 
            ". ", 
            " "
        ]
    )

    mevzuat_path = os.path.join(PROJECT_ROOT, "data", "mevzuat")
    kazalar_path = os.path.join(PROJECT_ROOT, "data", "kazalar")
    jeoloji_path = os.path.join(PROJECT_ROOT, "data", "jeoloji_mta")

    # RAG Engine ile tam uyumlu klasör yolları
    mevzuat_db_path = os.path.join(PROJECT_ROOT, "database", "mevzuat")
    kazalar_db_path = os.path.join(PROJECT_ROOT, "database", "kazalar")
    jeoloji_db_path = os.path.join(PROJECT_ROOT, "database", "jeoloji")

    # 1. MEVZUAT VERİLERİ
    print("\n--- Mevzuat Dokümanları İşleniyor ---")
    mevzuat_docs = load_documents_from_folder(mevzuat_path)

    if mevzuat_docs:
        safe_remove_dir(mevzuat_db_path)
        mevzuat_chunks = text_splitter.split_documents(mevzuat_docs)

        for chunk in mevzuat_chunks:
            source_file = os.path.basename(chunk.metadata.get("source", "Bilinmeyen Dosya"))
            if ISGChunkMetadata:
                default_meta = ISGChunkMetadata(
                    kategori="Genel Mevzuat & Teknik Doküman",
                    tehlike_turu="Genel",
                    ilgili_mevzuat=source_file,
                    koruma_tipi="Mevzuat / Standart"
                )
                chunk.metadata.update(default_meta.model_dump())

        Chroma.from_documents(
            documents=mevzuat_chunks,
            embedding=embeddings,
            persist_directory=mevzuat_db_path
        )
        print(f"✅ Başarılı: {len(mevzuat_chunks)} mevzuat parçası ChromaDB'ye eklendi.")

    # 2. TARİHSEL KAZALAR
    print("\n--- Tarihsel Kaza ve Saha Raporları İşleniyor ---")
    kaza_docs = load_documents_from_folder(kazalar_path)

    if kaza_docs:
        safe_remove_dir(kazalar_db_path)
        kaza_chunks = text_splitter.split_documents(kaza_docs)

        for chunk in kaza_chunks:
            source_file = os.path.basename(chunk.metadata.get("source", "İç Saha Raporu"))
            if ISGChunkMetadata:
                default_meta = ISGChunkMetadata(
                    kategori="Kaza / Ramak Kala Raporu",
                    tehlike_turu="Vaka Analizi",
                    ilgili_mevzuat=source_file,
                    koruma_tipi="Saha Önlemi"
                )
                chunk.metadata.update(default_meta.model_dump())

        Chroma.from_documents(
            documents=kaza_chunks,
            embedding=embeddings,
            persist_directory=kazalar_db_path
        )
        print(f"✅ Başarılı: {len(kaza_chunks)} kaza raporu parçası ChromaDB'ye eklendi.")

    # 3. MTA & JEOLOJİ
    print("\n--- MTA, Jeoloji & Teknik Madencilik Verileri İşleniyor ---")
    jeoloji_docs = load_documents_from_folder(jeoloji_path)

    if jeoloji_docs:
        safe_remove_dir(jeoloji_db_path)
        jeoloji_chunks = text_splitter.split_documents(jeoloji_docs)

        for chunk in jeoloji_chunks:
            source_file = os.path.basename(chunk.metadata.get("source", "MTA / Jeoloji Dokümanı"))
            if ISGChunkMetadata:
                default_meta = ISGChunkMetadata(
                    kategori="MTA / Jeoloji & İşletme Tekniği",
                    tehlike_turu="Jeolojik / Formasyon Riski",
                    ilgili_mevzuat=source_file,
                    koruma_tipi="Mühendislik Tedbiri"
                )
                chunk.metadata.update(default_meta.model_dump())

        Chroma.from_documents(
            documents=jeoloji_chunks,
            embedding=embeddings,
            persist_directory=jeoloji_db_path
        )
        print(f"✅ Başarılı: {len(jeoloji_chunks)} jeoloji/MTA parçası ChromaDB'ye eklendi.")


if __name__ == "__main__":
    os.makedirs(os.path.join(PROJECT_ROOT, "data", "mevzuat"), exist_ok=True)
    os.makedirs(os.path.join(PROJECT_ROOT, "data", "kazalar"), exist_ok=True)
    os.makedirs(os.path.join(PROJECT_ROOT, "data", "jeoloji_mta"), exist_ok=True)
    os.makedirs(os.path.join(PROJECT_ROOT, "database"), exist_ok=True)

    veritabani_besle()