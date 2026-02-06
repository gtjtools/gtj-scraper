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

# Construct the PostgreSQL connection URL with the port number
DATABASE_URL = f"postgresql://postgres:ForTestingLang123456@db.spttnizdxfnajghkbnvh.supabase.co:5432/postgres"
#DATABASE_URL = f"postgresql://postgres:Dreaming%20of%20a%20Contractor%20Life@db.spttnizdxfnajghkbnvh.supabase.co:5432/postgres"
#DATABASE_URL= f"postgresql://postgres.spttnizdxfnajghkbnvh:ForTestingLang123456@aws-1-us-east-2.pooler.supabase.com:5432/postgres"

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
    pool_size=5,
    max_overflow=10,
)

# Create a sessionmaker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# LOAD THE JWT SECRET
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
JWT_ALGORITHM = "HS256"
