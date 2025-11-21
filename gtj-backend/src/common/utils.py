# utils
from supabase import create_client, Client
import os

def get_supabase_client() -> Client:
    url: str = os.getenv("SUPABASE_URL")
    key: str = os.getenv("SUPABASE_KEY")
    return create_client(url, key)