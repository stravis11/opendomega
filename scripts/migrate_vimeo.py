#!/usr/bin/env python3
"""
Migrate Vimeo videos from SQLite to Supabase
"""

import os
import sqlite3
from pathlib import Path
from supabase_client import LegislatureDB

def load_env():
    """Load .env file into os.environ"""
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

def migrate_vimeo_videos():
    """Migrate 20 Vimeo videos from SQLite to Supabase"""
    load_env()
    print("🔄 Migrating Vimeo videos from SQLite → Supabase...\n")
    
    # Get credentials from env (loaded above)
    url = os.environ.get('SUPABASE_URL', 'https://czpackoyubllazezhhii.supabase.co')
    key = os.environ.get('SUPABASE_KEY')
    
    if not key:
        print("❌ Error: SUPABASE_KEY not found in .env")
        return
    
    db = LegislatureDB(url=url, key=key)
    
    conn = sqlite3.connect('legislature.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Get Vimeo videos
    c.execute("""
        SELECT video_id, url, title, chamber, session_type, session_year, 
               day_number, video_date, source, status, transcript, summary
        FROM videos 
        WHERE source LIKE 'vimeo%'
        ORDER BY source
    """)
    
    vimeo_videos = c.fetchall()
    
    migrated = 0
    failed = 0
    
    for video in vimeo_videos:
        # Build Supabase record
        record = {
            "video_id": f"vimeo_{video['video_id']}",
            "url": f"https://vimeo.com/{video['video_id']}",
            "title": video['title'],
            "chamber": video['chamber'],
            "session_type": video['session_type'] or 'regular',
            "session_year": video['session_year'] or 2026,
            "day_number": video['day_number'],
            "video_date": video['video_date'],
            "source": "vimeo",
            "status": video['status'] or 'pending',
            "transcript": video['transcript'],
            "summary": video['summary']
        }
        
        try:
            result = db.client.table('legislature_videos').insert(record, upsert=True).execute()
            if result.data:
                migrated += 1
                print(f"  ✓ vimeo_{video['video_id']}")
            else:
                print(f"  - vimeo_{video['video_id']} (already exists)")
        except Exception as e:
            failed += 1
            print(f"  ✗ vimeo_{video['video_id']}: {str(e)[:60]}")
    
    conn.close()
    
    print(f"\n✅ Migration complete:")
    print(f"  Migrated: {migrated}/20")
    print(f"  Failed: {failed}/20")

if __name__ == "__main__":
    migrate_vimeo_videos()
