'''
Supabase Client

Supabase client to interact with our db
'''

from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

supabase = create_client(SUPABASE_KEY, SUPABASE_URL)