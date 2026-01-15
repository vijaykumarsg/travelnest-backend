import os
from datetime import datetime, timedelta

from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import jwt, JWTError

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


# ===============================
# JWT CONFIG
# ===============================
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_THIS_SECRET_IN_PRODUCTION")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

security = HTTPBearer()


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Security(security)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ===============================
# BASE URL
# ===============================
def get_base_url():
    return os.getenv("BASE_URL", "http://127.0.0.1:8000")


# ===============================
# BOOKING NUMBER GENERATOR
# ===============================
def generate_booking_number(db: Session):
    today = datetime.utcnow().strftime("%Y%m%d")
    count = db.query(Booking).filter(
        Booking.booking_number.like(f"TNC-{today}-%")
    ).count()

    seq = str(count + 1).zfill(4)
    return f"TNC-{today}-{seq}"


# ===============================
# APP INIT
# ===============================
app = FastAPI(title="Travel Nest Cabs Backend")


# ===============================
# CORS
# ===============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===============================
# STATIC INVOICES
# ===============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INVOICE_DIR = os.path.join(BASE_DIR, "invoices")
os.makedirs(INVOICE_DIR, exist_ok=True)
app.mount("/invoices", StaticFiles(directory=INVOICE_DIR), name="invoices")


# ===============================
# DB INIT
# ===============================
Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ===============================
# HEALTH CHECK
# ===============================
@app.get("/")
def home():
    return {"status": "Backend running"}


# =====================================================
# PUBLIC API — CUSTOMER BOOKING (NO JWT)
# =====================================================
@app.post("/api/bookings", status_code=201)
def create_booking(data: BookingCreate, db: Session = Depends(get_db)):
    booking_number = generate_booking_number(db)

    booking = Booking(
        booking_number=booking_number,
        **data.dict()
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    return {
        "message": "Booking created successfully",
        "booking_id": booking.id,
        "booking_number": booking.booking_number
    }


# =====================================================
# ADMIN AUTH
# =====================================================
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

    token = create_access_token({"sub": admin.username})

    return {
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer"
    }


# =====================================================
# ADMIN APIs — JWT PROTECTED
# =====================================================
@app.get("/api/admin/bookings")
def view_bookings(
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin)
):
    bookings = db.query(Booking).order_by(Booking.created_at.desc()).all()
    result = []

    for b in bookings:
        invoice = db.query(Invoice).filter(
            Invoice.booking_id == b.id
        ).first()

        result.append({
            "id": b.id,
            "booking_number": b.booking_number,
            "name": b.name,
            "phone": b.phone,
            "pickup": b.pickup,
            "drop": b.drop,
            "car": b.car,
            "price": b.price,
            "status": b.status,
            "created_at": b.created_at,
            "invoice_exists": bool(invoice)
        })

    return result


@app.put("/api/admin/bookings/{booking_id}")
def update_booking_status(
    booking_id: int,
    data: BookingStatusUpdate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.status = data.status
    db.commit()

    whatsapp_link = None

    if data.status == "COMPLETED":
        invoice = db.query(Invoice).filter(
            Invoice.booking_id == booking_id
        ).first()

        if not invoice:
            base = booking.price
            gst = round(base * 0.05, 2)
            total = base + gst
            invoice_no = f"TNC-INV-{booking.booking_number}"

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
                status="GENERATED"
            )

            db.add(invoice)
            booking.status = "INVOICED"
            db.commit()

            invoice_url = f"{get_base_url()}/{pdf_path}"
            whatsapp_link = generate_whatsapp_link(
                booking.phone,
                invoice_url
            )

    return {
        "message": "Booking status updated",
        "whatsapp_link": whatsapp_link
    }


@app.post("/api/invoice/resend-whatsapp/{booking_id}")
def resend_invoice_whatsapp(
    booking_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    invoice = db.query(Invoice).filter(
        Invoice.booking_id == booking_id
    ).first()

    if not invoice:
        raise HTTPException(status_code=400, detail="Invoice not generated")

    invoice_url = f"{get_base_url()}/{invoice.pdf_path}"
    whatsapp_link = generate_whatsapp_link(
        booking.phone,
        invoice_url
    )

    return {
        "message": "WhatsApp invoice link generated",
        "whatsapp_link": whatsapp_link
    }
