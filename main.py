import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import Base, engine, SessionLocal
from models import Booking, Admin, Invoice
from schemas import (
    BookingCreate,
    AdminCreate,
    AdminLogin,
    BookingStatusUpdate,
    InvoiceStatusUpdate,
)
from auth import hash_password, verify_password
from generate_invoice import generate_invoice
from utils.whatsapp import generate_whatsapp_link

def get_base_url():
    # Render / Production
    if os.getenv("BASE_URL"):
        return os.getenv("BASE_URL")

    # Local fallback
    return "http://127.0.0.1:8000"

# -------------------
# App Init
# -------------------
app = FastAPI(title="Travel Nest Cabs Backend")

# -------------------
# CORS (DEV SAFE)
# -------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------
# Static Invoices
# -------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INVOICE_DIR = os.path.join(BASE_DIR, "invoices")
os.makedirs(INVOICE_DIR, exist_ok=True)

app.mount("/invoices", StaticFiles(directory=INVOICE_DIR), name="invoices")

# -------------------
# DB Init
# -------------------
Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------
# Home
# -------------------
@app.get("/")
def home():
    return {"status": "Running"}


# -------------------
# Booking API
# -------------------
@app.post("/api/bookings")
def create_booking(data: BookingCreate, db: Session = Depends(get_db)):
    booking = Booking(**data.dict())
    db.add(booking)
    db.commit()
    return {"message": "Booking created successfully"}


# -------------------
# Admin APIs
# -------------------
@app.post("/api/admin/create")
def create_admin(data: AdminCreate, db: Session = Depends(get_db)):
    if db.query(Admin).filter(Admin.username == data.username).first():
        raise HTTPException(status_code=400, detail="Admin already exists")

    admin = Admin(
        username=data.username,
        password=hash_password(data.password),
    )
    db.add(admin)
    db.commit()
    return {"message": "Admin created successfully"}


@app.post("/api/admin/login")
def admin_login(data: AdminLogin, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.username == data.username).first()
    if not admin or not verify_password(data.password, admin.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"message": "Login successful"}


# -------------------
# View Bookings
# -------------------
@app.get("/api/admin/bookings")
def view_bookings(db: Session = Depends(get_db)):
    bookings = db.query(Booking).all()
    result = []

    for b in bookings:
        invoice = db.query(Invoice).filter(
            Invoice.booking_id == b.id
        ).first()

        result.append({
            "id": b.id,
            "name": b.name,
            "phone": b.phone,
            "pickup": b.pickup,
            "drop": b.drop,
            "car": b.car,
            "price": b.price,
            "status": b.status,
            "invoice_exists": True if invoice else False
        })

    return result


# -------------------
# UPDATE BOOKING STATUS
# AUTO INVOICE + WHATSAPP
# -------------------
@app.put("/api/admin/bookings/{booking_id}")
def update_booking_status(
    booking_id: int,
    data: BookingStatusUpdate,
    db: Session = Depends(get_db),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # ✅ NORMALIZE STATUS
    new_status = data.status.strip().upper()
    booking.status = new_status
    db.commit()

    whatsapp_link = None

    # ✅ AUTO INVOICE WHEN COMPLETED
    if new_status == "COMPLETED":
        existing_invoice = db.query(Invoice).filter(
            Invoice.booking_id == booking_id
        ).first()

        if not existing_invoice:
            base = booking.price
            gst = round(base * 0.05, 2)
            total = base + gst

            invoice_no = f"TNC-INV-{booking.id}"

            pdf_path = generate_invoice({
                "invoice_no": invoice_no,
                "customer_name": booking.name,
                "pickup": booking.pickup,
                "drop": booking.drop,
                "car": booking.car,
                "travel_date": booking.travel_date,
                "base_amount": base,
                "gst_amount": gst,
                "total_amount": total,
            })

            invoice = Invoice(
                booking_id=booking.id,
                invoice_no=invoice_no,
                base_amount=base,
                gst_amount=gst,
                total_amount=total,
                pdf_path=pdf_path,
                status="Generated"
            )

            db.add(invoice)

            # SYSTEM STATE
            booking.status = "INVOICED"
            db.commit()

            # ✅ LOCAL / PROD SAFE URL
            base_url = get_base_url()
            invoice_url = f"{base_url}/{pdf_path}"


            whatsapp_link = generate_whatsapp_link(
                booking.phone,
                invoice_url
            )

    return {
        "message": "Booking status updated",
        "whatsapp_link": whatsapp_link
    }


# -------------------
# MANUAL INVOICE (BACKUP)
# -------------------
@app.post("/api/invoice/generate/{booking_id}")
def generate_gst_invoice(booking_id: int, db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    existing_invoice = db.query(Invoice).filter(
        Invoice.booking_id == booking_id
    ).first()

    if existing_invoice:
        return {
            "message": "Invoice already generated",
            "invoice_url": f"/{existing_invoice.pdf_path}",
            "invoice_status": existing_invoice.status
        }

    if booking.status.upper() != "COMPLETED":
        raise HTTPException(
            status_code=400,
            detail="Invoice can be generated only after ride completion"
        )

    base = booking.price
    gst = round(base * 0.05, 2)
    total = base + gst

    invoice_no = f"TNC-INV-{booking.id}"

    pdf_path = generate_invoice({
        "invoice_no": invoice_no,
        "customer_name": booking.name,
        "pickup": booking.pickup,
        "drop": booking.drop,
        "car": booking.car,
        "travel_date": booking.travel_date,
        "base_amount": base,
        "gst_amount": gst,
        "total_amount": total,
    })

    invoice = Invoice(
        booking_id=booking.id,
        invoice_no=invoice_no,
        base_amount=base,
        gst_amount=gst,
        total_amount=total,
        pdf_path=pdf_path,
        status="Generated"
    )

    db.add(invoice)
    booking.status = "INVOICED"
    db.commit()

    return {
        "message": "GST Invoice generated successfully",
        "invoice_url": f"/{pdf_path}",
        "invoice_status": "Generated"
    }


# -------------------
# UPDATE INVOICE STATUS
# -------------------
@app.put("/api/admin/invoices/{invoice_id}/status")
def update_invoice_status(
    invoice_id: int,
    data: InvoiceStatusUpdate,
    db: Session = Depends(get_db)
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status == "Paid":
        raise HTTPException(
            status_code=400,
            detail="Paid invoice cannot be modified"
        )

    invoice.status = data.status
    db.commit()

    return {
        "message": "Invoice status updated",
        "invoice_id": invoice_id,
        "status": data.status
    }


# -------------------
# RESEND WHATSAPP
# -------------------
@app.post("/api/invoice/resend-whatsapp/{booking_id}")
def resend_invoice_whatsapp(
    booking_id: int,
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    invoice = db.query(Invoice).filter(
        Invoice.booking_id == booking_id
    ).first()

    if not invoice:
        raise HTTPException(
            status_code=400,
            detail="Invoice not generated yet"
        )

    base_url = get_base_url()
    invoice_url = f"{base_url}/{invoice.pdf_path}"


    whatsapp_link = generate_whatsapp_link(
        booking.phone,
        invoice_url
    )

    return {
        "message": "WhatsApp invoice link generated",
        "whatsapp_link": whatsapp_link
    }
