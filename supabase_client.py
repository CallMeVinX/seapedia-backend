from supabase import create_client, Client
from config import settings
import logging

logger = logging.getLogger(__name__)

supabase_client: Client = None

if settings.supabase_url and settings.supabase_key:
    try:
        supabase_client = create_client(settings.supabase_url, settings.supabase_key)
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
else:
    logger.warning("Supabase credentials not configured in environment variables (.env). Please set SUPABASE_URL and SUPABASE_KEY.")

def get_supabase_client() -> Client:
    if supabase_client is None:
        raise ValueError("Supabase client is not initialized. Please ensure SUPABASE_URL and SUPABASE_KEY are set in your .env file.")
    return supabase_client
