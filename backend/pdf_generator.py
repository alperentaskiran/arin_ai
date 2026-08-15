# pdf_generator.py
from datetime import datetime
from weasyprint import HTML

def generate_isg_pdf_report(analysis_title, analysis_content, author="Arın AI İSG Asistanı"):
    current_date = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    html_template = f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{
                size: A4;
                margin: 20mm 15mm;
                @bottom-right {{
                    content: "Sayfa " counter(page) " / " counter(pages);
                    font-size: 9pt;
                    color: #718096;
                }}
            }}
            body {{
                font-family: 'Helvetica Neue', Arial, sans-serif;
                color: #2D3748;
                line-height: 1.6;
                margin: 0;
            }}
            .header {{
                border-bottom: 2px solid #00D2FF;
                padding-bottom: 15px;
                margin-bottom: 25px;
            }}
            .company-title {{
                font-size: 20pt;
                font-weight: bold;
                color: #0A192F;
                margin: 0;
                letter-spacing: 1px;
            }}
            .subtitle {{
                font-size: 10pt;
                color: #4A5568;
                margin-top: 4px;
            }}
            .meta-box {{
                background-color: #F7FAFC;
                border-left: 4px solid #0A192F;
                padding: 12px 16px;
                margin-bottom: 25px;
                font-size: 9.5pt;
            }}
            .meta-item {{
                margin-bottom: 4px;
            }}
            h1 {{
                font-size: 14pt;
                color: #1A202C;
                border-bottom: 1px solid #E2E8F0;
                padding-bottom: 6px;
                margin-top: 20px;
            }}
            .content {{
                font-size: 10pt;
                text-align: justify;
            }}
            .footer {{
                margin-top: 40px;
                padding-top: 15px;
                border-top: 1px dashed #CBD5E0;
                font-size: 8.5pt;
                color: #A0AEC0;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="company-title">ARIN AI // İSG KARAR DESTEK RAPORU</div>
            <div class="subtitle">Aethel Technologies Otonom Güvenlik & Risk Değerlendirme Sistemi</div>
        </div>

        <div class="meta-box">
            <div class="meta-item"><strong>Rapor Başlığı:</strong> {analysis_title}</div>
            <div class="meta-item"><strong>Oluşturulma Tarihi:</strong> {current_date}</div>
            <div class="meta-item"><strong>Yetkili Birim / Ajan:</strong> {author}</div>
            <div class="meta-item"><strong>Sistem Versiyonu:</strong> Arın AI Enterprise v1.0</div>
        </div>

        <div class="content">
            {analysis_content}
        </div>

        <div class="footer">
            Bu belge Arın AI yapay zeka karar destek motoru tarafından 6331 sayılı İSG Kanunu ve ilgili maden mevzuatları referans alınarak üretilmiştir.
        </div>
    </body>
    </html>
    """
    
    pdf_bytes = HTML(string=html_template).write_pdf()
    return pdf_bytes