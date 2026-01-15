from urllib.parse import quote

def generate_whatsapp_link(phone: str, invoice_url: str):
    phone = phone.strip().replace(" ", "").replace("+", "")
    if phone.startswith("0"):
        phone = "91" + phone[1:]

    message = (
        "🧾 *Travel Nest Cabs – GST Invoice*\n\n"
        "Your invoice is ready.\n\n"
        "📄 Download Invoice:\n"
        f"{invoice_url}\n\n"
        "Please tap *Send* to receive this invoice.\n\n"
        "Thank you for choosing Travel Nest Cabs 🚖"
    )

    return f"https://wa.me/{phone}?text={quote(message)}"
