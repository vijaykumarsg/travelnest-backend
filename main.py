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


# -------------------
# App Init
# -------------------
app = FastAPI(title="Travel Nest Cabs Backend")

# -------------------
# CORS
# -------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------
# Static Invoices Path
# -------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INVOICE_DIR = os.path.join(BASE_DIR, "invoices")
os.makedirs(INVOICE_DIR, exist_ok=True)

app.mount("/invoices", StaticFiles(directory=INVOICE_DIR), name="invoices")

# -------------------
# DB Init
# -------------------
Base.metadata.create_all(bind=engine)

# -------------------
# DB Dependency
# -------------------
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
# Booking APIs
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
    return db.query(Booking).all()

# -------------------
# UPDATE BOOKING STATUS
# AUTO-INVOICE + WHATSAPP
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

    booking.status = data.status
    db.commit()

    invoice_created = False
    invoice_url = None
    whatsapp_link = None

    if data.status.lower() == "completed":
        existing_invoice = db.query(Invoice).filter(
            Invoice.booking_id == booking_id
        ).first()

        if not existing_invoice:
            base_amount = booking.price
            gst_amount = round(base_amount * 0.05, 2)
            total_amount = base_amount + gst_amount

            invoice_no = f"TNC-INV-{booking.id}"

            invoice_data = {
                "invoice_no": invoice_no,
                "customer_name": booking.name,
                "pickup": booking.pickup,
                "drop": booking.drop,
                "car": booking.car,
                "travel_date": booking.travel_date,
                "base_amount": base_amount,
                "gst_amount": gst_amount,
                "total_amount": total_amount,
            }

            pdf_path = generate_invoice(invoice_data)

            invoice = Invoice(
                booking_id=booking.id,
                invoice_no=invoice_no,
                base_amount=base_amount,
                gst_amount=gst_amount,
                total_amount=total_amount,
                pdf_path=pdf_path,
                status="Generated"
            )

            db.add(invoice)
            booking.status = "INVOICED"
            db.commit()

            invoice_created = True
            invoice_url = f"/{pdf_path}"

            invoice_full_url = f"https://travelnest-backend-p13p.onrender.com{invoice_url}"
            whatsapp_link = generate_whatsapp_link(
                booking.phone,
                invoice_full_url
            )

    return {
        "message": "Booking status updated",
        "invoice_created": invoice_created,
        "invoice_url": invoice_url,
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

    if booking.status.lower() != "completed":
        raise HTTPException(
            status_code=400,
            detail="Invoice can be generated only after ride completion"
        )

    base_amount = booking.price
    gst_amount = round(base_amount * 0.05, 2)
    total_amount = base_amount + gst_amount

    invoice_no = f"TNC-INV-{booking.id}"

    invoice_data = {
        "invoice_no": invoice_no,
        "customer_name": booking.name,
        "pickup": booking.pickup,
        "drop": booking.drop,
        "car": booking.car,
        "travel_date": booking.travel_date,
        "base_amount": base_amount,
        "gst_amount": gst_amount,
        "total_amount": total_amount,
    }

    pdf_path = generate_invoice(invoice_data)

    invoice = Invoice(
        booking_id=booking.id,
        invoice_no=invoice_no,
        base_amount=base_amount,
        gst_amount=gst_amount,
        total_amount=total_amount,
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
