import urllib.parse

def generate_whatsapp_link(phone: str, invoice_url: str):
    """
    Generates WhatsApp click-to-chat link
    """
    message = (
        "Hello 👋\n"
        "Your GST Invoice is ready.\n\n"
        f"Download here: {invoice_url}"
    )

    encoded_message = urllib.parse.quote(message)

    phone = phone.replace("+", "").replace(" ", "")

    return f"https://wa.me/{phone}?text={encoded_message}"
