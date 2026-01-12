from pydantic import BaseModel
from typing import Literal

class BookingCreate(BaseModel):
    name: str
    phone: str
    pickup: str
    drop: str
    trip_type: str
    car: str
    price: float
    travel_date: str
    travel_time: str


class AdminCreate(BaseModel):
    username: str
    password: str


class AdminLogin(BaseModel):
    username: str
    password: str


class BookingStatusUpdate(BaseModel):
    status: Literal["Pending", "Confirmed", "Completed", "Cancelled"]


class InvoiceStatusUpdate(BaseModel):
    status: Literal[
        "NotGenerated",
        "Generated",
        "Sent",
        "Paid",
        "Cancelled"
    ]