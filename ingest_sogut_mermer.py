import os
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("❌ OPENAI_API_KEY bulunamadı!")

try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma

from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

CHROMA_PATH = "./database/mevzuat"

def sogut_mermer_isg_verilerini_ekle():
    documents = [
        # --- BASAMAK VE ŞEV GÜVENLİĞİ ---
        Document(
            page_content="Mermer Ocakları Şev ve Basamak Standardı: Açık işletme mermer ocaklarında basamak yüksekliği, kademede çalışan iş makinesinin (ekskavatör/loder) maksimum uzanma (bom) yüksekliğini geçemez. Basamak aynasında tespit edilen fay, çatlak ve eklem yapıları günlük olarak denetlenmeli, askıda kalan gevşek bloklar (askı taşlar) tespit edildiği an çalışma durdurularak arındırılmalıdır.",
            metadata={"kaynak": "Açık Maden İşletmeleri İSG Yönetmeliği", "kategori": "Basamak Güvenliği", "standart": "TR-ISG"}
        ),
        
        # --- ELMAS TEL KESME OPERASYONLARI ---
        Document(
            page_content="Elmas Tel Kesme Makinesi İSG Prosedürü: Elmas tel ile mermer blok kesimi sırasında, tel kopması durumunda kamçı etkisi oluşabileceğinden tel çalışma doğrultusunda ve 30 metre yarıçapında güvenlik alanı (tehlike bölgesi) oluşturulur. Çalışma sırasında bu alana kimse giremez. Tel soğutma suyu kesildiğinde makine otomatik durdurulmalıdır.",
            metadata={"kaynak": "Mermer Ocakları Tel Kesme Emniyet Kılavuzu", "kategori": "Makine Emniyeti", "standart": "TR-ISG"}
        ),

        # --- BLOK DEVİRME OPERASYONU ---
        Document(
            page_content="Mermer Blok Devirme Güvenlik Standardı: Ana kütleden ayrılan mermer bloklarının (sayalama) devrilmesi öncesinde, bloğun düşeceği zemin yumuşak malzeme (pasat/kum yastığı) ile kaplanmalıdır. Blok devrilme yönünde ve devrilme alanının en az 1.5 katı mesafede personel ve araç bulunması kesinlikle yasaktır.",
            metadata={"kaynak": "Mermer Üretim İSG Prosedürü", "kategori": "Saha Operasyonu", "standart": "TR-ISG"}
        ),

        # --- OCAK İÇİ NAKLİYAT VE BERM KURALLARI ---
        Document(
            page_content="Mermer Ocağı Nakliyat Yolları ve Berm (Emniyet Seti) Standardı: Mermer ocaklarında kamyon ve loder trafiğinin olduğu yollarda ve döküm/paso sahalarının kenarlarında, sahadaki en büyük iş makinesi tekerlek çapının en az %50'si (yarısı) yüksekliğinde koruma seti (berm) bulunması zorunludur. Berm bulunmayan yollarda araç trafiği durdurulur.",
            metadata={"kaynak": "MSHA 30 CFR § 56.9300 & TR İSG", "kategori": "Araç ve Yol Emniyeti", "standart": "MSHA/TR"}
        ),

        # --- YÜKLEME VE TAKOZLAMA ---
        Document(
            page_content="Mermer Blok Nakliye Yükleme Standardı: Nakliye kamyonlarına yüklenen mermer blokları, kasa içinde ahşap takozlar ve zincir/sapan mekanizmaları ile sabitlenmelidir. Denge merkezi kaymış veya çatlak barındıran blokların kara yolu nakliyesine çıkarılması yasaktır.",
            metadata={"kaynak": "Lojistik ve Yük Güvenliği Kılavuzu", "kategori": "Taşıma Emniyeti", "standart": "TR-ISG"}
        )
    ]

    embeddings = OpenAIEmbeddings()
    vector_store = Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=embeddings,
        collection_name="arin_isg_hafiza"
    )

    vector_store.add_documents(documents)
    print(f"✅ Söğüt Mermer Ocaklarına özel {len(documents)} adet kritik İSG standardı Arın AI hafızasına eklendi!")

if __name__ == "__main__":
    sogut_mermer_isg_verilerini_ekle()