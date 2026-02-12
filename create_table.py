import os
from supabase import create_client

SUPABASE_URL = "https://czpackoyubllazezhhii.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN6cGFja295dWJsbGF6ZXpoaGlpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA1NDExMjMsImV4cCI6MjA4NjExNzEyM30.3vtLLbGy0FQN0syklHGpbWihlu_gzWv8l_AE1zBaZ_E"

client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Try to query the table to see if it exists
try:
    result = client.table('legislature_videos').select('id').limit(1).execute()
    print(f"Table exists! Found {len(result.data)} records")
except Exception as e:
    print(f"Table doesn't exist or error: {e}")
    print("\nNeed to create table via Supabase dashboard SQL editor")
