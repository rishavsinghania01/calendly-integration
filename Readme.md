# Appointment Scheduling Service (Calendly-style) - FastAPI

A FastAPI backend that generates appointment availability and books slots, with double-booking prevention built into the scheduling logic.

It provides backend endpoints that simulate appointment scheduling for a medical clinic:

- Return available appointment slots
- Book appointments
- Prevent double-booking
- Handle appointment-type durations
- Return clean JSON responses


---

## 📁 Project Structure

```text
calendly_integration/
├── main.py             # FastAPI app + endpoints + scheduling logic
├── models.py           # Pydantic models and enums
├── requirements.txt    # Dependencies
└── README.md           # This file
