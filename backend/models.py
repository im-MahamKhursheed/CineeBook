"""
CineBook   – Python Models (MongoDB Compatibility)
===================================================
Redefined to remove SQLAlchemy mapping while preserving full property/attribute compatibility
with existing business logic.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional, Any


# ─── Enums  ───────────────

class UserRole(str, enum.Enum):
    USER  = "user"
    ADMIN = "admin"


class BookingStatus(str, enum.Enum):
    PENDING   = "pending"
    CONFIRMED = "confirmed"
    FAILED    = "failed"


class PaymentStatus(str, enum.Enum):
    PENDING   = "pending"
    COMPLETED = "completed"
    REFUNDED  = "refunded"


# ─── Model Classes  ───────

def _parse_datetime(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class User:
    def __init__(
        self,
        _id: Optional[int] = None,
        id: Optional[int] = None,
        username: str = "",
        email: str = "",
        hashed_password: str = "",
        role: UserRole | str = UserRole.USER,
        is_active: bool = True,
        created_at: Any = None,
        **kwargs: Any,
    ):
        self.id = _id if _id is not None else id
        self.username = username
        self.email = email
        self.hashed_password = hashed_password
        self.role = UserRole(role) if isinstance(role, str) else role
        self.is_active = is_active
        self.created_at = _parse_datetime(created_at) or datetime.now(timezone.utc)
        self.bookings: list[Booking] = []

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role}>"


class Movie:
    def __init__(
        self,
        _id: Optional[int] = None,
        id: Optional[int] = None,
        title: str = "",
        description: Optional[str] = None,
        genre: Optional[str] = None,
        duration_min: int = 0,
        poster_url: Optional[str] = None,
        is_active: bool = True,
        created_at: Any = None,
        updated_at: Any = None,
        **kwargs: Any,
    ):
        self.id = _id if _id is not None else id
        self.title = title
        self.description = description
        self.genre = genre
        self.duration_min = duration_min
        self.poster_url = poster_url
        self.is_active = is_active
        self.created_at = _parse_datetime(created_at) or datetime.now(timezone.utc)
        self.updated_at = _parse_datetime(updated_at) or datetime.now(timezone.utc)
        self.showtimes: list[Showtime] = []

    def __repr__(self) -> str:
        return f"<Movie id={self.id} title={self.title!r}>"


class Hall:
    def __init__(
        self,
        _id: Optional[int] = None,
        id: Optional[int] = None,
        name: str = "",
        capacity: int = 0,
        seats_per_row: int = 4,
        is_active: bool = True,
        **kwargs: Any,
    ):
        self.id = _id if _id is not None else id
        self.name = name
        self.capacity = capacity
        self.seats_per_row = seats_per_row
        self.is_active = is_active
        self.showtimes: list[Showtime] = []

    def __repr__(self) -> str:
        return f"<Hall id={self.id} name={self.name!r} capacity={self.capacity}>"


class Showtime:
    def __init__(
        self,
        _id: Optional[int] = None,
        id: Optional[int] = None,
        movie_id: int = 0,
        hall_id: int = 0,
        start_time: Any = None,
        ticket_price: float = 0.0,
        is_active: bool = True,
        movie: Optional[Movie] = None,
        hall: Optional[Hall] = None,
        **kwargs: Any,
    ):
        self.id = _id if _id is not None else id
        self.movie_id = movie_id
        self.hall_id = hall_id
        self.start_time = _parse_datetime(start_time)
        self.ticket_price = ticket_price
        self.is_active = is_active
        self.movie = movie
        self.hall = hall
        self.bookings: list[Booking] = []

    def __repr__(self) -> str:
        return f"<Showtime id={self.id} movie_id={self.movie_id} hall_id={self.hall_id} start={self.start_time}>"


class Booking:
    def __init__(
        self,
        _id: Optional[int] = None,
        id: Optional[int] = None,
        user_id: int = 0,
        showtime_id: int = 0,
        seat_number: int = 0,
        status: BookingStatus | str = BookingStatus.PENDING,
        booked_at: Any = None,
        user: Optional[User] = None,
        showtime: Optional[Showtime] = None,
        payment: Optional[Payment] = None,
        **kwargs: Any,
    ):
        self.id = _id if _id is not None else id
        self.user_id = user_id
        self.showtime_id = showtime_id
        self.seat_number = seat_number
        self.status = BookingStatus(status) if isinstance(status, str) else status
        self.booked_at = _parse_datetime(booked_at) or datetime.now(timezone.utc)
        self.user = user
        self.showtime = showtime
        self.payment = payment

    def seat_label(self) -> str:
        if not self.showtime or not self.showtime.hall:
            return f"Seat {self.seat_number}"
        spr = self.showtime.hall.seats_per_row
        row_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        row_idx = (self.seat_number - 1) // spr
        col_idx = (self.seat_number - 1) %  spr + 1
        return f"{row_letters[row_idx]}{col_idx}"

    def __repr__(self) -> str:
        return f"<Booking id={self.id} user={self.user_id} seat={self.seat_number} status={self.status}>"


class Payment:
    def __init__(
        self,
        _id: Optional[int] = None,
        id: Optional[int] = None,
        booking_id: int = 0,
        amount: float = 0.0,
        currency: str = "USD",
        status: PaymentStatus | str = PaymentStatus.COMPLETED,
        transaction_id: str = "",
        paid_at: Any = None,
        booking: Optional[Booking] = None,
        **kwargs: Any,
    ):
        self.id = _id if _id is not None else id
        self.booking_id = booking_id
        self.amount = amount
        self.currency = currency
        self.status = PaymentStatus(status) if isinstance(status, str) else status
        self.transaction_id = transaction_id
        self.paid_at = _parse_datetime(paid_at) or datetime.now(timezone.utc)
        self.booking = booking

    def __repr__(self) -> str:
        return f"<Payment id={self.id} booking={self.booking_id} amount={self.amount} status={self.status}>"
