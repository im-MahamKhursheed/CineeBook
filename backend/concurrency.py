"""
CineBook   – OS Concurrency Engine (per showtime context)

Threading model
---------------
  • One daemon worker thread per ConcurrencyContext (per showtime).
  • Workers are started lazily on first booking for that showtime.
  • Workers run for the process lifetime (daemon=True → auto-exit on shutdown).
  • The _context_lock guards the _contexts registry itself (meta-lock).
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


# Per-showtime context  

@dataclass
class ConcurrencyContext:
    showtime_id : int
    capacity    : int                          # Hall.capacity → Semaphore ceiling

    mutex       : threading.Lock              = field(default_factory=threading.Lock)
    fcfs_queue  : queue.Queue                 = field(default_factory=queue.Queue)
    _semaphore  : Optional[threading.Semaphore] = field(default=None, init=False)
    _worker     : Optional[threading.Thread]  = field(default=None, init=False)
    _started    : bool                        = field(default=False, init=False)

    def __post_init__(self):
        self._semaphore = threading.Semaphore(self.capacity)

    #  Semaphore helpers (expose without leaking internals) 

    def acquire_capacity(self, timeout: float = 5.0) -> bool:
        """Semaphore.acquire — returns False if hall is fully booked."""
        return self._semaphore.acquire(blocking=True, timeout=timeout)

    def release_capacity(self):
        """Release one semaphore permit (seat released / booking failed)."""
        self._semaphore.release()

    #  Worker lifecycle  ─

    def ensure_worker(self, on_job):
        """
        Start the FCFS worker thread for this context if not already running.
        `on_job` is a callable that receives a job dict and processes it.
        Thread-safe: guarded by _started flag + a local lock.
        """
        if self._started:
            return
        self._worker = threading.Thread(
            target=self._worker_loop,
            args=(on_job,),
            daemon=True,
            name=f"fcfs-showtime-{self.showtime_id}",
        )
        self._worker.start()
        self._started = True

    def _worker_loop(self, on_job):
        while True:
            job = self.fcfs_queue.get()
            if job is None:                 # sentinel for graceful shutdown
                break
            try:
                on_job(self, job)
            finally:
                self.fcfs_queue.task_done()


# Global context registry 

_contexts: dict[int, ConcurrencyContext] = {}
_context_lock = threading.Lock()          # protects the dict itself


def get_context(showtime_id: int, hall_capacity: int) -> ConcurrencyContext:
    """
    Return (and lazily create) the ConcurrencyContext for a given showtime.
    Idempotent — calling with the same showtime_id always returns the same object.
    """
    with _context_lock:
        if showtime_id not in _contexts:
            ctx = ConcurrencyContext(showtime_id=showtime_id, capacity=hall_capacity)
            _contexts[showtime_id] = ctx
        return _contexts[showtime_id]


# Core booking job processor 

def process_booking_job(ctx: ConcurrencyContext, job: dict):
    """
    Called by each showtime's FCFS worker thread.

    job = {
        "showtime_id" : int,
        "seat_number" : int,
        "user_id"     : int,
        "db_factory"  : Callable[[], Database],
        "result"      : dict,           # written by this function
        "event"       : threading.Event
    }
    """
    from datetime import datetime, timezone
    from pymongo.errors import DuplicateKeyError
    from .models import Booking, BookingStatus, Showtime as ST, Movie, Hall, Payment, PaymentStatus, User
    from .database import get_next_id

    seat_number  = job["seat_number"]
    user_id      = job["user_id"]
    showtime_id  = job["showtime_id"]
    db_factory   = job["db_factory"]
    result_store = job["result"]
    done_event   = job["event"]

    # Step 1: Semaphore (capacity gate) 
    if not ctx.acquire_capacity(timeout=5.0):
        result_store.update({"ok": False, "msg": "Hall is fully booked — no seats available."})
        done_event.set()
        return

    db = db_factory()
    try:
        # Step 2: Mutex (critical section) 
        with ctx.mutex:
            # Check if seat is already CONFIRMED for this showtime
            existing = db.bookings.find_one({
                "showtime_id": showtime_id,
                "seat_number": seat_number,
                "status": "confirmed"
            })
            if existing:
                ctx.release_capacity()
                result_store.update({"ok": False, "msg": f"Seat {seat_number} is already taken for this show."})
                done_event.set()
                return

            # Validate seat number against hall capacity
            st_doc = db.showtimes.find_one({"_id": showtime_id})
            if not st_doc:
                ctx.release_capacity()
                result_store.update({"ok": False, "msg": "Showtime not found."})
                done_event.set()
                return

            hall_doc = db.halls.find_one({"_id": st_doc["hall_id"]})
            if not hall_doc:
                ctx.release_capacity()
                result_store.update({"ok": False, "msg": "Hall not found."})
                done_event.set()
                return

            if seat_number < 1 or seat_number > hall_doc["capacity"]:
                ctx.release_capacity()
                result_store.update({"ok": False, "msg": f"Seat {seat_number} does not exist in {hall_doc['name']}."})
                done_event.set()
                return

            # Reconstruct Showtime object for attribute access compatibility
            movie_doc = db.movies.find_one({"_id": st_doc["movie_id"]})
            showtime = ST(
                **st_doc,
                movie=Movie(**movie_doc) if movie_doc else None,
                hall=Hall(**hall_doc) if hall_doc else None
            )

            #  ATOMIC write (inside mutex) 
            booking_id = get_next_id(db, "bookings")
            booking_doc = {
                "_id": booking_id,
                "user_id": user_id,
                "showtime_id": showtime_id,
                "seat_number": seat_number,
                "status": "confirmed",
                "booked_at": datetime.now(timezone.utc)
            }
            try:
                db.bookings.insert_one(booking_doc)
            except DuplicateKeyError:
                ctx.release_capacity()
                result_store.update({"ok": False, "msg": f"Seat {seat_number} was just taken by another user."})
                done_event.set()
                return

            # Derive label
            spr       = showtime.hall.seats_per_row
            row_idx   = (seat_number - 1) // spr
            col_idx   = (seat_number - 1) %  spr + 1
            seat_label = f"{'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[row_idx]}{col_idx}"

        # ── Step 3: Payment (outside mutex ─ no shared-state risk) ───────────
        import uuid
        payment_id = get_next_id(db, "payments")
        payment_doc = {
            "_id": payment_id,
            "booking_id": booking_id,
            "amount": showtime.ticket_price,
            "currency": "USD",
            "status": "completed",
            "transaction_id": str(uuid.uuid4()),
            "paid_at": datetime.now(timezone.utc)
        }
        db.payments.insert_one(payment_doc)

        # ── Step 4: Build ticket summary   
        user_doc = db.users.find_one({"_id": user_id})
        user = User(**user_doc) if user_doc else None

        booking = Booking(**booking_doc, showtime=showtime, user=user)
        payment = Payment(**payment_doc)

        ticket = build_ticket(booking, payment, showtime, seat_label)
        result_store.update({"ok": True, "msg": f"Seat {seat_label} successfully booked!", "ticket": ticket})

    except Exception as exc:
        ctx.release_capacity()
        result_store.update({"ok": False, "msg": f"Internal error: {exc}"})
    finally:
        done_event.set()


# Ticket builder  

def build_ticket(booking, payment, showtime, seat_label: str) -> dict:
    """
    Assembles the digital ticket summary returned after a successful POST /book/.

    The ticket is a pure data dict — rendering (PDF, email, HTML badge)
    is the frontend's responsibility.

    Fields
    ------
    ticket_id        : Booking primary key (opaque reference number)
    movie_title      : Human-readable film name
    hall_name        : e.g. "Hall A"
    show_timing      : ISO-8601 datetime string of the screening
    seat_number      : Integer index (e.g. 5)
    seat_label       : Human-readable label (e.g. "B2")
    passenger_name   : Username of the booker
    payment_status   : "completed" / "pending"
    amount_paid      : Numeric ticket price
    currency         : "USD"
    transaction_id   : UUID4 payment reference
    booked_at        : ISO-8601 booking timestamp
    """
    return {
        "ticket_id"      : booking.id,
        "movie_title"    : showtime.movie.title,
        "hall_name"      : showtime.hall.name,
        "show_timing"    : showtime.start_time.isoformat(),
        "seat_number"    : booking.seat_number,
        "seat_label"     : seat_label,
        "passenger_name" : booking.user.username,
        "payment_status" : payment.status.value,
        "amount_paid"    : payment.amount,
        "currency"       : payment.currency,
        "transaction_id" : payment.transaction_id,
        "booked_at"      : booking.booked_at.isoformat(),
    }


def process_booking_multiple_job(ctx: ConcurrencyContext, job: dict):
    """
    Called by each showtime's FCFS worker thread to book multiple seats.

    job = {
        "showtime_id"  : int,
        "seat_numbers" : list[int],
        "user_id"      : int,
        "db_factory"   : Callable[[], Database],
        "result"       : dict,           # written by this function
        "event"        : threading.Event
    }
    """
    from datetime import datetime, timezone
    from pymongo.errors import DuplicateKeyError
    from .models import Booking, BookingStatus, Showtime as ST, Movie, Hall, Payment, PaymentStatus, User
    from .database import get_next_id

    seat_numbers = job["seat_numbers"]
    user_id      = job["user_id"]
    showtime_id  = job["showtime_id"]
    db_factory   = job["db_factory"]
    result_store = job["result"]
    done_event   = job["event"]

    # Step 1: Semaphore (capacity gate for all requested seats) 
    acquired = 0
    success = True
    for _ in range(len(seat_numbers)):
        if ctx.acquire_capacity(timeout=5.0):
            acquired += 1
        else:
            success = False
            break

    if not success:
        # Release any permits we already acquired to avoid leak
        for _ in range(acquired):
            ctx.release_capacity()
        result_store.update({"ok": False, "msg": "Hall does not have enough seats available."})
        done_event.set()
        return

    db = db_factory()
    try:
        # Step 2: Mutex (critical section) 
        with ctx.mutex:
            # Check if any seat is already CONFIRMED for this showtime
            already_booked = list(db.bookings.find({
                "showtime_id": showtime_id,
                "seat_number": {"$in": seat_numbers},
                "status": "confirmed"
            }))
            if already_booked:
                for _ in range(acquired):
                    ctx.release_capacity()
                booked_seats_str = ", ".join(str(b["seat_number"]) for b in already_booked)
                result_store.update({"ok": False, "msg": f"Seats {booked_seats_str} are already taken for this show."})
                done_event.set()
                return

            # Check if any seat is locked by another user (lock not expired, user_id != current_user)
            now = datetime.now(timezone.utc)
            active_locks = list(db.seat_locks.find({
                "showtime_id": showtime_id,
                "seat_number": {"$in": seat_numbers},
                "expires_at": {"$gt": now}
            }))
            other_locks = [l for l in active_locks if l["user_id"] != user_id]
            if other_locks:
                for _ in range(acquired):
                    ctx.release_capacity()
                other_locked_seats_str = ", ".join(str(l["seat_number"]) for l in other_locks)
                result_store.update({"ok": False, "msg": f"Seats {other_locked_seats_str} are currently viewed by another user."})
                done_event.set()
                return

            # Validate seat numbers against hall capacity
            st_doc = db.showtimes.find_one({"_id": showtime_id})
            if not st_doc:
                for _ in range(acquired):
                    ctx.release_capacity()
                result_store.update({"ok": False, "msg": "Showtime not found."})
                done_event.set()
                return

            hall_doc = db.halls.find_one({"_id": st_doc["hall_id"]})
            if not hall_doc:
                for _ in range(acquired):
                    ctx.release_capacity()
                result_store.update({"ok": False, "msg": "Hall not found."})
                done_event.set()
                return

            for s in seat_numbers:
                if s < 1 or s > hall_doc["capacity"]:
                    for _ in range(acquired):
                        ctx.release_capacity()
                    result_store.update({"ok": False, "msg": f"Seat {s} does not exist in {hall_doc['name']}."})
                    done_event.set()
                    return

            # Reconstruct objects
            movie_doc = db.movies.find_one({"_id": st_doc["movie_id"]})
            showtime = ST(
                **st_doc,
                movie=Movie(**movie_doc) if movie_doc else None,
                hall=Hall(**hall_doc) if hall_doc else None
            )
            # ATOMIC insert multiple bookings
            booking_ids = []
            booking_docs = []
            for s in seat_numbers:
                booking_id = get_next_id(db, "bookings")
                booking_ids.append(booking_id)
                booking_doc = {
                    "_id": booking_id,
                    "user_id": user_id,
                    "showtime_id": showtime_id,
                    "seat_number": s,
                    "status": "confirmed",
                    "booked_at": datetime.now(timezone.utc)
                }
                booking_docs.append(booking_doc)

            try:
                db.bookings.insert_many(booking_docs)
            except DuplicateKeyError:
                for _ in range(acquired):
                    ctx.release_capacity()
                result_store.update({"ok": False, "msg": "One or more seats were just taken by another user."})
                done_event.set()
                return

            # Release the temporary seat locks for this user
            db.seat_locks.delete_many({
                "showtime_id": showtime_id,
                "seat_number": {"$in": seat_numbers},
                "user_id": user_id
            })

            # Derive labels
            spr = showtime.hall.seats_per_row
            row_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            seat_labels = []
            for s in seat_numbers:
                row_idx = (s - 1) // spr
                col_idx = (s - 1) % spr + 1
                seat_labels.append(f"{row_letters[row_idx]}{col_idx}")

        #  Step 3: Payment (outside mutex) 
        import uuid
        payment_id = get_next_id(db, "payments")
        total_amount = showtime.ticket_price * len(seat_numbers)
        payment_doc = {
            "_id": payment_id,
            "booking_id": booking_ids[0],  # legacy field compatibility
            "booking_ids": booking_ids,    # new list field
            "amount": total_amount,
            "currency": "USD",
            "status": "completed",
            "transaction_id": str(uuid.uuid4()),
            "paid_at": datetime.now(timezone.utc)
        }
        db.payments.insert_one(payment_doc)

        # Step 4: Build response  
        user_doc = db.users.find_one({"_id": user_id})
        username = user_doc["username"] if user_doc else "Unknown"

        result_store.update({
            "ok": True,
            "msg": f"Seats {', '.join(seat_labels)} successfully booked!",
            "ticket": {
                "ticket_id": booking_ids[0],  # main booking id
                "booking_ids": booking_ids,
                "movie_title": showtime.movie.title,
                "hall_name": showtime.hall.name,
                "show_timing": showtime.start_time.isoformat(),
                "seat_number": seat_numbers[0],  # first seat
                "seat_numbers": seat_numbers,
                "seat_label": seat_labels[0],   # first label
                "seat_labels": seat_labels,
                "passenger_name": username,
                "payment_status": "completed",
                "amount_paid": total_amount,
                "currency": "USD",
                "transaction_id": payment_doc["transaction_id"],
                "booked_at": payment_doc["paid_at"].isoformat()
            }
        })

    except Exception as exc:
        for _ in range(acquired):
            ctx.release_capacity()
        result_store.update({"ok": False, "msg": f"Internal error: {exc}"})
    finally:
        done_event.set()
