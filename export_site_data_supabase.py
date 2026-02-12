#!/usr/bin/env python3
"""
Export video data from Supabase to JSON for the static website
"""

import json
import os
from pathlib import Path
from datetime import datetime

from supabase import create_client

# Supabase config
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://czpackoyubllazezhhii.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN6cGFja295dWJsbGF6ZXpoaGlpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA1NDExMjMsImV4cCI6MjA4NjExNzEyM30.3vtLLbGy0FQN0syklHGpbWihlu_gzWv8l_AE1zBaZ_E")

OUTPUT_DIR = Path(__file__).parent / "web" / "data"


def get_db():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def export_videos():
    """Export all summarized videos to JSON"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    sb = get_db()
    
    # Get all videos with summaries
    result = sb.table('legislature_videos').select('*').not_.is_('summary', 'null').order('session_year', desc=True).order('video_date', desc=True).execute()
    
    videos = []
    for row in result.data:
        video = {
            'video_id': row['video_id'],
            'url': row['url'],
            'title': row['title'],
            'chamber': row.get('chamber'),
            'session_type': row.get('session_type'),
            'session_year': row.get('session_year'),
            'day_number': row.get('day_number'),
            'video_date': row.get('video_date'),
            'duration_minutes': (row.get('duration_seconds') or 0) // 60,
            'summary': row['summary'],
            'updated_at': row.get('updated_at'),
        }
        videos.append(video)
    
    # Write main index
    with open(OUTPUT_DIR / "videos.json", "w") as f:
        json.dump(videos, f, indent=2)
    
    # Write individual video files
    for video in videos:
        video_file = OUTPUT_DIR / f"{video['video_id']}.json"
        with open(video_file, "w") as f:
            json.dump(video, f, indent=2)
    
    # Get stats
    all_videos = sb.table('legislature_videos').select('status, session_year').execute()
    
    total = len(all_videos.data)
    summarized = sum(1 for v in all_videos.data if v.get('status') == 'summarized')
    years = [v.get('session_year') for v in all_videos.data if v.get('session_year')]
    
    stats = {
        "total_videos": total,
        "summarized": summarized,
        "year_range": [min(years) if years else None, max(years) if years else None],
        "last_updated": datetime.now().isoformat(),
    }
    
    with open(OUTPUT_DIR / "stats.json", "w") as f:
        json.dump(stats, f, indent=2)
    
    print(f"Exported {len(videos)} videos to {OUTPUT_DIR}")
    print(f"Stats: {stats}")
    
    return len(videos)


def export_by_year():
    """Export videos grouped by year"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    sb = get_db()
    
    # Get all summarized videos
    result = sb.table('legislature_videos').select('*').not_.is_('summary', 'null').execute()
    
    # Group by year
    by_year = {}
    for row in result.data:
        year = row.get('session_year')
        if year:
            if year not in by_year:
                by_year[year] = []
            by_year[year].append({
                'video_id': row['video_id'],
                'url': row['url'],
                'title': row['title'],
                'chamber': row.get('chamber'),
                'session_type': row.get('session_type'),
                'day_number': row.get('day_number'),
                'video_date': row.get('video_date'),
                'duration_minutes': (row.get('duration_seconds') or 0) // 60,
                'summary': row['summary'],
            })
    
    for year, videos in sorted(by_year.items(), reverse=True):
        with open(OUTPUT_DIR / f"year_{year}.json", "w") as f:
            json.dump(videos, f, indent=2)
        print(f"  Year {year}: {len(videos)} videos")


if __name__ == "__main__":
    print("Exporting video data from Supabase for website...")
    export_videos()
    export_by_year()
    print("Done!")
