#!/usr/bin/env python3
"""
Export video data as JSON for the static website
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "legislature.db"
OUTPUT_DIR = Path(__file__).parent / "web" / "data"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def export_videos():
    """Export all summarized videos to JSON"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get all videos with summaries
    cursor.execute("""
        SELECT 
            video_id, url, title, chamber, session_type, session_year,
            day_number, video_date, duration_seconds, summary, updated_at
        FROM videos 
        WHERE summary IS NOT NULL AND summary != ''
        ORDER BY session_year DESC, video_date DESC, day_number DESC
    """)
    
    videos = []
    for row in cursor.fetchall():
        video = dict(row)
        # Clean up for JSON
        video['duration_minutes'] = (video.get('duration_seconds') or 0) // 60
        del video['duration_seconds']
        videos.append(video)
    
    # Write main index
    with open(OUTPUT_DIR / "videos.json", "w") as f:
        json.dump(videos, f, indent=2)
    
    # Write individual video files
    for video in videos:
        video_file = OUTPUT_DIR / f"{video['video_id']}.json"
        with open(video_file, "w") as f:
            json.dump(video, f, indent=2)
    
    # Export stats
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN summary IS NOT NULL THEN 1 ELSE 0 END) as summarized,
            SUM(CASE WHEN transcript IS NOT NULL THEN 1 ELSE 0 END) as transcribed,
            MIN(session_year) as min_year,
            MAX(session_year) as max_year
        FROM videos
    """)
    
    stats_row = cursor.fetchone()
    stats = {
        "total_videos": stats_row['total'],
        "summarized": stats_row['summarized'],
        "transcribed": stats_row['transcribed'],
        "year_range": [stats_row['min_year'], stats_row['max_year']],
        "last_updated": datetime.now().isoformat(),
    }
    
    with open(OUTPUT_DIR / "stats.json", "w") as f:
        json.dump(stats, f, indent=2)
    
    conn.close()
    
    print(f"Exported {len(videos)} videos to {OUTPUT_DIR}")
    print(f"Stats: {stats}")
    
    return len(videos)


def export_by_year():
    """Export videos grouped by year"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT session_year FROM videos WHERE summary IS NOT NULL ORDER BY session_year DESC")
    years = [row['session_year'] for row in cursor.fetchall()]
    
    for year in years:
        cursor.execute("""
            SELECT 
                video_id, url, title, chamber, session_type,
                day_number, video_date, duration_seconds, summary
            FROM videos 
            WHERE session_year = ? AND summary IS NOT NULL
            ORDER BY video_date DESC, day_number DESC
        """, (year,))
        
        videos = [dict(row) for row in cursor.fetchall()]
        
        with open(OUTPUT_DIR / f"year_{year}.json", "w") as f:
            json.dump(videos, f, indent=2)
        
        print(f"  Year {year}: {len(videos)} videos")
    
    conn.close()


if __name__ == "__main__":
    print("Exporting video data for website...")
    export_videos()
    export_by_year()
