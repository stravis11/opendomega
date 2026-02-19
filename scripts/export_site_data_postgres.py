#!/usr/bin/env python3
"""
Export video data from local Postgres to JSON for the static website
"""

import json
import os
import psycopg2
from pathlib import Path
from datetime import datetime

# Postgres config
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "192.168.68.84")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "legislature")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "postgres")

OUTPUT_DIR = Path(__file__).parent.parent / "web" / "data"


def get_db():
    """Connect to Postgres"""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            sslmode="disable"
        )
        return conn
    except Exception as e:
        print(f"Error connecting to Postgres: {e}")
        print("\nNote: If running on Mac, the Postgres is on Linux (192.168.68.84:5432)")
        print("This script should be run on the Linux machine where Postgres is running.")
        raise


def export_videos():
    """Export all summarized videos to JSON with transcripts"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    transcripts_dir = OUTPUT_DIR / "transcripts"
    transcripts_dir.mkdir(exist_ok=True)
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Get all videos with summaries
        cursor.execute("""
            SELECT 
                id, video_id, url, title, chamber, session_type, 
                session_year, day_number, video_date, duration_seconds,
                summary, transcript, source
            FROM legislature_videos 
            WHERE status = 'summarized'
            ORDER BY session_year DESC, video_date DESC
        """)
        
        rows = cursor.fetchall()
        videos = []
        search_index = []
        
        print(f"Exporting {len(rows)} summarized videos...")
        
        for row in rows:
            vid_id, video_id, url, title, chamber, session_type, session_year, day_number, video_date, duration_seconds, summary, transcript, source = row
            
            # Save transcript if available
            if transcript:
                transcript_file = f"{video_id}.txt"
                with open(transcripts_dir / transcript_file, 'w') as f:
                    f.write(transcript)
            
            # Build video object
            video = {
                'video_id': video_id,
                'url': url,
                'title': title,
                'chamber': chamber,
                'session_type': session_type,
                'session_year': session_year,
                'day_number': day_number,
                'video_date': video_date,
                'duration_minutes': (duration_seconds or 0) // 60,
                'summary': summary,
                'source': source,
                'has_transcript': bool(transcript)
            }
            videos.append(video)
            
            # Add to search index
            search_index.append({
                'video_id': video_id,
                'title': title,
                'chamber': chamber,
                'session_year': session_year,
                'summary': summary[:200]  # First 200 chars for search
            })
        
        # Write videos.json
        with open(OUTPUT_DIR / "videos.json", 'w') as f:
            json.dump(videos, f, indent=2, default=str)
        print(f"✓ Wrote {len(videos)} videos to videos.json")
        
        # Get stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'summarized' THEN 1 END) as summarized,
                COUNT(CASE WHEN status = 'transcribed' THEN 1 END) as transcribed,
                COUNT(CASE WHEN status = 'error' THEN 1 END) as errors,
                MIN(session_year) as min_year,
                MAX(session_year) as max_year,
                COUNT(DISTINCT session_year) as years_covered,
                COUNT(DISTINCT chamber) as chambers
            FROM legislature_videos
        """)
        
        total, summarized, transcribed, errors, min_year, max_year, years_covered, chambers = cursor.fetchone()
        
        stats = {
            'total_videos': total,
            'summarized_videos': summarized,
            'transcribed_videos': transcribed,
            'error_videos': errors,
            'years_covered': years_covered,
            'min_year': min_year,
            'max_year': max_year,
            'chambers': chambers,
            'last_updated': datetime.now().isoformat()
        }
        
        # Write stats.json
        with open(OUTPUT_DIR / "stats.json", 'w') as f:
            json.dump(stats, f, indent=2, default=str)
        print(f"✓ Wrote stats to stats.json")
        print(f"  - Total: {stats['total_videos']}")
        print(f"  - Summarized: {stats['summarized_videos']}")
        print(f"  - Transcribed: {stats['transcribed_videos']}")
        print(f"  - Errors: {stats['error_videos']}")
        print(f"  - Years: {stats['min_year']}-{stats['max_year']} ({stats['years_covered']} years)")
        
        # Write search_index.json
        with open(OUTPUT_DIR / "search_index.json", 'w') as f:
            json.dump(search_index, f, indent=2, default=str)
        print(f"✓ Wrote search index")
        
        print("\n✅ Export complete!")
        print(f"Ready to deploy to {OUTPUT_DIR}")
        
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    print("Exporting video data from local Postgres for website...\n")
    export_videos()
