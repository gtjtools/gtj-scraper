from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Load Supabase URL and Key from environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Extract the hostname from the SUPABASE_URL
hostname = SUPABASE_URL.split("://")[-1]

# Port 6543 is Supabase's PgBouncer pooler; 5432 is a direct Postgres
# connection. gtj-serverless already uses 6543 (lib/common/db.js) for the same
# reason this service now does: several apps share this database, and a direct
# connection consumes a real server slot per client.
#
# Direct-connection arithmetic for this service alone was 4 uvicorn workers x
# (pool_size 5 + max_overflow 10) = 60 possible connections, against a Supabase
# instance whose ceiling is likely 60-120 shared with gtj-backend and
# gtj-process. That is what produced "QueuePool limit of size 5 overflow 10
# reached, connection timed out".
#
# Set DATABASE_URL in the environment to override — useful for pointing at a
# direct connection if a migration or a prepared-statement-heavy job needs one.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:ForTestingLang123456@db.spttnizdxfnajghkbnvh.supabase.co:6543/postgres",
)

# Create the SQLAlchemy engine with connection pooling and keepalive
engine = create_engine(
    DATABASE_URL,
    echo=True,
    connect_args={
        "sslmode": "require",
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    },
    pool_pre_ping=True,      # Check connection before using
    pool_recycle=300,        # Recycle connections every 5 min
    pool_timeout=30,
    # Small client pool on purpose: PgBouncer (port 6543) does the real
    # server-side pooling, so a large per-process pool only holds pooler slots
    # open and multiplies across uvicorn workers. gtj-serverless uses max=2 for
    # the same reason.
    #
    # 4 workers x (2 + 3) = 20 worst case, down from 60.
    pool_size=2,
    max_overflow=3,
)

# Create a sessionmaker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# LOAD THE JWT SECRET
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
JWT_ALGORITHM = "HS256"
