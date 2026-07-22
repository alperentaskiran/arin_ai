from crewai import Crew, Process
from backend.agents import MiningSefAgents
from backend.tasks import MiningSefTasks

class CrewManager:
    def __init__(self):
        self.agents_factory = MiningSefAgents()
        self.tasks_factory = MiningSefTasks()

    def run_analysis(self, vardiya_notu: str) -> str:
        # 1. Ajanları Örnekle
        isg_uzmani = self.agents_factory.isg_mevzuat_uzmani_ajan()
        kaza_analisti = self.agents_factory.kaza_tahmin_ve_risk_ajani()
        bas_muhendis = self.agents_factory.bas_muhendis_raportor_ajan()

        # 2. Görevleri Oluştur ve Vardiya Notunu Enjekte Et
        task_mevzuat = self.tasks_factory.mevzuat_denetim_gorevi(isg_uzmani, vardiya_notu)
        task_kaza = self.tasks_factory.kaza_analiz_ve_tahmin_gorevi(kaza_analisti, vardiya_notu)
        
        # Baş mühendis, diğer iki ajanın raporunu sentezleyecek
        task_sentez = self.tasks_factory.nihai_rapor_sentez_gorevi(bas_muhendis, [task_mevzuat, task_kaza])

        # 3. Ekibi (Crew) Kur
        crew = Crew(
            agents=[isg_uzmani, kaza_analisti, bas_muhendis],
            tasks=[task_mevzuat, task_kaza, task_sentez],
            process=Process.sequential,  # Sıralı analiz süreci
            verbose=True
        )

        # 4. Süreci Başlat ve Sonucu Döndür
        result = crew.kickoff()
        return str(result)

if __name__ == "__main__":
    # Küçük bir backend testi yapalım
    manager = CrewManager()
    test_notu = "3. Batı galerisinde metan oranı %1.6'ya yükseldi. Tahkimatta hafif esneme sesleri var."
    print("\n--- Mühendislik Analizi Başlıyor (Backend Test) ---")
    rapor = manager.run_analysis(test_notu)
    print("\n--- ANALİZ SONUCU ---")
    print(rapor)