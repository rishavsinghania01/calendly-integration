# Calendly Integration — Mock Scheduling API (FastAPI)

This project implements **Calendly Integration**

It provides backend endpoints that simulate appointment scheduling for a medical clinic:

- Return available appointment slots
- Book appointments
- Prevent double-booking
- Handle appointment-type durations
- Return clean JSON responses

This submission only implements the **Calendly module**, as allowed in the brief.

---

## 📁 Project Structure

```text
calendly_integration/
├── main.py             # FastAPI app + endpoints + scheduling logic
├── models.py           # Pydantic models and enums
├── requirements.txt    # Dependencies
└── README.md           # This file
