from pydantic import BaseModel
from typing import Literal


# -------------------
# BOOKING (FRONTEND)
# -------------------
class BookingCreate(BaseModel):
    name: str
    phone: str
    pickup: str
    drop: str
    trip_type: str
    car: str
    price: float
    travel_date: str | None = None
    travel_time: str | None = None



# -------------------
# ADMIN AUTH
# -------------------
class AdminCreate(BaseModel):
    username: str
    password: str


class AdminLogin(BaseModel):
    username: str
    password: str


# -------------------
# BOOKING STATUS
# -------------------
class BookingStatusUpdate(BaseModel):
    status: Literal[
        "PENDING",
        "CONFIRMED",
        "COMPLETED",
        "CANCELLED"
    ]


# -------------------
# INVOICE STATUS
# -------------------
class InvoiceStatusUpdate(BaseModel):
    status: Literal[
        "NOT_GENERATED",
        "GENERATED",
        "SENT",
        "PAID",
        "CANCELLED"
    ]
