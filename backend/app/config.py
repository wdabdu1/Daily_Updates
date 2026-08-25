"""Application configuration, read from environment variables.

DATABASE_URL follows Railway's convention (Postgres). When it's not set
(e.g. running locally without a Postgres instance handy), we fall back to a
local SQLite file so the app can still boot for preview purposes.
"""
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./local_dev.db")

# Railway/Heroku-style URLs sometimes use postgres:// which SQLAlchemy 1.4+
# no longer accepts directly; normalize to postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me-in-railway-vars")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "480"))  # 8h shift

DEFAULT_ADMIN_USERNAME = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin123")

# Currencies seeded on first boot if the table is empty.
SEED_CURRENCIES = ["USD", "EUR", "EGP", "GBP", "SAR", "AED", "SDG"]

# Currency pairs where CBOS Rate and Pricing Rate are meaningful, in addition
# to Market Rate. Every other pair only ever carries a Market Rate.
SDG_RATE_TYPES = ["Market", "CBOS", "Pricing"]
NON_SDG_RATE_TYPES = ["Market"]
