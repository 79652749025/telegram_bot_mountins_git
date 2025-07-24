class QRCodeService:
    @staticmethod
    def generate_qr_with_logo(data, logo_path):
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(data)
        qr.make(fit=True)
        
        qr_image = qr.make_image(fill_color="black", back_color="white")
        
        # Добавление логотипа
        logo = Image.open(logo_path)
        qr_image = qr_image.copy()
        pos = ((qr_image.size[0] - logo.size[0]) // 2,
               (qr_image.size[1] - logo.size[1]) // 2)
        qr_image.paste(logo, pos, logo)
        
        return qr_image