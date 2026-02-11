#!/usr/bin/env python3
"""
Migrate SQLite legislature.db to Supabase

Usage:
    export SUPABASE_URL=https://your-project.supabase.co
    export SUPABASE_KEY=your-anon-or-service-role-key
    python migrate_to_supabase.py
"""

import os
import sqlite3
import json
from datetime import datetime
from supabase import create_client, Client

# Supabase connection
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables required")
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def migrate():
    # Connect to SQLite
    sqlite_conn = sqlite3.connect('legislature.db')
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    
    # Connect to Supabase
    supabase = get_supabase()
    
    # Get all videos from SQLite
    cursor.execute('SELECT * FROM videos')
    rows = cursor.fetchall()
    
    print(f"Found {len(rows)} videos to migrate")
    
    # Batch insert into Supabase (in chunks of 100)
    batch_size = 100
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        records = []
        for row in batch:
            record = {
                'video_id': row['video_id'],
                'url': row['url'],
                'title': row['title'],
                'chamber': row['chamber'],
                'session_type': row['session_type'],
                'session_year': row['session_year'],
                'day_number': row['day_number'],
                'video_date': row['video_date'],
                'part': row['part'],
                'time_of_day': row['time_of_day'],
                'duration_seconds': row['duration_seconds'],
                'source': row['source'],
                'raw_text': row['raw_text'],
                'transcript': row['transcript'],
                'summary': row['summary'],
                'status': row['status'] or 'pending',
            }
            records.append(record)
        
        # Insert batch
        result = supabase.table('legislature_videos').insert(records).execute()
        print(f"Migrated batch {i//batch_size + 1}: {len(records)} records")
    
    print("Migration complete!")
    
    # Verify counts
    count_result = supabase.table('legislature_videos').select('id', count='exact').execute()
    print(f"Supabase now has {count_result.count} records")

def export_pending_json():
    """Export pending videos as JSON for debugging/backup"""
    sqlite_conn = sqlite3.connect('legislature.db')
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    
    cursor.execute('SELECT video_id, url, title, chamber, session_year, status FROM videos WHERE status = "pending"')
    rows = cursor.fetchall()
    
    videos = [dict(row) for row in rows]
    
    with open('pending_videos.json', 'w') as f:
        json.dump(videos, f, indent=2)
    
    print(f"Exported {len(videos)} pending videos to pending_videos.json")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--export':
        export_pending_json()
    else:
        migrate()
