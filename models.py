from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from datetime import datetime
from database import Base


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)

    # ✅ NEW
    booking_number = Column(String, unique=True, index=True)

    name = Column(String)
    phone = Column(String)
    pickup = Column(String)
    drop = Column(String)
    trip_type = Column(String)
    car = Column(String)
    price = Column(Float)
    travel_date = Column(String)
    travel_time = Column(String)

    status = Column(String, default="PENDING")

    # ✅ NEW
    created_at = Column(DateTime, default=datetime.utcnow)


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), unique=True)
    invoice_no = Column(String, unique=True)
    base_amount = Column(Float)
    gst_amount = Column(Float)
    total_amount = Column(Float)
    pdf_path = Column(String)

    status = Column(String, default="NOT_GENERATED")
