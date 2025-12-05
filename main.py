# main.py
from datetime import datetime, time, timedelta, date
from typing import Dict, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from models import (
    AppointmentType,
    Slot,
    AvailabilityResponse,
    BookingRequest,
    BookingResponse,
    BookingDetails,
    Patient,
)

app = FastAPI(
    title="Mock Calendly Integration - Medical Clinic",
    description="Simulated availability & booking endpoints for a medical clinic.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Configuration / Mock Data ----

WORK_DAY_START = time(9, 0)   # 09:00
WORK_DAY_END = time(17, 0)    # 17:00

# Appointment type durations in minutes
APPOINTMENT_DURATIONS: Dict[AppointmentType, int] = {
    AppointmentType.consultation: 30,
    AppointmentType.follow_up: 15,
    AppointmentType.physical: 45,
    AppointmentType.specialist: 60,
}

# In-memory storage of bookings:
#   key: date
#   value: list of BookingDetails
BOOKINGS_BY_DATE: Dict[date, List[BookingDetails]] = {}


# ---- Helper Functions ----

def get_duration_for_type(appointment_type: AppointmentType) -> timedelta:
    """Return timedelta duration for a given appointment type."""
    minutes = APPOINTMENT_DURATIONS[appointment_type]
    return timedelta(minutes=minutes)


def generate_daily_slots(
    target_date: date,
    appointment_type: AppointmentType
) -> List[Slot]:
    """
    Generate all potential slots for a given date and appointment type,
    marking which are available vs booked.
    """
    duration = get_duration_for_type(appointment_type)
    day_start = datetime.combine(target_date, WORK_DAY_START)
    day_end = datetime.combine(target_date, WORK_DAY_END)

    existing_bookings = BOOKINGS_BY_DATE.get(target_date, [])

    slots: List[Slot] = []
    current_start = day_start


    now = datetime.now()
    ignore_past = (target_date == now.date())

    while current_start + duration <= day_end:
        current_end = current_start + duration

        # Skip past times on the current day
        if ignore_past and current_end <= now:
            current_start = current_end
            continue

        # Check if this slot overlaps any existing booking
        slot_available = True
        for booking in existing_bookings:
            b_start = datetime.combine(target_date, _parse_time_str(booking.start_time))
            b_end = datetime.combine(target_date, _parse_time_str(booking.end_time))

            # Time ranges overlap if:
            # start < other_end AND end > other_start
            if current_start < b_end and current_end > b_start:
                slot_available = False
                break

        slots.append(
            Slot(
                start_time=current_start.strftime("%H:%M"),
                end_time=current_end.strftime("%H:%M"),
                available=slot_available,
            )
        )

        current_start = current_end

    return slots


def _parse_time_str(time_str: str) -> time:
    """Parse HH:MM string to time object."""
    return datetime.strptime(time_str, "%H:%M").time()


def _generate_booking_id(target_date: date, index: int) -> str:
    """Simple booking ID generator (can be improved as needed)."""
    return f"APPT-{target_date.strftime('%Y%m%d')}-{index:03d}"


def _generate_confirmation_code() -> str:
    """Very simple confirmation code generator."""
    return datetime.now().strftime("%H%M%S")


# ---- Endpoints ----

@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok", "message": "Service is up."}


@app.get(
    "/api/calendly/availability",
    response_model=AvailabilityResponse,
    tags=["calendly"],
)
def get_availability(
    date_param: date = Query(..., alias="date", description="Date for which to fetch availability (YYYY-MM-DD)"),
    appointment_type: AppointmentType = Query(..., description="Type of appointment."),
):
    """
    Return available and booked slots for a given date and appointment type.
    """

    slots = generate_daily_slots(date_param, appointment_type)

    return AvailabilityResponse(
        date=date_param,
        appointment_type=appointment_type,
        available_slots=slots,
    )


@app.post(
    "/api/calendly/book",
    response_model=BookingResponse,
    tags=["calendly"],
)
def book_appointment(payload: BookingRequest):
    """
    Book an appointment for a given date, time, and appointment type.
    """

    # Validate slot exists and is available
    requested_date = payload.date
    requested_type = payload.appointment_type
    requested_start_time = _parse_time_str(payload.start_time)
    duration = get_duration_for_type(requested_type)

    day_start = datetime.combine(requested_date, WORK_DAY_START)
    day_end = datetime.combine(requested_date, WORK_DAY_END)

    # Ensure requested time is within working hours
    requested_start_dt = datetime.combine(requested_date, requested_start_time)
    requested_end_dt = requested_start_dt + duration

    if requested_start_dt < day_start or requested_end_dt > day_end:
        raise HTTPException(
            status_code=400,
            detail="Requested time is outside clinic working hours.",
        )

    # Check slot availability using existing bookings
    existing_bookings = BOOKINGS_BY_DATE.get(requested_date, [])

    for booking in existing_bookings:
        b_start = datetime.combine(requested_date, _parse_time_str(booking.start_time))
        b_end = datetime.combine(requested_date, _parse_time_str(booking.end_time))

        if requested_start_dt < b_end and requested_end_dt > b_start:
            # Overlaps existing booking
            raise HTTPException(
                status_code=409,
                detail="Requested time slot is already booked.",
            )

    # If we reach here, slot is available -> create booking
    index = len(existing_bookings) + 1
    booking_id = _generate_booking_id(requested_date, index)
    confirmation_code = _generate_confirmation_code()

    start_str = payload.start_time
    end_str = requested_end_dt.strftime("%H:%M")

    booking_details = BookingDetails(
        booking_id=booking_id,
        appointment_type=requested_type,
        date=requested_date,
        start_time=start_str,
        end_time=end_str,
        patient=payload.patient,
        reason=payload.reason,
    )

    # Store in memory
    if requested_date not in BOOKINGS_BY_DATE:
        BOOKINGS_BY_DATE[requested_date] = []
    BOOKINGS_BY_DATE[requested_date].append(booking_details)

    return BookingResponse(
        status="confirmed",
        confirmation_code=confirmation_code,
        details=booking_details,
    )
