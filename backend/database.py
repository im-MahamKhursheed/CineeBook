"""
CineBook   – MongoDB Configuration & Session Management
========================================================
Uses PyMongo directly. Creates collections, indexes, and seed data automatically.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure

# ─── Configuration  ────────

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME   = os.getenv("DB_NAME", "cinebook")

# Establish a single global MongoClient
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client[DB_NAME]


# ─── Connection Verification & Dependency   

def get_db():
    """FastAPI dependency that yields the MongoDB database instance."""
    try:
        # Check connection
        client.admin.command("ping")
    except ConnectionFailure:
        print(f"[FAIL] Could not connect to MongoDB at {MONGO_URI}")
    yield db


# ─── Auto-Increment Counter Helper   ──────

def get_next_id(db_instance, collection_name: str) -> int:
    """Increment and return the next auto-increment sequence ID in a thread-safe way."""
    counter = db_instance["counters"].find_one_and_update(
        {"_id": collection_name},
        {"$inc": {"seq": 1}},
        return_document=True,
        upsert=True
    )
    return counter["seq"]


# ─── Database Initialization & Seeding   ───

def create_tables():
    """Wrapper that matches startup call signature. Triggers collection & index setup."""
    init_db(db)


def seed_demo_data(db_instance):
    """Wrapper that matches startup call signature. Runs seeder if required."""
    # Data is already seeded within init_db if missing, so this is a no-op wrapper.
    pass


def init_db(db_instance):
    """Create collections, indexes, and seed demo data in MongoDB."""
    print("=" * 60)
    print("  Initializing MongoDB Collections & Indexes...")
    print("=" * 60)

    # 1. Collections & Indexes
    db_instance["users"].create_index("username", unique=True, name="uq_username")
    db_instance["users"].create_index("email",    unique=True, name="uq_email")

    db_instance["movies"].create_index("title",     name="idx_movie_title")
    db_instance["movies"].create_index("is_active", name="idx_movie_active")

    db_instance["halls"].create_index("name", unique=True, name="uq_hall_name")

    db_instance["showtimes"].create_index(
        [("movie_id", ASCENDING), ("hall_id", ASCENDING), ("start_time", ASCENDING)],
        unique=True,
        name="uq_showtime_slot",
    )
    db_instance["showtimes"].create_index("is_active", name="idx_showtime_active")

    db_instance["bookings"].create_index(
        [("showtime_id", ASCENDING), ("seat_number", ASCENDING)],
        unique=True,
        name="uq_seat_per_showtime",
    )
    db_instance["bookings"].create_index("user_id",     name="idx_booking_user")
    db_instance["bookings"].create_index("showtime_id", name="idx_booking_showtime")
    db_instance["bookings"].create_index("status",      name="idx_booking_status")

    db_instance["payments"].create_index("booking_id",     unique=True, name="uq_payment_booking")
    db_instance["payments"].create_index("transaction_id", unique=True, name="uq_transaction_id")
    db_instance["payments"].create_index("booking_ids",   name="idx_payment_booking_ids")

    # Seat Locks collection index
    db_instance["seat_locks"].create_index(
        [("showtime_id", ASCENDING), ("seat_number", ASCENDING)],
        unique=True,
        name="uq_seat_lock",
    )

    print("[OK] Collections and indexes verified.")

    # 2. Seeding Data (Only if database is empty)
    if db_instance["users"].count_documents({}) > 0:
        print("[INFO] Database already seeded - skipping.")
        return

    import bcrypt
    def _hash(pw: str) -> str:
        return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    # Seed Users
    user_docs = [
        {
            "_id": 1,
            "username":        "admin",
            "email":           "admin@cinebook.io",
            "hashed_password": _hash("Admin@123"),
            "role":            "admin",
            "is_active":       True,
            "created_at":      now,
        },
        {
            "_id": 2,
            "username":        "alice",
            "email":           "alice@example.com",
            "hashed_password": _hash("Alice@123"),
            "role":            "user",
            "is_active":       True,
            "created_at":      now,
        },
        {
            "_id": 3,
            "username":        "bob",
            "email":           "bob@example.com",
            "hashed_password": _hash("Bob@123"),
            "role":            "user",
            "is_active":       True,
            "created_at":      now,
        },
    ]
    db_instance["users"].insert_many(user_docs)
    print("[OK] Seeded users: admin, alice, bob")

    # Seed Halls
    hall_docs = [
        {"_id": 1, "name": "Hall A", "capacity": 16, "seats_per_row": 4, "is_active": True},
        {"_id": 2, "name": "Hall B", "capacity": 24, "seats_per_row": 6, "is_active": True},
    ]
    db_instance["halls"].insert_many(hall_docs)
    print("[OK] Seeded halls: Hall A, Hall B")

    # Seed Movies with Unsplash Cinematic Image URLs
    movie_docs = [
        {
            "_id": 1,
            "title":        "Inception",
            "genre":        "Sci-Fi",
            "duration_min": 148,
            "description":  "A thief who steals corporate secrets through the use of dream-sharing technology.",
            "poster_url":   "https://images.unsplash.com/photo-1536440136628-849c177e76a1?auto=format&fit=crop&w=600&q=80",
            "is_active":    True,
            "created_at":   now,
            "updated_at":   now,
        },
        {
            "_id": 2,
            "title":        "The Dark Knight",
            "genre":        "Action",
            "duration_min": 152,
            "description":  "Batman faces the Joker, a criminal mastermind who plunges Gotham into chaos.",
            "poster_url":   "https://images.unsplash.com/photo-1509198397868-475647b2a1e5?auto=format&fit=crop&w=600&q=80",
            "is_active":    True,
            "created_at":   now,
            "updated_at":   now,
        },
        {
            "_id": 3,
            "title":        "Interstellar",
            "genre":        "Sci-Fi",
            "duration_min": 169,
            "description":  "A team of explorers travel through a wormhole in space to ensure humanity's survival.",
            "poster_url":   "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=600&q=80",
            "is_active":    True,
            "created_at":   now,
            "updated_at":   now,
        },
    ]
    db_instance["movies"].insert_many(movie_docs)
    print("[OK] Seeded movies: Inception, The Dark Knight, Interstellar")

    # Seed Showtimes
    showtime_docs = [
        {"_id": 1, "movie_id": 1, "hall_id": 1, "start_time": now + timedelta(hours=2),  "ticket_price": 12.50, "is_active": True},
        {"_id": 2, "movie_id": 1, "hall_id": 2, "start_time": now + timedelta(hours=5),  "ticket_price": 10.00, "is_active": True},
        {"_id": 3, "movie_id": 2, "hall_id": 1, "start_time": now + timedelta(hours=8),  "ticket_price": 12.50, "is_active": True},
        {"_id": 4, "movie_id": 2, "hall_id": 2, "start_time": now + timedelta(hours=11), "ticket_price": 10.00, "is_active": True},
        {"_id": 5, "movie_id": 3, "hall_id": 1, "start_time": now + timedelta(hours=14), "ticket_price": 14.00, "is_active": True},
    ]
    db_instance["showtimes"].insert_many(showtime_docs)
    print("[OK] Seeded showtimes")

    # Initialize counters for auto-increment IDs
    counter_docs = [
        {"_id": "users",     "seq": 3},
        {"_id": "movies",    "seq": 3},
        {"_id": "halls",     "seq": 2},
        {"_id": "showtimes", "seq": 5},
        {"_id": "bookings",  "seq": 0},
        {"_id": "payments",  "seq": 0},
    ]
    for doc in counter_docs:
        db_instance["counters"].update_one({"_id": doc["_id"]}, {"$set": {"seq": doc["seq"]}}, upsert=True)
    print("[OK] Initialized auto-increment counters")
    print("=" * 60)
