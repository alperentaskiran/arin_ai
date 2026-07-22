from PIL import Image

def logo_to_ico(input_path, output_path):
    # 1. Görseli aç
    img = Image.open(input_path).convert("RGBA")
    width, height = img.size

    # 2. Üstteki dairesel ikonun konumunu belirle (Yazıyı dahil etmeden)
    # Logoyu kapsayan kare alanı kırpıyoruz
    crop_size = int(height * 0.65)  # Logonun dairesel yüksekliği
    center_x = width // 2
    center_y = int(height * 0.35)   # Logonun dikeydeki merkez noktası

    left = max(0, center_x - crop_size // 2)
    top = max(0, center_y - crop_size // 2)
    right = min(width, center_x + crop_size // 2)
    bottom = min(height, center_y + crop_size // 2)

    cropped_img = img.crop((left, top, right, bottom))

    # 3. Yüksek kalitede 64x64 boyutuna getir
    resized_img = cropped_img.resize((64, 64), Image.Resampling.LANCZOS)

    # 4. .ico formatında kaydet (Dilerseniz içine 16x16, 32x32 gibi alternatif boyutlar da eklenebilir)
    resized_img.save(
        output_path, 
        format="ICO", 
        sizes=[(64, 64)]
    )
    print(f"Başarılı! İkon '{output_path}' olarak kaydedildi.")

# Çalıştırma
logo_to_ico("arin_logo.png", "favicon.ico")