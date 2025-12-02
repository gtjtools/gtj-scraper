"""
Supabase Client Adapter
Provides a connection to Supabase using the Supabase Python client
"""

from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()

class SupabaseAdapter:
    _instance: Client = None

    @classmethod
    def get_client(cls) -> Client:
        """
        Get or create Supabase client singleton

        Environment Variables Required:
        - SUPABASE_URL: Your Supabase project URL
        - SUPABASE_KEY: Your Supabase anon/service key
        """
        if cls._instance is None:
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_KEY")

            if not supabase_url or not supabase_key:
                raise ValueError(
                    "Missing Supabase credentials. "
                    "Please set SUPABASE_URL and SUPABASE_KEY in .env file"
                )

            cls._instance = create_client(supabase_url, supabase_key)
            print("✅ Supabase client initialized successfully")

        return cls._instance

# Convenience function to get client
def get_supabase_client() -> Client:
    """Get the Supabase client instance"""
    return SupabaseAdapter.get_client()
