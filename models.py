from enum import Enum
from datetime import date
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class AppointmentType(str, Enum):
    consultation = "consultation"
    follow_up = "follow_up"
    physical = "physical"
    specialist = "specialist"


class Slot(BaseModel):
    start_time: str  # "HH:MM"
    end_time: str    # "HH:MM"
    available: bool = True


class AvailabilityResponse(BaseModel):
    date: date
    appointment_type: AppointmentType
    available_slots: List[Slot]


class Patient(BaseModel):
    name: str = Field(..., example="John Doe")
    email: EmailStr = Field(..., example="john@example.com")
    phone: str = Field(..., example="+1-555-0100")


class BookingRequest(BaseModel):
    appointment_type: AppointmentType
    date: date
    start_time: str  # "HH:MM"
    patient: Patient
    reason: Optional[str] = Field(
        default=None,
        example="Annual checkup"
    )


class BookingDetails(BaseModel):
    booking_id: str
    appointment_type: AppointmentType
    date: date
    start_time: str
    end_time: str
    patient: Patient
    reason: Optional[str] = None


class BookingResponse(BaseModel):
    status: str = "confirmed"
    confirmation_code: str
    details: BookingDetails
