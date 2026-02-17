#!/usr/bin/env python3
"""
Enumerate full Vimeo channel archives using yt-dlp
Pipes video IDs directly to Supabase as PENDING
"""

import os
import sys
from pathlib import Path
from supabase_client import LegislatureDB

try:
    import yt_dlp
except ImportError:
    print("Installing yt-dlp...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp", "-q"])
    import yt_dlp

# Load env
env_file = Path(__file__).parent / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

VIMEO_CHANNELS = {
    "house": "https://vimeo.com/georgiahouse/videos",
    "senate": "https://vimeo.com/georgiastatesenate/videos",
}

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

def enumerate_channel(chamber: str, url: str) -> list[str]:
    """Enumerate all video IDs from a Vimeo channel using yt-dlp library"""
    print(f"🎬 Enumerating {chamber.upper()} channel: {url}")
    sys.stdout.flush()
    
    video_ids = []
    
    try:
        ydl_opts = {
            'quiet': False,
            'no_warnings': False,
            'extract_flat': 'in_playlist',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"  ⏳ Fetching (this takes ~30 min)...")
            sys.stdout.flush()
            
            info = ydl.extract_info(url, download=False)
            
            if 'entries' in info:
                video_ids = [entry['id'] for entry in info['entries'] if entry and 'id' in entry]
        
        print(f"  ✓ Found {len(video_ids)} videos")
        
    except Exception as e:
        print(f"  ✗ Error: {str(e)[:100]}")
    
    return video_ids

def insert_videos(chamber: str, video_ids: list[str]) -> tuple[int, int]:
    """Insert video IDs into Supabase as PENDING"""
    # Ensure env is loaded
    load_env()
    db = LegislatureDB()
    
    inserted = 0
    skipped = 0
    
    print(f"  📤 Inserting {len(video_ids)} videos into Supabase...")
    sys.stdout.flush()
    
    for i, vid in enumerate(video_ids):
        if not vid:
            continue
        
        record = {
            "video_id": f"vimeo_{vid}",
            "url": f"https://vimeo.com/{vid}",
            "title": f"Vimeo {chamber.upper()} Video",  # Will be updated later
            "chamber": chamber,
            "session_type": "regular",
            "session_year": 2026,
            "source": "vimeo",
            "status": "pending"
        }
        
        try:
            result = db.client.table('legislature_videos').insert(record, upsert=True).execute()
            if result.data:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            if "duplicate" not in str(e).lower():
                print(f"    Error {i}: {str(e)[:60]}")
                sys.stdout.flush()
            else:
                skipped += 1
        
        # Progress every 200
        if (i + 1) % 200 == 0:
            print(f"    {i+1}/{len(video_ids)} processed ({inserted} new, {skipped} dup)...")
            sys.stdout.flush()
    
    return inserted, skipped

def main():
    print("🎬 Vimeo Channel Enumeration & Import\n")
    
    total_videos = 0
    total_inserted = 0
    total_skipped = 0
    
    for chamber, url in VIMEO_CHANNELS.items():
        # Enumerate
        video_ids = enumerate_channel(chamber, url)
        total_videos += len(video_ids)
        
        if not video_ids:
            continue
        
        # Insert
        inserted, skipped = insert_videos(chamber, video_ids)
        total_inserted += inserted
        total_skipped += skipped
        
        print(f"  ✅ {chamber.upper()}: {inserted} new, {skipped} duplicate\n")
        sys.stdout.flush()
    
    print(f"\n🎉 Complete:")
    print(f"  Total videos found: {total_videos}")
    print(f"  Inserted to Supabase: {total_inserted}")
    print(f"  Skipped (duplicates): {total_skipped}")
    print(f"\nReady for transcription! 🍺")

if __name__ == "__main__":
    main()
