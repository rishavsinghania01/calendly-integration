# Appointment Scheduling Service

A small FastAPI service that generates appointment availability for a clinic and books slots, with overlap detection that works across appointment types of different lengths.

It is a focused piece of scheduling logic rather than a product: two modules, three endpoints, no database. The interesting part is how a booking request is validated, and this README is explicit about both what that logic gets right and what it deliberately does not do.

```
main.py       FastAPI app, slot generation, booking validation   (227 lines)
models.py     Pydantic request/response models and the type enum  (57 lines)
```

---

## The part worth reading

Two appointments clash when they **overlap in time**, not when they sit in the same slot on a grid. That distinction matters here because four appointment types have four different durations, so the "grid" is different for each one. A 15-minute follow-up starting at 09:15 has to conflict with a 30-minute consultation that started at 09:00, even though neither is in the other's grid.

The whole rule is one line. Here it is in the booking path, verbatim — `requested_*` is the incoming appointment, `b_start` / `b_end` an existing one:

```python
# main.py:193
if requested_start_dt < b_end and requested_end_dt > b_start:
    raise HTTPException(status_code=409, detail="Requested time slot is already booked.")
```

The availability path applies the same comparison at `main.py:96` to decide whether to mark a generated slot as taken, so a slot can never show as free and then be refused at booking time.

These are **half-open intervals** — `[start, end)`. An appointment that ends at 09:30 and one that starts at 09:30 do not overlap, so back-to-back bookings are allowed and there is no artificial gap between them.

Worked through, against an existing **09:00–09:30 consultation**:

| Requested | Interval | Overlaps? | Response |
|---|---|---|---|
| consultation 09:00 | 09:00–09:30 | identical | `409 Conflict` |
| follow-up 09:15 | 09:15–09:30 | sits inside it | `409 Conflict` |
| follow-up 09:30 | 09:30–09:45 | touches the end | `201` booked |
| physical 08:45 | 08:45–09:30 | starts before clinic opens | `400` outside hours |
| specialist 16:30 | 16:30–17:30 | ends after clinic closes | `400` outside hours |

The last two are a separate check: the request must fit entirely inside the working day, and the *end* is what fails — a 30-minute consultation at 16:30 ends at 17:00 and is accepted, while a 60-minute specialist appointment at the same time is not.

---

## Appointment types

Durations are the only thing that distinguishes the types (`main.py:38`), and they decide how many slots exist in a day. The clinic runs 09:00–17:00, which is 480 minutes:

| Type | Duration | Slots in an empty day | Last slot |
|---|---|---|---|
| `follow_up` | 15 min | 32 | 16:45–17:00 |
| `consultation` | 30 min | 16 | 16:30–17:00 |
| `physical` | 45 min | 10 | 15:45–16:30 |
| `specialist` | 60 min | 8 | 16:00–17:00 |

`physical` gets 10 slots rather than 10.67 because generation stops as soon as the next slot would run past closing time.

---

## Running it

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Interactive docs — FastAPI generates them from the Pydantic models — at `http://localhost:8000/docs`.

### Try the conflict rules yourself

```bash
# 1. an empty day: 16 consultation slots, all available
curl "localhost:8000/api/calendly/availability?date=2026-10-12&appointment_type=consultation"

# 2. book the first one
curl -X POST localhost:8000/api/calendly/book -H 'Content-Type: application/json' -d '{
  "appointment_type": "consultation", "date": "2026-10-12", "start_time": "09:00",
  "patient": {"name": "John Doe", "email": "john@example.com", "phone": "+1-555-0100"},
  "reason": "Annual checkup"
}'

# 3. a 15-minute follow-up *inside* that booking is refused with 409
curl -X POST localhost:8000/api/calendly/book -H 'Content-Type: application/json' -d '{
  "appointment_type": "follow_up", "date": "2026-10-12", "start_time": "09:15",
  "patient": {"name": "Jane Roe", "email": "jane@example.com", "phone": "+1-555-0101"}
}'

# 4. the same follow-up at 09:30 is accepted — it touches the end, it does not overlap
```

---

## API

### `GET /api/calendly/availability`

Query parameters: `date` (`YYYY-MM-DD`) and `appointment_type`.

Slots are generated on the fly for the requested type, starting at 09:00 and stepping by that type's duration. Each is marked available or not by testing it against every booking already held for that date. On today's date, slots that have already finished are omitted entirely.

```json
{
  "date": "2026-10-12",
  "appointment_type": "consultation",
  "available_slots": [
    { "start_time": "09:00", "end_time": "09:30", "available": false },
    { "start_time": "09:30", "end_time": "10:00", "available": true }
  ]
}
```

### `POST /api/calendly/book`

Four checks run in order (`main.py:162`):

1. Pydantic validates the body — unknown appointment type, malformed date or invalid email are rejected before the handler runs.
2. The appointment must fit inside 09:00–17:00, end included.
3. It must not overlap any existing booking on that date.
4. Only then is it stored, and a booking id and confirmation code returned.

```json
{
  "status": "confirmed",
  "confirmation_code": "142305",
  "details": {
    "booking_id": "APPT-20261012-001",
    "appointment_type": "consultation",
    "date": "2026-10-12",
    "start_time": "09:00",
    "end_time": "09:30",
    "patient": { "name": "John Doe", "email": "john@example.com", "phone": "+1-555-0100" },
    "reason": "Annual checkup"
  }
}
```

The client sends only `start_time`; `end_time` is derived from the appointment type so the two can never disagree.

### `GET /health`

`{"status": "ok"}`. Nothing more.

---

## What this does not do

This is the scope boundary, stated plainly because the code is short enough for anyone to check it.

**Bookings live in a dictionary in the process** (`BOOKINGS_BY_DATE`, `main.py:48`). They are lost on restart and are not shared between workers, so running this under `uvicorn --workers 2` gives each worker its own private calendar.

**The conflict check is check-then-insert, and it is not safe under concurrency.** Two requests for the same slot can both run the loop at `main.py:189`, both find nothing, and both append. This is not hypothetical even in one process: `book_appointment` is a plain `def`, so FastAPI runs it in a threadpool and two requests can genuinely interleave between the check and the write. The GIL makes the individual `append` atomic; it does nothing for a decision spread across the lines in between.

The fix is not a mutex. It is to make the database refuse the second write:

```sql
CREATE EXTENSION btree_gist;

ALTER TABLE appointments ADD CONSTRAINT no_overlap
  EXCLUDE USING gist (
    practitioner_id WITH =,
    tstzrange(starts_at, ends_at) WITH &&
  );
```

Postgres then enforces the same half-open overlap rule this code implements in Python, but atomically — the loser of a race gets a constraint violation instead of a double booking. Two things belong with it: an **idempotency key** on the booking request, so a client retry after a timeout does not create a second appointment, and **expiring holds** if the UI ever needs to reserve a slot while a patient fills in a form.

**There are no timezones.** Times are naive `"HH:MM"` strings and `date` objects throughout, and `datetime.now()` at `main.py:77` reads the server's local clock. That is fine for one clinic in one place; it breaks as soon as a patient books from another timezone or a DST transition falls inside a working day. Storing `timestamptz` in UTC and rendering in the clinic's zone is the change.

**Start times are not snapped to the grid.** `/availability` offers 09:00, 09:30, 10:00 …, but `/book` only checks working hours and overlap — so a consultation at 09:07 is accepted on an empty day and then blocks two of the offered slots. Either validate the start against the generated grid, or accept arbitrary starts deliberately.

**Ids are weaker than they look.** `booking_id` counts the bookings already held for that date (`APPT-20261012-001`), and `confirmation_code` is the current time formatted `HHMMSS` — two bookings in the same second get the same code. Both should be UUIDs, or a database sequence.

**CORS is wide open.** `allow_origins=["*"]` together with `allow_credentials=True` (`main.py:24-30`) is both permissive and self-defeating — browsers refuse to send credentials to a wildcard origin, so the combination should be an explicit origin list.

There are also no tests, no auth, no cancellation or rescheduling, and no practitioner dimension — every booking competes for one shared calendar.

---

## Why it is built this way

The brief was the scheduling logic, so everything else is deliberately absent: no database, no ORM, no auth layer. Two consequences worth naming.

Availability is **computed, not stored**. There is no table of empty slots to keep in step with reality; a slot exists because the arithmetic says it does, and it is free because no booking overlaps it. That removes a whole class of drift between "what we think is free" and "what is actually booked", at the cost of recomputing the day on every request — which is trivial for a 480-minute day and would need caching for a real practice with many practitioners.

Duration lives in **one dictionary** (`main.py:38`) and is read by both the availability path and the booking path, so the two can never disagree about how long a `physical` takes. Adding an appointment type is one line there and one enum member in `models.py`.
