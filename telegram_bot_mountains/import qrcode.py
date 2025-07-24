import qrcode
from urllib.parse import quote

def generate_qr(post_id: str, post_title: str):
    """
    Генерирует QR-код для конкретного поста
    :param post_id: Уникальный идентификатор поста (например, p0001)
    :param post_title: Название поста для имени файла
    """
    # Создаем ссылку для бота
    tg_url = f"https://t.me/vershiny_rossii_bot?start={quote(post_id)}"
    
    # Настройки QR-кода
    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4,
    )
    qr.add_data(tg_url)
    qr.make(fit=True)
    
    # Генерация и сохранение изображения
    img = qr.make_image(fill_color="black", back_color="white")
    filename = f"qr_{post_title.lower().replace(' ', '_')}.png"
    img.save(filename)
    print(f"QR-код сохранен как: {filename}")
    return filename

# Пример использования:
# generate_qr("p0001", "Гора Эльбрус")