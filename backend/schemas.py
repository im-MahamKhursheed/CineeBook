"""
CineBook   – Pydantic Schemas (Request & Response models)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ─── Auth  ────────────────

class RegisterRequest(BaseModel):
    username : str        = Field(..., min_length=3, max_length=50)
    email    : EmailStr
    password : str        = Field(..., min_length=8)


class LoginRequest(BaseModel):
    username : str
    password : str


class TokenResponse(BaseModel):
    access_token : str
    token_type   : str = "bearer"
    role         : str
    username     : str


# ─── Movies  ──────────────

class MovieCreate(BaseModel):
    title        : str          = Field(..., max_length=200)
    description  : Optional[str] = None
    genre        : Optional[str] = None
    duration_min : int          = Field(..., gt=0)
    poster_url   : Optional[str] = None


class MovieUpdate(BaseModel):
    title        : Optional[str] = None
    description  : Optional[str] = None
    genre        : Optional[str] = None
    duration_min : Optional[int] = None
    poster_url   : Optional[str] = None
    is_active    : Optional[bool] = None


class MovieOut(BaseModel):
    id           : int
    title        : str
    description  : Optional[str]
    genre        : Optional[str]
    duration_min : int
    poster_url   : Optional[str]
    is_active    : bool
    created_at   : datetime

    model_config = {"from_attributes": True}


# ─── Halls  ───────────────

class HallCreate(BaseModel):
    name          : str = Field(..., max_length=100)
    capacity      : int = Field(..., gt=0)
    seats_per_row : int = Field(default=4, gt=0)


class HallOut(BaseModel):
    id            : int
    name          : str
    capacity      : int
    seats_per_row : int
    is_active     : bool

    model_config = {"from_attributes": True}


# ─── Showtimes  ────────────

class ShowtimeCreate(BaseModel):
    movie_id     : int
    hall_id      : int
    start_time   : datetime
    ticket_price : float = Field(..., ge=0)


class ShowtimeUpdate(BaseModel):
    start_time   : Optional[datetime] = None
    ticket_price : Optional[float]    = None
    is_active    : Optional[bool]     = None


class ShowtimeOut(BaseModel):
    id           : int
    movie_id     : int
    hall_id      : int
    start_time   : datetime
    ticket_price : float
    is_active    : bool
    movie        : MovieOut
    hall         : HallOut

    model_config = {"from_attributes": True}


# ─── Seats  ───────────────

class SeatInfo(BaseModel):
    seat_number : int
    seat_label  : str
    row         : str
    col         : int
    is_booked   : bool
    booked_by   : Optional[str] = None   # username, visible to admin only
    is_locked   : bool = False           # Locked by another user
    locked_by_me: bool = False           # Locked by current user


class BookMultipleRequest(BaseModel):
    seat_numbers: list[int]


class SeatsResponse(BaseModel):
    showtime_id  : int
    movie_title  : str
    hall_name    : str
    start_time   : datetime
    total_seats  : int
    free_seats   : int
    occupied_seats: int
    seats        : list[SeatInfo]


# ─── Booking  ─────────────

class BookRequest(BaseModel):
    seat_number : int = Field(..., gt=0)


class TicketOut(BaseModel):
    ticket_id      : int
    movie_title    : str
    hall_name      : str
    show_timing    : str
    seat_number    : int
    seat_label     : str
    passenger_name : str
    payment_status : str
    amount_paid    : float
    currency       : str
    transaction_id : str
    booked_at      : str


class BookResponse(BaseModel):
    status  : str
    message : str
    ticket  : Optional[TicketOut] = None


# ─── My Tickets  ──────────

class MyTicketOut(BaseModel):
    booking_id     : int
    movie_title    : str
    hall_name      : str
    show_timing    : datetime
    seat_label     : str
    payment_status : str
    amount_paid    : float
    booked_at      : datetime

    model_config = {"from_attributes": True}


# ─── Admin Audit  ─────────

class AuditEntry(BaseModel):
    booking_id     : int
    username       : str
    email          : str
    movie_title    : str
    hall_name      : str
    show_timing    : datetime
    seat_label     : str
    booking_status : str
    payment_status : Optional[str]
    amount_paid    : Optional[float]
    booked_at      : datetime
