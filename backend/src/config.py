import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://claims:claims@localhost:17744/claims")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:16344/0")
JWT_SECRET = os.getenv("JWT_SECRET", "claim-lead-classification-demo-secret")
JWT_ALGORITHM = "HS256"
MAX_FALSE_POSITIVE_RATE = 0.25
