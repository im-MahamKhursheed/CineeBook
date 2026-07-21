from __future__ import annotations

from datetime import datetime, timezone, timedelta
import os
import threading
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.database import Database

from .auth import (
    create_access_token,
    hash_password,
    require_admin,
    require_user,
    verify_password,
)
from .concurrency import get_context, process_booking_job, process_booking_multiple_job
from .database import create_tables, get_db, seed_demo_data, get_next_id
from .models import (
    Booking,
    BookingStatus,
    Hall,
    Movie,
    Payment,
    Showtime,
    User,
    UserRole,
)
from .schemas import (
    LoginRequest,
    MovieCreate,
    MovieOut,
    MovieUpdate,
    HallOut,
    HallCreate,
    BookRequest,
    BookResponse,
    BookMultipleRequest,
    MyTicketOut,
    RegisterRequest,
    SeatsResponse,
    SeatInfo,
    ShowtimeCreate,
    ShowtimeOut,
    ShowtimeUpdate,
    TicketOut,
    TokenResponse,
)

# ─── App Setup  ────────────

app = FastAPI(
    title="CineBook  ",
    description="Multi-movie, multi-hall seat booking with OS concurrency primitives.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "..", "frontend", "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ─── Startup  ──────────────

@app.on_event("startup")
def on_startup():
    create_tables()


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/auth/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Annotated[Database, Depends(get_db)]):
    """Create a new user account (role: user by default)."""
    if db.users.find_one({"username": payload.username}):
        raise HTTPException(400, "Username already taken.")
    if db.users.find_one({"email": payload.email}):
        raise HTTPException(400, "Email already registered.")

    user_id = get_next_id(db, "users")
    user_doc = {
        "_id": user_id,
        "username": payload.username,
        "email": payload.email,
        "hashed_password": hash_password(payload.password),
        "role": UserRole.USER.value,
        "is_active": True,
        "created_at": datetime.now(timezone.utc)
    }
    db.users.insert_one(user_doc)
    user = User(**user_doc)
    return TokenResponse(
        access_token = create_access_token(user),
        role         = user.role.value,
        username     = user.username,
    )


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Annotated[Database, Depends(get_db)]):
    """Authenticate and receive a Bearer token."""
    user_doc = db.users.find_one({"username": payload.username})
    if not user_doc or not verify_password(payload.password, user_doc["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    user = User(**user_doc)
    return TokenResponse(
        access_token = create_access_token(user),
        role         = user.role.value,
        username     = user.username,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MOVIE ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/movies", response_model=list[MovieOut])
def list_movies(db: Annotated[Database, Depends(get_db)]):
    movie_docs = db.movies.find({"is_active": True})
    return [Movie(**m) for m in movie_docs]


@app.get("/api/movies/{movie_id}", response_model=MovieOut)
def get_movie(movie_id: int, db: Annotated[Database, Depends(get_db)]):
    movie_doc = db.movies.find_one({"_id": movie_id})
    if not movie_doc:
        raise HTTPException(404, "Movie not found.")
    return Movie(**movie_doc)


@app.post("/api/movies", response_model=MovieOut, status_code=201)
def create_movie(
    payload       : MovieCreate,
    _admin        : Annotated[User, Depends(require_admin)],
    db            : Annotated[Database, Depends(get_db)],
):
    movie_id = get_next_id(db, "movies")
    now = datetime.now(timezone.utc)
    movie_doc = {
        "_id": movie_id,
        "title": payload.title,
        "description": payload.description,
        "genre": payload.genre,
        "duration_min": payload.duration_min,
        "poster_url": payload.poster_url,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    db.movies.insert_one(movie_doc)
    return Movie(**movie_doc)


@app.put("/api/movies/{movie_id}", response_model=MovieOut)
def update_movie(
    movie_id : int,
    payload  : MovieUpdate,
    _admin   : Annotated[User, Depends(require_admin)],
    db       : Annotated[Database, Depends(get_db)],
):
    movie_doc = db.movies.find_one({"_id": movie_id})
    if not movie_doc:
        raise HTTPException(404, "Movie not found.")
    
    update_data = payload.model_dump(exclude_none=True)
    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc)
        db.movies.update_one({"_id": movie_id}, {"$set": update_data})
        movie_doc = db.movies.find_one({"_id": movie_id})
        
    return Movie(**movie_doc)


@app.delete("/api/movies/{movie_id}", status_code=204)
def delete_movie(
    movie_id : int,
    _admin   : Annotated[User, Depends(require_admin)],
    db       : Annotated[Database, Depends(get_db)],
):
    """Soft-delete (sets is_active=False) to preserve booking history."""
    movie_doc = db.movies.find_one({"_id": movie_id})
    if not movie_doc:
        raise HTTPException(404, "Movie not found.")
    db.movies.update_one({"_id": movie_id}, {"$set": {"is_active": False}})


# ═══════════════════════════════════════════════════════════════════════════════
# HALL ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/halls", response_model=list[HallOut])
def list_halls(
    _admin : Annotated[User, Depends(require_admin)],
    db     : Annotated[Database, Depends(get_db)],
):
    halls = db.halls.find({"is_active": True})
    return [Hall(**h) for h in halls]


@app.post("/halls", response_model=HallOut, status_code=201)
def create_hall(
    payload : HallCreate,
    _admin  : Annotated[User, Depends(require_admin)],
    db      : Annotated[Database, Depends(get_db)],
):
    hall_id = get_next_id(db, "halls")
    hall_doc = {
        "_id": hall_id,
        "name": payload.name,
        "capacity": payload.capacity,
        "seats_per_row": payload.seats_per_row,
        "is_active": True,
    }
    db.halls.insert_one(hall_doc)
    return Hall(**hall_doc)


# ═══════════════════════════════════════════════════════════════════════════════
# SHOWTIME ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/showtimes", response_model=list[ShowtimeOut])
def list_showtimes(db: Annotated[Database, Depends(get_db)]):
    st_docs = list(db.showtimes.find({"is_active": True}))
    showtimes = []
    for st in st_docs:
        m_doc = db.movies.find_one({"_id": st["movie_id"]})
        h_doc = db.halls.find_one({"_id": st["hall_id"]})
        showtimes.append(Showtime(
            **st,
            movie=Movie(**m_doc) if m_doc else None,
            hall=Hall(**h_doc) if h_doc else None
        ))
    showtimes.sort(key=lambda x: x.start_time)
    return showtimes


@app.get("/showtimes/{showtime_id}", response_model=ShowtimeOut)
def get_showtime(showtime_id: int, db: Annotated[Database, Depends(get_db)]):
    st_doc = db.showtimes.find_one({"_id": showtime_id})
    if not st_doc:
        raise HTTPException(404, "Showtime not found.")
    m_doc = db.movies.find_one({"_id": st_doc["movie_id"]})
    h_doc = db.halls.find_one({"_id": st_doc["hall_id"]})
    return Showtime(
        **st_doc,
        movie=Movie(**m_doc) if m_doc else None,
        hall=Hall(**h_doc) if h_doc else None
    )


@app.post("/showtimes", response_model=ShowtimeOut, status_code=201)
def create_showtime(
    payload : ShowtimeCreate,
    _admin  : Annotated[User, Depends(require_admin)],
    db      : Annotated[Database, Depends(get_db)],
):
    # Verify movie and hall exist
    m_doc = db.movies.find_one({"_id": payload.movie_id})
    if not m_doc:
        raise HTTPException(400, "Invalid movie_id.")
    h_doc = db.halls.find_one({"_id": payload.hall_id})
    if not h_doc:
        raise HTTPException(400, "Invalid hall_id.")

    st_id = get_next_id(db, "showtimes")
    st_doc = {
        "_id": st_id,
        "movie_id": payload.movie_id,
        "hall_id": payload.hall_id,
        "start_time": payload.start_time,
        "ticket_price": payload.ticket_price,
        "is_active": True,
    }
    db.showtimes.insert_one(st_doc)
    return Showtime(
        **st_doc,
        movie=Movie(**m_doc),
        hall=Hall(**h_doc)
    )


@app.put("/showtimes/{showtime_id}", response_model=ShowtimeOut)
def update_showtime(
    showtime_id : int,
    payload     : ShowtimeUpdate,
    _admin      : Annotated[User, Depends(require_admin)],
    db          : Annotated[Database, Depends(get_db)],
):
    st_doc = db.showtimes.find_one({"_id": showtime_id})
    if not st_doc:
        raise HTTPException(404, "Showtime not found.")
    
    update_data = payload.model_dump(exclude_none=True)
    if update_data:
        db.showtimes.update_one({"_id": showtime_id}, {"$set": update_data})
        st_doc = db.showtimes.find_one({"_id": showtime_id})
        
    m_doc = db.movies.find_one({"_id": st_doc["movie_id"]})
    h_doc = db.halls.find_one({"_id": st_doc["hall_id"]})
    return Showtime(
        **st_doc,
        movie=Movie(**m_doc) if m_doc else None,
        hall=Hall(**h_doc) if h_doc else None
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SEATS ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

def _build_seat_map(showtime: Showtime, db: Database, current_user_id: Optional[int] = None, include_owner: bool = False) -> SeatsResponse:
    """
    Builds a complete seat map for a showtime.
    Queries confirmed bookings and active locks, and marks each seat state.
    include_owner=True populates the `booked_by` field (admin only).
    """
    hall    = showtime.hall
    spr     = hall.seats_per_row
    rows    = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    confirmed_docs = list(db.bookings.find({
        "showtime_id": showtime.id,
        "status": "confirmed"
    }))
    
    booked_map: dict[int, str] = {}
    for b in confirmed_docs:
        user_doc = db.users.find_one({"_id": b["user_id"]})
        username = user_doc["username"] if user_doc else "Unknown"
        booked_map[b["seat_number"]] = username

    # Query active locks
    now = datetime.now(timezone.utc)
    active_locks = list(db.seat_locks.find({
        "showtime_id": showtime.id,
        "expires_at": {"$gt": now}
    }))
    lock_map = {l["seat_number"]: l["user_id"] for l in active_locks}

    seats: list[SeatInfo] = []
    for n in range(1, hall.capacity + 1):
        row_letter = rows[(n - 1) // spr]
        col        = (n - 1) %  spr + 1
        label      = f"{row_letter}{col}"
        is_booked  = n in booked_map
        
        is_locked = False
        locked_by_me = False
        if n in lock_map:
            lock_uid = lock_map[n]
            if lock_uid == current_user_id:
                locked_by_me = True
            else:
                is_locked = True

        seats.append(SeatInfo(
            seat_number = n,
            seat_label  = label,
            row         = row_letter,
            col         = col,
            is_booked   = is_booked,
            booked_by   = booked_map[n] if (include_owner and is_booked) else None,
            is_locked   = is_locked,
            locked_by_me=locked_by_me,
        ))

    free = sum(1 for s in seats if not s.is_booked and not s.is_locked)
    return SeatsResponse(
        showtime_id    = showtime.id,
        movie_title    = showtime.movie.title,
        hall_name      = hall.name,
        start_time     = showtime.start_time,
        total_seats    = hall.capacity,
        free_seats     = free,
        occupied_seats = hall.capacity - free,
        seats          = seats,
    )


@app.get("/showtimes/{showtime_id}/seats", response_model=SeatsResponse)
def get_seats(
    showtime_id  : int,
    _user        : Annotated[User, Depends(require_user)],
    db           : Annotated[Database, Depends(get_db)],
):
    """User-facing seat map — shows booked/free, includes locking info."""
    st_doc = db.showtimes.find_one({"_id": showtime_id})
    if not st_doc:
        raise HTTPException(404, "Showtime not found.")
    m_doc = db.movies.find_one({"_id": st_doc["movie_id"]})
    h_doc = db.halls.find_one({"_id": st_doc["hall_id"]})
    showtime = Showtime(
        **st_doc,
        movie=Movie(**m_doc) if m_doc else None,
        hall=Hall(**h_doc) if h_doc else None
    )
    return _build_seat_map(showtime, db, current_user_id=_user.id, include_owner=False)


@app.get("/showtimes/{showtime_id}/seats/admin", response_model=SeatsResponse)
def get_seats_admin(
    showtime_id : int,
    _admin      : Annotated[User, Depends(require_admin)],
    db          : Annotated[Database, Depends(get_db)],
):
    """Admin seat map — includes which user booked each seat, plus locking info."""
    st_doc = db.showtimes.find_one({"_id": showtime_id})
    if not st_doc:
        raise HTTPException(404, "Showtime not found.")
    m_doc = db.movies.find_one({"_id": st_doc["movie_id"]})
    h_doc = db.halls.find_one({"_id": st_doc["hall_id"]})
    showtime = Showtime(
        **st_doc,
        movie=Movie(**m_doc) if m_doc else None,
        hall=Hall(**h_doc) if h_doc else None
    )
    return _build_seat_map(showtime, db, current_user_id=_admin.id, include_owner=True)


# ═══════════════════════════════════════════════════════════════════════════════
# BOOKING ROUTE — Core OS concurrency path
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/showtimes/{showtime_id}/book", response_model=BookResponse)
def book_seat(
    showtime_id  : int,
    payload      : BookRequest,
    current_user : Annotated[User, Depends(require_user)],
    db           : Annotated[Database, Depends(get_db)],
):
    st_doc = db.showtimes.find_one({"_id": showtime_id, "is_active": True})
    if not st_doc:
        raise HTTPException(404, "Showtime not found or inactive.")
    
    hall_doc = db.halls.find_one({"_id": st_doc["hall_id"]})
    if not hall_doc:
        raise HTTPException(404, "Hall not found.")

    if payload.seat_number < 1 or payload.seat_number > hall_doc["capacity"]:
        raise HTTPException(400, f"Seat {payload.seat_number} is out of range for {hall_doc['name']}.")

    # Retrieve (or lazily create) this showtime's concurrency context
    ctx = get_context(showtime_id=showtime_id, hall_capacity=hall_doc["capacity"])

    # Build job dict
    result_store : dict           = {}
    done_event   : threading.Event = threading.Event()

    job = {
        "showtime_id" : showtime_id,
        "seat_number" : payload.seat_number,
        "user_id"     : current_user.id,
        "db_factory"  : lambda: db,   # worker queries MongoDB
        "result"      : result_store,
        "event"       : done_event,
    }

    # Ensure FCFS worker is running for this showtime, then enqueue
    ctx.ensure_worker(on_job=process_booking_job)
    ctx.fcfs_queue.put(job)

    # Block HTTP handler until worker signals completion (max 10 s)
    done_event.wait(timeout=10)

    if not result_store:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Request timed out. Please try again.", "ticket": None},
        )

    if result_store["ok"]:
        return BookResponse(
            status  = "success",
            message = result_store["msg"],
            ticket  = TicketOut(**result_store["ticket"]),
        )
    else:
        return JSONResponse(
            status_code=409,
            content={"status": "error", "message": result_store["msg"], "ticket": None},
        )


# ─── Seat Locking Endpoints   ─────────────

@app.post("/showtimes/{showtime_id}/lock")
def lock_seat(
    showtime_id  : int,
    payload      : BookRequest,
    current_user : Annotated[User, Depends(require_user)],
    db           : Annotated[Database, Depends(get_db)]
):
    """Acquires a temporary lock on a seat for 5 minutes."""
    st_doc = db.showtimes.find_one({"_id": showtime_id, "is_active": True})
    if not st_doc:
        raise HTTPException(404, "Showtime not found or inactive.")
    hall_doc = db.halls.find_one({"_id": st_doc["hall_id"]})
    if not hall_doc:
        raise HTTPException(404, "Hall not found.")
    
    if payload.seat_number < 1 or payload.seat_number > hall_doc["capacity"]:
        raise HTTPException(400, "Seat number out of bounds.")
        
    # Check if seat is permanently booked
    booked = db.bookings.find_one({
        "showtime_id": showtime_id,
        "seat_number": payload.seat_number,
        "status": "confirmed"
    })
    if booked:
        raise HTTPException(409, "This seat is already booked.")
        
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=5)
    
    from pymongo.errors import DuplicateKeyError
    try:
        # Atomic check-and-upsert using query conditions
        res = db.seat_locks.update_one(
            {
                "showtime_id": showtime_id,
                "seat_number": payload.seat_number,
                "$or": [
                    {"expires_at": {"$lt": now}},
                    {"user_id": current_user.id}
                ]
            },
            {
                "$set": {
                    "user_id": current_user.id,
                    "locked_at": now,
                    "expires_at": expires_at
                }
            },
            upsert=True
        )
        
        if res.matched_count > 0 or res.upserted_id is not None:
            return {"status": "success", "message": f"Seat {payload.seat_number} locked successfully."}
        else:
            raise HTTPException(409, "This seat is currently being viewed by another user. Please select a different seat or wait until it becomes available.")
    except DuplicateKeyError:
        raise HTTPException(409, "This seat is currently being viewed by another user. Please select a different seat or wait until it becomes available.")


@app.post("/showtimes/{showtime_id}/unlock")
def unlock_seat(
    showtime_id  : int,
    payload      : BookRequest,
    current_user : Annotated[User, Depends(require_user)],
    db           : Annotated[Database, Depends(get_db)]
):
    """Releases a specific temporary seat lock held by the user."""
    db.seat_locks.delete_one({
        "showtime_id": showtime_id,
        "seat_number": payload.seat_number,
        "user_id": current_user.id
    })
    return {"status": "success", "message": f"Seat {payload.seat_number} unlocked."}


@app.post("/showtimes/{showtime_id}/unlock-all")
def unlock_all_seats(
    showtime_id  : int,
    current_user : Annotated[User, Depends(require_user)],
    db           : Annotated[Database, Depends(get_db)]
):
    """Releases all temporary seat locks held by the user for this showtime."""
    db.seat_locks.delete_many({
        "showtime_id": showtime_id,
        "user_id": current_user.id
    })
    return {"status": "success", "message": "All your seat locks released."}


@app.post("/showtimes/{showtime_id}/book-multiple", response_model=BookResponse)
def book_multiple_seats(
    showtime_id  : int,
    payload      : BookMultipleRequest,
    current_user : Annotated[User, Depends(require_user)],
    db           : Annotated[Database, Depends(get_db)],
):
    """Books multiple seats inside the per-showtime serialized FCFS worker thread."""
    if not payload.seat_numbers:
        raise HTTPException(400, "No seats selected.")
        
    st_doc = db.showtimes.find_one({"_id": showtime_id, "is_active": True})
    if not st_doc:
        raise HTTPException(404, "Showtime not found or inactive.")
    
    hall_doc = db.halls.find_one({"_id": st_doc["hall_id"]})
    if not hall_doc:
        raise HTTPException(404, "Hall not found.")
        
    for s in payload.seat_numbers:
        if s < 1 or s > hall_doc["capacity"]:
            raise HTTPException(400, f"Seat {s} is out of range.")
            
    # Retrieve context
    ctx = get_context(showtime_id=showtime_id, hall_capacity=hall_doc["capacity"])
    
    result_store = {}
    done_event = threading.Event()
    
    job = {
        "showtime_id"  : showtime_id,
        "seat_numbers" : payload.seat_numbers,
        "user_id"      : current_user.id,
        "db_factory"   : lambda: db,
        "result"       : result_store,
        "event"        : done_event,
    }
    
    ctx.ensure_worker(on_job=process_booking_multiple_job)
    ctx.fcfs_queue.put(job)
    
    # Wait for execution
    done_event.wait(timeout=15)
    
    if not result_store:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Request timed out. Please try again.", "ticket": None},
        )
        
    if result_store["ok"]:
        return BookResponse(
            status  = "success",
            message = result_store["msg"],
            ticket  = TicketOut(**result_store["ticket"]),
        )
    else:
        return JSONResponse(
            status_code=409,
            content={"status": "error", "message": result_store["msg"], "ticket": None},
        )


@app.get("/api/receipt/{booking_id}")
def get_receipt(
    booking_id   : int,
    current_user : Annotated[User, Depends(require_user)],
    db           : Annotated[Database, Depends(get_db)],
):
    """Retrieves full receipt/invoice details for a booking or booking group."""
    booking_doc = db.bookings.find_one({"_id": booking_id})
    if not booking_doc:
        raise HTTPException(404, "Booking not found.")
        
    if booking_doc["user_id"] != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(403, "Not authorized to view this receipt.")
        
    # Find payment record associated with this booking
    payment_doc = db.payments.find_one({
        "$or": [
            {"booking_ids": booking_id},
            {"booking_id": booking_id}
        ]
    })
    
    if not payment_doc:
        raise HTTPException(404, "Payment record not found for this booking.")
        
    # Find all bookings in this payment group
    booking_ids = payment_doc.get("booking_ids", [booking_id])
    all_booking_docs = list(db.bookings.find({"_id": {"$in": booking_ids}}))
    all_booking_docs.sort(key=lambda x: x["seat_number"])
    
    showtime_id = booking_doc["showtime_id"]
    st_doc = db.showtimes.find_one({"_id": showtime_id})
    if not st_doc:
        raise HTTPException(404, "Showtime not found.")
        
    m_doc = db.movies.find_one({"_id": st_doc["movie_id"]})
    h_doc = db.halls.find_one({"_id": st_doc["hall_id"]})
    
    # Derive seat labels
    spr = h_doc["seats_per_row"] if h_doc else 4
    row_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    
    selected_seats = []
    for b in all_booking_docs:
        seat_num = b["seat_number"]
        row_idx = (seat_num - 1) // spr
        col_idx = (seat_num - 1) % spr + 1
        label = f"{row_letters[row_idx]}{col_idx}"
        selected_seats.append(label)
        
    user_doc = db.users.find_one({"_id": booking_doc["user_id"]})
    username = user_doc["username"] if user_doc else "Unknown"
    
    return {
        "booking_id"       : booking_id,
        "booking_ids"      : booking_ids,
        "username"         : username,
        "movie_title"      : m_doc["title"] if m_doc else "Unknown Movie",
        "hall_name"        : h_doc["name"] if h_doc else "Unknown Hall",
        "show_timing"      : st_doc["start_time"].isoformat(),
        "selected_seats"   : ", ".join(selected_seats),
        "number_of_tickets": len(all_booking_docs),
        "total_amount"     : payment_doc["amount"],
        "payment_status"   : payment_doc["status"],
        "booking_date"     : booking_doc["booked_at"].isoformat(),
        "transaction_id"   : payment_doc.get("transaction_id", "N/A"),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# USER DASHBOARD — "My Tickets"
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/me/tickets")
def my_tickets(
    current_user : Annotated[User, Depends(require_user)],
    db           : Annotated[Database, Depends(get_db)],
):
    """
    Returns all confirmed bookings for the logged-in user.
    Includes ticket details assembled from booking + payment + showtime joins.
    """
    bookings = list(db.bookings.find({
        "user_id": current_user.id,
        "status": "confirmed"
    }).sort("booked_at", -1))

    tickets = []
    for b_doc in bookings:
        st_doc = db.showtimes.find_one({"_id": b_doc["showtime_id"]})
        if not st_doc:
            continue
        m_doc = db.movies.find_one({"_id": st_doc["movie_id"]})
        h_doc = db.halls.find_one({"_id": st_doc["hall_id"]})
        p_doc = db.payments.find_one({"booking_id": b_doc["_id"]})

        st = Showtime(**st_doc, movie=Movie(**m_doc) if m_doc else None, hall=Hall(**h_doc) if h_doc else None)
        booking = Booking(**b_doc, showtime=st)

        tickets.append({
            "booking_id"     : b_doc["_id"],
            "movie_title"    : st.movie.title if st.movie else "Unknown Movie",
            "hall_name"      : st.hall.name if st.hall else "Unknown Hall",
            "show_timing"    : st.start_time.isoformat(),
            "seat_label"     : booking.seat_label(),
            "payment_status" : p_doc["status"] if p_doc else "N/A",
            "amount_paid"    : p_doc["amount"] if p_doc else 0.0,
            "booked_at"      : booking.booked_at.isoformat(),
        })

    return {"user": current_user.username, "ticket_count": len(tickets), "tickets": tickets}


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN AUDIT ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/audit")
def audit_all(
    _admin : Annotated[User, Depends(require_admin)],
    db     : Annotated[Database, Depends(get_db)],
):
    """
    Admin view: all confirmed bookings across every movie, hall, and showtime.
    Shows which user reserved which seat.
    """
    bookings = list(db.bookings.find({"status": "confirmed"}).sort("booked_at", -1))
    return {"total": len(bookings), "bookings": _format_audit(bookings, db)}


@app.get("/admin/audit/{showtime_id}")
def audit_showtime(
    showtime_id : int,
    _admin      : Annotated[User, Depends(require_admin)],
    db          : Annotated[Database, Depends(get_db)],
):
    """Admin view: confirmed bookings for a single showtime."""
    bookings = list(db.bookings.find({
        "showtime_id": showtime_id,
        "status": "confirmed"
    }).sort("seat_number", 1))
    return {"showtime_id": showtime_id, "total": len(bookings), "bookings": _format_audit(bookings, db)}


def _format_audit(bookings: list[dict], db: Database) -> list[dict]:
    result = []
    for b_doc in bookings:
        st_doc = db.showtimes.find_one({"_id": b_doc["showtime_id"]})
        if not st_doc:
            continue
        m_doc = db.movies.find_one({"_id": st_doc["movie_id"]})
        h_doc = db.halls.find_one({"_id": st_doc["hall_id"]})
        u_doc = db.users.find_one({"_id": b_doc["user_id"]})
        p_doc = db.payments.find_one({"booking_id": b_doc["_id"]})

        st = Showtime(**st_doc, movie=Movie(**m_doc) if m_doc else None, hall=Hall(**h_doc) if h_doc else None)
        booking = Booking(**b_doc, showtime=st, user=User(**u_doc) if u_doc else None)

        result.append({
            "booking_id"     : b_doc["_id"],
            "username"       : booking.user.username if booking.user else "Unknown",
            "email"          : booking.user.email if booking.user else "",
            "movie_title"    : st.movie.title if st.movie else "Unknown Movie",
            "hall_name"      : st.hall.name if st.hall else "Unknown Hall",
            "show_timing"    : st.start_time.isoformat(),
            "seat_label"     : booking.seat_label(),
            "booking_status" : booking.status.value,
            "payment_status" : p_doc["status"] if p_doc else None,
            "amount_paid"    : p_doc["amount"] if p_doc else None,
            "booked_at"      : booking.booked_at.isoformat(),
        })
    return result


# ─── Health check  ─────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


# ═══════════════════════════════════════════════════════════════════════════════
# FRONTEND PAGE ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request

TEMPLATES_DIR = os.path.join(BASE_DIR, "..", "frontend", "templates")
print(f"DEBUG: Checking template directory at: {os.path.abspath(TEMPLATES_DIR)}")
print(f"DEBUG: Does directory exist? {os.path.isdir(TEMPLATES_DIR)}")

TEMPLATES_DIR = os.path.join(BASE_DIR, "..", "frontend", "templates")
if os.path.isdir(TEMPLATES_DIR):
    _templates = Jinja2Templates(directory=TEMPLATES_DIR)
    _templates.env.cache = None

    @app.get("/", response_class=HTMLResponse)
    @app.get("/index.html", response_class=HTMLResponse)
    def page_index(request: Request):
        return _templates.TemplateResponse(request=request, name="index.html", context={"request": request})

    # # Add this to main.py to  handle both URLs
    # @app.get("/movies", response_class=HTMLResponse)
    # def page_movies_clean(request: Request):
    #     return _templates.TemplateResponse(request=request, name="movies.html", context={"request": request})

    @app.get("/movies", response_class=HTMLResponse)
    @app.get("/movies.html", response_class=HTMLResponse)
    def page_movies(request: Request):
        return _templates.TemplateResponse(request=request, name="movies.html", context={"request": request})

    @app.get("/booking", response_class=HTMLResponse)
    @app.get("/booking.html", response_class=HTMLResponse)
    def page_booking(request: Request):
        return _templates.TemplateResponse(request=request, name="booking.html", context={"request": request})

    @app.get("/dashboard", response_class=HTMLResponse)
    @app.get("/dashboard.html", response_class=HTMLResponse)
    def page_dashboard(request: Request):
        return _templates.TemplateResponse(request=request, name="dashboard.html", context={"request": request})

    @app.get("/admin", response_class=HTMLResponse)
    @app.get("/admin.html", response_class=HTMLResponse)
    def page_admin(request: Request):
        return _templates.TemplateResponse(request=request, name="admin.html", context={"request": request})

    @app.get("/login", response_class=HTMLResponse)
    @app.get("/login.html", response_class=HTMLResponse)
    def page_login(request: Request):
        return _templates.TemplateResponse(request=request, name="login.html", context={"request": request})

    @app.get("/register", response_class=HTMLResponse)
    @app.get("/register.html", response_class=HTMLResponse)
    def page_register(request: Request):
        return _templates.TemplateResponse(request=request, name="register.html", context={"request": request})
 
    @app.get("/about", response_class=HTMLResponse)
    @app.get("/about.html", response_class=HTMLResponse)
    def page_about(request: Request):
        return _templates.TemplateResponse(request=request, name="about.html", context={"request": request})

    @app.get("/faq", response_class=HTMLResponse)
    @app.get("/faq.html", response_class=HTMLResponse)
    def page_faq(request: Request):
        return _templates.TemplateResponse(request=request, name="faq.html", context={"request": request})

    @app.get("/contact", response_class=HTMLResponse)
    @app.get("/contact.html", response_class=HTMLResponse)
    def page_contact(request: Request):
        return _templates.TemplateResponse(request=request, name="contact.html", context={"request": request})