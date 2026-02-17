#!/usr/bin/env python3
"""
Georgia Legislature Video Scraper
Extracts YouTube URLs from House and Senate archive pages + Vimeo RSS feeds
Writes to Supabase for distributed processing
"""

import re
import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from html.parser import HTMLParser
from vimeo_scraper import scrape_vimeo
from supabase_client import LegislatureDB

# Archive page URLs
SOURCES = {
    "house_floor": "https://www.house.ga.gov/en-US/HouseFloorVideoArchives.aspx",
}

# YouTube channels to scrape (for Senate and committee videos)
YOUTUBE_CHANNELS = {
    "gpb_lawmakers": "https://www.youtube.com/@GPBLawmakers/videos",  # Senate floor + committee
    "senate_press": "https://www.youtube.com/@GeorgiaStateSenate/videos",  # Press conferences
}

DB_PATH = Path(__file__).parent / "legislature.db"


class YouTubeLinkParser(HTMLParser):
    """Extract YouTube URLs and their link text from HTML"""
    
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_href = None
        self.current_text = ""
        self.in_link = False
    
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if "youtu" in href or "youtube" in href:
                self.current_href = href
                self.current_text = ""
                self.in_link = True
    
    def handle_endtag(self, tag):
        if tag == "a" and self.in_link:
            if self.current_href:
                self.links.append({
                    "url": self.current_href,
                    "text": self.current_text.strip()
                })
            self.in_link = False
            self.current_href = None
    
    def handle_data(self, data):
        if self.in_link:
            self.current_text += data


def fetch_page(url: str) -> str:
    """Fetch HTML content from URL"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def extract_youtube_links(html: str) -> list[dict]:
    """Extract YouTube URLs and metadata from HTML"""
    parser = YouTubeLinkParser()
    parser.feed(html)
    return parser.links


def parse_video_metadata(link: dict, source: str) -> dict:
    """Parse video metadata from link text"""
    text = link["text"]
    url = link["url"]
    
    # Extract video ID from URL
    video_id = None
    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0]
    elif "youtube.com" in url and "v=" in url:
        video_id = url.split("v=")[1].split("&")[0]
    elif "youtube.com/live/" in url:
        video_id = url.split("/live/")[1].split("?")[0]
    
    # Parse day and date from text
    # Examples: "Day 1 - January 9", "Day 25 - February 28 Part 1"
    day_match = re.search(r"Day\s*(\d+)", text, re.IGNORECASE)
    date_match = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d+)", text, re.IGNORECASE)
    part_match = re.search(r"Part\s*(\d+)", text, re.IGNORECASE)
    time_match = re.search(r"\((AM|PM)\)", text, re.IGNORECASE)
    
    # Determine chamber
    chamber = "house" if "house" in source.lower() else "senate"
    
    # Determine session type
    session_type = "special" if "special" in text.lower() else "regular"
    
    return {
        "video_id": video_id,
        "url": url,
        "text": text,
        "source": source,
        "chamber": chamber,
        "session_type": session_type,
        "day_number": int(day_match.group(1)) if day_match else None,
        "month": date_match.group(1) if date_match else None,
        "day": int(date_match.group(2)) if date_match else None,
        "part": int(part_match.group(1)) if part_match else None,
        "time_of_day": time_match.group(1).upper() if time_match else None,
    }


def init_database():
    """Initialize SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE,
            url TEXT NOT NULL,
            title TEXT,
            chamber TEXT,
            session_type TEXT,
            session_year INTEGER,
            day_number INTEGER,
            video_date TEXT,
            part INTEGER,
            time_of_day TEXT,
            duration_seconds INTEGER,
            source TEXT,
            raw_text TEXT,
            transcript TEXT,
            summary TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_video_id ON videos(video_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_status ON videos(status)
    """)
    
    conn.commit()
    return conn


def save_video(conn: sqlite3.Connection, video: dict, year: int, db: LegislatureDB = None):
    """Save video to database (Supabase primary, SQLite fallback), skip if exists"""
    cursor = conn.cursor()
    
    # Build date string if we have month and day
    video_date = None
    if video.get("month") and video.get("day"):
        try:
            month_num = datetime.strptime(video["month"], "%B").month
            video_date = f"{year}-{month_num:02d}-{video['day']:02d}"
        except ValueError:
            pass
    
    # Build record for insertion
    video_record = {
        "video_id": video["video_id"],
        "url": video["url"],
        "chamber": video["chamber"],
        "session_type": video["session_type"],
        "session_year": year,
        "day_number": video["day_number"],
        "video_date": video_date,
        "part": video["part"],
        "time_of_day": video["time_of_day"],
        "source": video["source"],
        "status": "pending"
    }
    
    # Try to insert into Supabase first
    is_new = False
    if db:
        try:
            result = db.client.table('legislature_videos').insert(video_record, upsert=True).execute()
            is_new = bool(result.data)
        except Exception as e:
            print(f"  Supabase insert error: {e}")
    
    # Also save to local SQLite for reference
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO videos 
            (video_id, url, chamber, session_type, session_year, day_number, 
             video_date, part, time_of_day, source, raw_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            video["video_id"],
            video["url"],
            video["chamber"],
            video["session_type"],
            year,
            video["day_number"],
            video_date,
            video["part"],
            video["time_of_day"],
            video["source"],
            video["text"]
        ))
        conn.commit()
        return cursor.rowcount > 0 or is_new  # True if inserted to either DB
    except sqlite3.IntegrityError:
        return is_new


def scrape_youtube_channel(channel_url: str, source_name: str, limit: int = 100) -> list[dict]:
    """Scrape video metadata from a YouTube channel using yt-dlp"""
    videos = []
    
    try:
        # Use yt-dlp to get playlist/channel info
        cmd = [
            "yt-dlp", "--flat-playlist", "--print-json",
            "--playlist-end", str(limit),
            channel_url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                title = data.get("title", "")
                
                # Parse chamber and type from title
                chamber = None
                session_type = "regular"
                
                if "Senate" in title:
                    chamber = "senate"
                elif "House" in title:
                    chamber = "house"
                
                if "Committee" in title:
                    session_type = "committee"
                elif "Press" in title:
                    session_type = "press"
                
                # Parse day number and date from title
                # Examples: "Georgia Senate 2026 - Day 5 AM Session 1"
                day_match = re.search(r"Day\s*(\d+)", title)
                year_match = re.search(r"20\d{2}", title)
                
                videos.append({
                    "video_id": data.get("id"),
                    "url": f"https://www.youtube.com/watch?v={data.get('id')}",
                    "title": title,
                    "source": source_name,
                    "chamber": chamber,
                    "session_type": session_type,
                    "day_number": int(day_match.group(1)) if day_match else None,
                    "year": int(year_match.group()) if year_match else datetime.now().year,
                })
            except json.JSONDecodeError:
                continue
                
    except subprocess.TimeoutExpired:
        print(f"  Timeout scraping {source_name}")
    except Exception as e:
        print(f"  Error scraping {source_name}: {e}")
    
    return videos


def scrape_all(years: list[int] = None) -> dict:
    """Scrape all sources (YouTube + Vimeo) and save to Supabase"""
    conn = init_database()  # Keep SQLite for local reference
    db = LegislatureDB()  # Use Supabase for primary database
    results = {"new": 0, "existing": 0, "errors": [], "youtube": 0, "vimeo": 0}
    
    # Scrape Vimeo RSS feeds (fastest - do this first)
    print("\n=== VIMEO SOURCES ===")
    try:
        vimeo_videos = scrape_vimeo()
        print(f"Found {len(vimeo_videos)} Vimeo videos")
        
        for video in vimeo_videos:
            if not video["video_id"]:
                continue
            
            # Build Supabase-compatible record
            vimeo_id = video["video_id"]
            try:
                # Insert into Supabase
                video_record = {
                    "video_id": f"vimeo_{vimeo_id}",
                    "url": f"https://vimeo.com/{vimeo_id}",
                    "title": video["title"],
                    "chamber": video["chamber"],
                    "session_type": "regular",
                    "session_year": video.get("session_year", datetime.now().year),
                    "day_number": video.get("day_number"),
                    "source": "vimeo",
                    "status": "pending"
                }
                
                # Use supabase_client to insert (upsert handles duplicates)
                result = db.client.table('legislature_videos').insert(video_record, upsert=True).execute()
                
                if result.data:
                    results["new"] += 1
                    results["vimeo"] += 1
                else:
                    results["existing"] += 1
                    
                # Also save to local SQLite for reference
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO videos 
                    (video_id, url, title, chamber, session_type, session_year, 
                     day_number, source, raw_text, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"vimeo_{vimeo_id}",
                    f"https://vimeo.com/{vimeo_id}",
                    video["title"],
                    video["chamber"],
                    "regular",
                    video.get("session_year", datetime.now().year),
                    video.get("day_number"),
                    "vimeo",
                    video["title"],
                    "pending"
                ))
                conn.commit()
            except Exception as e:
                if "duplicate" not in str(e).lower():
                    results["errors"].append(f"Vimeo insert: {str(e)}")
                    print(f"  Error inserting {vimeo_id}: {e}")
                else:
                    results["existing"] += 1
    except Exception as e:
        results["errors"].append(f"Vimeo scrape: {str(e)}")
        print(f"  Error: {e}")
    
    # Scrape HTML archive pages (House)
    for source_name, url in SOURCES.items():
        print(f"Scraping {source_name}...")
        try:
            html = fetch_page(url)
            links = extract_youtube_links(html)
            print(f"  Found {len(links)} YouTube links")
            
            for link in links:
                video = parse_video_metadata(link, source_name)
                if not video["video_id"]:
                    continue
                
                # Try to determine year from context or default to current
                # The archive pages are organized by year, we'll need to parse that
                # For now, guess based on date patterns or use current year
                year = datetime.now().year
                
                if save_video(conn, video, year, db):
                    results["new"] += 1
                else:
                    results["existing"] += 1
                    
        except Exception as e:
            results["errors"].append(f"{source_name}: {str(e)}")
            print(f"  Error: {e}")
    
    # Scrape YouTube channels (Senate, GPB)
    for source_name, channel_url in YOUTUBE_CHANNELS.items():
        print(f"Scraping YouTube channel {source_name}...")
        try:
            videos = scrape_youtube_channel(channel_url, source_name, limit=200)
            print(f"  Found {len(videos)} videos")
            
            for video in videos:
                if not video["video_id"]:
                    continue
                
                # Save YouTube channel videos to Supabase
                year = video.get("year", datetime.now().year)
                video_record = {
                    "video_id": video["video_id"],
                    "url": video["url"],
                    "title": video["title"],
                    "chamber": video["chamber"],
                    "session_type": video["session_type"],
                    "session_year": year,
                    "day_number": video["day_number"],
                    "source": video["source"],
                    "status": "pending"
                }
                
                try:
                    result = db.client.table('legislature_videos').insert(video_record, upsert=True).execute()
                    if result.data:
                        results["new"] += 1
                        results["youtube"] += 1
                    else:
                        results["existing"] += 1
                except Exception as e:
                    if "duplicate" not in str(e).lower():
                        results["errors"].append(f"YouTube channel insert: {str(e)}")
                    else:
                        results["existing"] += 1
                
                # Also save to local SQLite for reference
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO videos 
                        (video_id, url, title, chamber, session_type, session_year, 
                         day_number, source, raw_text)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        video["video_id"],
                        video["url"],
                        video["title"],
                        video["chamber"],
                        video["session_type"],
                        year,
                        video["day_number"],
                        video["source"],
                        video["title"]
                    ))
                    conn.commit()
                except sqlite3.IntegrityError:
                    pass
                    
        except Exception as e:
            results["errors"].append(f"{source_name}: {str(e)}")
            print(f"  Error: {e}")
    
    conn.close()
    return results


def get_pending_videos(limit: int = 10) -> list[dict]:
    """Get videos that haven't been processed yet"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM videos 
        WHERE status = 'pending' 
        ORDER BY session_year DESC, day_number DESC
        LIMIT ?
    """, (limit,))
    
    videos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return videos


def get_video_stats() -> dict:
    """Get statistics about videos in database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM videos")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM videos WHERE status = 'pending'")
    pending = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM videos WHERE status = 'transcribed'")
    transcribed = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM videos WHERE status = 'summarized'")
    summarized = cursor.fetchone()[0]
    
    cursor.execute("SELECT DISTINCT session_year FROM videos ORDER BY session_year DESC")
    years = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return {
        "total": total,
        "pending": pending,
        "transcribed": transcribed,
        "summarized": summarized,
        "years": years
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        stats = get_video_stats()
        print(json.dumps(stats, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "pending":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        videos = get_pending_videos(limit)
        for v in videos:
            print(f"{v['video_id']}: {v['chamber']} Day {v['day_number']} ({v['video_date']})")
    else:
        print("Scraping Georgia Legislature video archives...")
        results = scrape_all()
        print(f"\nResults:")
        print(f"  New videos: {results['new']}")
        print(f"  Already in DB: {results['existing']}")
        if results["errors"]:
            print(f"  Errors: {results['errors']}")
        
        stats = get_video_stats()
        print(f"\nDatabase stats:")
        print(f"  Total videos: {stats['total']}")
        print(f"  Pending: {stats['pending']}")
