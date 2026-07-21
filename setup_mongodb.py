"""
CineBook   — MongoDB Database Setup Script
=============================================
Creates a 'cinebook' MongoDB database with collections, indexes, and seed data
that mirrors the existing SQLite/SQLAlchemy schema.

Prerequisites:
    pip install pymongo
    MongoDB running on localhost:27017 (default)

Usage:
    python setup_mongodb.py
"""

import sys

# Ensure stdout supports unicode characters to prevent UnicodeEncodeError on Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass
from datetime import datetime, timezone, timedelta
from uuid import uuid4

try:
    from pymongo import MongoClient, ASCENDING
    from pymongo.errors import ConnectionFailure, DuplicateKeyError
except ImportError:
    print("ERROR: pymongo is not installed.")
    print("Install it with:  pip install pymongo")
    sys.exit(1)

# ─── Configuration  ────────

MONGO_URI = "mongodb://localhost:27017"
DB_NAME   = "cinebook"

# ─── Connect  ──────────────

def get_client():
    """Connect to MongoDB and verify the connection."""
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
        print(f"[✓] Connected to MongoDB at {MONGO_URI}")
    except ConnectionFailure:
        print(f"[✗] Could not connect to MongoDB at {MONGO_URI}")
        print("    Make sure MongoDB is running: mongod --dbpath <your_data_path>")
        sys.exit(1)
    return client

# ─── Create Collections & Indexes   ───────

def setup_collections(db):
    """Create collections with proper indexes mirroring the SQLAlchemy models."""

    # ── Users  ────────────
    users = db["users"]
    users.create_index("username", unique=True, name="uq_username")
    users.create_index("email",    unique=True, name="uq_email")
    print("[✓] Collection 'users' — indexes: uq_username, uq_email")

    # ── Movies  ───────────
    movies = db["movies"]
    movies.create_index("title",     name="idx_movie_title")
    movies.create_index("is_active", name="idx_movie_active")
    print("[✓] Collection 'movies' — indexes: idx_movie_title, idx_movie_active")

    # ── Halls  ────────────
    halls = db["halls"]
    halls.create_index("name", unique=True, name="uq_hall_name")
    print("[✓] Collection 'halls' — indexes: uq_hall_name")

    # ── Showtimes  ────────
    showtimes = db["showtimes"]
    showtimes.create_index(
        [("movie_id", ASCENDING), ("hall_id", ASCENDING), ("start_time", ASCENDING)],
        unique=True,
        name="uq_showtime_slot",
    )
    showtimes.create_index("is_active", name="idx_showtime_active")
    print("[✓] Collection 'showtimes' — indexes: uq_showtime_slot, idx_showtime_active")

    # ── Bookings  ─────────
    bookings = db["bookings"]
    bookings.create_index(
        [("showtime_id", ASCENDING), ("seat_number", ASCENDING)],
        unique=True,
        name="uq_seat_per_showtime",
    )
    bookings.create_index("user_id",     name="idx_booking_user")
    bookings.create_index("showtime_id", name="idx_booking_showtime")
    bookings.create_index("status",      name="idx_booking_status")
    print("[✓] Collection 'bookings' — indexes: uq_seat_per_showtime, idx_booking_user, idx_booking_showtime")

    # ── Payments  ─────────
    payments = db["payments"]
    payments.create_index("booking_id",     unique=True, name="uq_payment_booking")
    payments.create_index("transaction_id", unique=True, name="uq_transaction_id")
    payments.create_index("booking_ids",   name="idx_payment_booking_ids")
    print("[✓] Collection 'payments' — indexes: uq_payment_booking, uq_transaction_id, idx_payment_booking_ids")

    # ── Seat Locks  ───────
    seat_locks = db["seat_locks"]
    seat_locks.create_index(
        [("showtime_id", ASCENDING), ("seat_number", ASCENDING)],
        unique=True,
        name="uq_seat_lock",
    )
    print("[✓] Collection 'seat_locks' — indexes: uq_seat_lock")

    return users, movies, halls, showtimes, bookings, payments


# ─── Seed Demo Data  ──────

def seed_demo_data(db, users, movies, halls, showtimes, bookings, payments):
    """Insert demo data only if the users collection is empty."""
    if users.count_documents({}) > 0:
        print("[i] Database already seeded — skipping.")
        return

    try:
        import bcrypt
        def _hash(pw: str) -> str:
            return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        print("[!] bcrypt not installed — using plaintext passwords for demo (NOT for production).")
        def _hash(pw: str) -> str:
            return f"PLAINTEXT:{pw}"

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    # ── Users  ────────────
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
    users.insert_many(user_docs)
    print("[✓] Seeded 3 users: admin, alice, bob")

    # ── Halls  ────────────
    hall_docs = [
        {"_id": 1, "name": "Hall A", "capacity": 16, "seats_per_row": 4, "is_active": True},
        {"_id": 2, "name": "Hall B", "capacity": 24, "seats_per_row": 6, "is_active": True},
    ]
    halls.insert_many(hall_docs)
    print("[✓] Seeded 2 halls: Hall A (16 seats), Hall B (24 seats)")

    # ── Movies  ───────────
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
    movies.insert_many(movie_docs)
    print("[✓] Seeded 3 movies: Inception, The Dark Knight, Interstellar")

    # ── Showtimes  ────────
    showtime_docs = [
        {"_id": 1, "movie_id": 1, "hall_id": 1, "start_time": now + timedelta(hours=2),  "ticket_price": 12.50, "is_active": True},
        {"_id": 2, "movie_id": 1, "hall_id": 2, "start_time": now + timedelta(hours=5),  "ticket_price": 10.00, "is_active": True},
        {"_id": 3, "movie_id": 2, "hall_id": 1, "start_time": now + timedelta(hours=8),  "ticket_price": 12.50, "is_active": True},
        {"_id": 4, "movie_id": 2, "hall_id": 2, "start_time": now + timedelta(hours=11), "ticket_price": 10.00, "is_active": True},
        {"_id": 5, "movie_id": 3, "hall_id": 1, "start_time": now + timedelta(hours=14), "ticket_price": 14.00, "is_active": True},
    ]
    showtimes.insert_many(showtime_docs)
    print("[✓] Seeded 5 showtimes across 3 movies and 2 halls")

    # ── Counters (for auto-increment IDs) ────────────────────────────────────
    counters = db["counters"]
    counter_docs = [
        {"_id": "users",     "seq": 3},
        {"_id": "movies",    "seq": 3},
        {"_id": "halls",     "seq": 2},
        {"_id": "showtimes", "seq": 5},
        {"_id": "bookings",  "seq": 0},
        {"_id": "payments",  "seq": 0},
    ]
    for doc in counter_docs:
        counters.update_one({"_id": doc["_id"]}, {"$set": {"seq": doc["seq"]}}, upsert=True)
    print("[✓] Initialized auto-increment counters")


# ─── Main  ────────────────

def main():
    print("=" * 60)
    print("  CineBook   — MongoDB Database Setup")
    print("=" * 60)
    print()

    client = get_client()
    db     = client[DB_NAME]

    print(f"\n[i] Using database: '{DB_NAME}'")
    print()

    users, movies, halls, showtimes, bookings, payments = setup_collections(db)

    print()
    seed_demo_data(db, users, movies, halls, showtimes, bookings, payments)

    print()
    print("=" * 60)
    print(f"  Database '{DB_NAME}' is ready!")
    print()
    print("  Collections created:")
    for name in sorted(db.list_collection_names()):
        count = db[name].count_documents({})
        print(f"    • {name:15s}  ({count} documents)")
    print()
    print("  Connection string: mongodb://localhost:27017/cinebook")
    print("=" * 60)

    client.close()


if __name__ == "__main__":
    main()
