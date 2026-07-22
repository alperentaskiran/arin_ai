from crewai import Task

class MiningSefTasks:
    def mevzuat_denetim_gorevi(self, agent, vardiya_notu) -> Task:
        return Task(
            description=(
                f"Sana iletilen şu vardiya notunu/raporunu incele:\n\n'{vardiya_notu}'\n\n"
                "Bu raporda geçen teknik verileri, gaz ölçümlerini, tahkimat durumlarını ve çalışma koşullarını "
                "'Mevzuat Arama Aracı'nı kullanarak resmi maden yönetmelikleri ve 6331 sayılı kanun ile kıyasla. "
                "Hangi maddelerin ihlal edildiğini, hangi yasal limitlerin (örneğin metan, karbonmonoksit oranları, "
                "havalandırma hızları vb.) zorlandığını veya aşıldığını net olarak yasa maddeleriyle raporla."
            ),
            expected_output=(
                "Mevzuat uyumluluk raporu. Tespit edilen risklerin hangi kanun veya yönetmelik maddesine "
                "aykırı olduğunu ve yasal sınırları içeren detaylı teknik analiz."
            ),
            agent=agent
        )

    def kaza_analiz_ve_tahmin_gorevi(self, agent, vardiya_notu) -> Task:
        return Task(
            description=(
                f"Sana iletilen şu vardiya notunu/raporunu incele:\n\n'{vardiya_notu}'\n\n"
                "1. Bu rapordaki anomalileri ve çalışma koşullarını, Tarihsel Kaza Analiz Aracı'nı kullanarak "
                "geçmişte yaşanan büyük maden facialarının (Soma, Amasra, Kozlu, İliç vb.) kök nedenleriyle karşılaştır.\n"
                "2. Sahadaki her bir tehlike için 5x5 Risk Matrisi metodolojisini kullan: "
                "Olasılık (1-5) ve Şiddet (1-5) değerlerini belirleyerek Risk Skoru = Olasılık x Şiddet olarak puanla."
            ),
            expected_output=(
                "Tarihsel kaza benzerlik ve kök neden analiz raporu. Tespit edilen risklerin 5x5 Risk Matrisi skorları "
                "(Olasılık x Şiddet) ve geçmiş facialarla olan paralellikleri içeren proaktif risk değerlendirmesi."
            ),
            agent=agent
        )

    def nihai_rapor_sentez_gorevi(self, agent, context_tasks) -> Task:
        return Task(
            description=(
                "Mevzuat Uzmanı ve Kaza Analisti ajanlar tarafından hazırlanan raporları birleştir, "
                "sentezle ve maden işletme yönetimi ile vardiya amirlerinin hızla aksiyon alabileceği "
                "üst düzey bir 'Proaktif Karar Destek ve Aksiyon Raporu' hazırla.\n\n"
                "Rapor içerisinde 5x5 Risk Matrisi skorlarına dayalı acil Düzeltici ve Önleyici Faaliyet (DÖF) "
                "tablosuna veya maddelerine mutlaka yer ver. Raporun dili net, emir ve tavsiyeler uygulanabilir olmalıdır."
            ),
            expected_output=(
                "Markdown formatında yazılmış, profesyonel, başlıkları net (1. Yasal Durum ve Mevzuat İhlalleri, "
                "2. 5x5 Risk Matrisi ve Geçmiş Kaza Benzerlikleri, 3. Acil Alınması Gereken Önlemler ve DÖF Planı) "
                "olan nihai karar destek raporu."
            ),
            agent=agent,
            context=context_tasks  # Önceki görevlerin çıktılarını bu ajana girdi olarak veriyoruz
        )