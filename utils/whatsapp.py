from urllib.parse import quote

def generate_whatsapp_link(phone, invoice_url):
    message = f"""
🧾 *Travel Nest Cabs – GST Invoice*

Your invoice is ready.

{invoice_url}

Thank you for choosing Travel Nest Cabs 🚖
"""
    return f"https://wa.me/{phone}?text={quote(message)}"
