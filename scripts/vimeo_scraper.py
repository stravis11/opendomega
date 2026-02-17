#!/usr/bin/env python3
"""
Georgia Legislature Vimeo Scraper
Extracts video URLs from Vimeo RSS feeds with rate limiting
"""

import re
import xml.etree.ElementTree as ET
import time
from urllib.request import urlopen, Request
from datetime import datetime
from pathlib import Path

# Vimeo RSS feeds
VIMEO_FEEDS = {
    "house": "https://vimeo.com/georgiahouse/videos/rss",
    "senate": "https://vimeo.com/georgiastatesenate/videos/rss",
}


def fetch_rss(url: str) -> str:
    """Fetch RSS feed content"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def parse_vimeo_rss(rss_content: str, chamber: str) -> list[dict]:
    """Parse Vimeo RSS feed and extract video URLs"""
    videos = []
    
    try:
        root = ET.fromstring(rss_content)
        
        # Namespace for RSS
        ns = {
            'content': 'http://purl.org/rss/1.0/modules/content/',
            'media': 'http://search.yahoo.com/mrss/'
        }
        
        # Extract items from RSS
        for item in root.findall('.//item'):
            title_elem = item.find('title')
            link_elem = item.find('link')
            pub_date_elem = item.find('pubDate')
            description_elem = item.find('description')
            
            if title_elem is not None and link_elem is not None:
                title = title_elem.text or ""
                url = link_elem.text or ""
                pub_date = pub_date_elem.text if pub_date_elem is not None else None
                description = description_elem.text if description_elem is not None else ""
                
                # Extract video ID from Vimeo URL
                # Vimeo URLs look like: https://vimeo.com/123456789
                video_id_match = re.search(r'vimeo\.com/(\d+)', url)
                if video_id_match:
                    video_id = video_id_match.group(1)
                    
                    # Parse metadata from title
                    # Examples: "2.12.26 Natural Resources & Environment"
                    date_match = re.search(r'(\d+)\.(\d+)\.(\d+)', title)
                    day_match = re.search(r'Day\s*(\d+)', title, re.IGNORECASE)
                    
                    video = {
                        "video_id": video_id,
                        "url": url,
                        "title": title,
                        "chamber": chamber,
                        "source": f"vimeo_{chamber}",
                        "platform": "vimeo",
                        "pub_date": pub_date,
                        "description": description,
                    }
                    
                    # Try to extract date (format: M.D.YY or Day N)
                    if date_match:
                        month, day, year = date_match.groups()
                        # Assume 2026 if YY < 50, else 2000+YY
                        full_year = int(f"20{year}") if int(year) < 50 else int(f"19{year}")
                        video["session_year"] = full_year
                        video["video_date"] = f"{full_year}-{month.zfill(2)}-{day.zfill(2)}"
                    
                    if day_match:
                        video["day_number"] = int(day_match.group(1))
                    
                    videos.append(video)
        
    except ET.ParseError as e:
        print(f"Error parsing RSS feed: {e}")
        return []
    
    return videos


def scrape_vimeo(delay: float = 1.0) -> list[dict]:
    """Scrape all Vimeo sources with rate limiting"""
    all_videos = []
    
    for chamber, feed_url in VIMEO_FEEDS.items():
        print(f"Scraping Vimeo {chamber.upper()} (delay: {delay}s per page)...")
        
        # Vimeo RSS feeds support pagination via ?page parameter
        page = 1
        total_for_chamber = 0
        
        while True:
            paginated_url = f"{feed_url}?page={page}"
            
            try:
                print(f"  Page {page}...", end="", flush=True)
                rss_content = fetch_rss(paginated_url)
                videos = parse_vimeo_rss(rss_content, chamber)
                
                if not videos:
                    print(" (no more videos)")
                    break
                
                print(f" {len(videos)} videos")
                all_videos.extend(videos)
                total_for_chamber += len(videos)
                page += 1
                
                # Rate limiting — respect Vimeo's servers
                if page % 10 == 0:
                    print(f"  (pausing {delay}s after 10 pages...)")
                    time.sleep(delay * 10)  # Longer pause every 10 pages
                else:
                    time.sleep(delay)  # Standard delay between pages
                
            except Exception as e:
                print(f" Error: {e}")
                if "503" in str(e):
                    print(f"  (Rate limited. Try again later.)")
                break
        
        print(f"  Total for {chamber}: {total_for_chamber}\n")
    
    return all_videos


if __name__ == "__main__":
    import sys
    
    delay = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    videos = scrape_vimeo(delay=delay)
    print(f"\nTotal Vimeo videos found: {len(videos)}")
    for video in videos[:5]:
        print(f"  - {video['title']} ({video['video_id']})")
    
    print(f"\nUsage: python3 vimeo_scraper.py [delay_seconds]")
    print(f"  delay_seconds: Delay between page fetches (default: 1.0)")
    print(f"  Example: python3 vimeo_scraper.py 2.0  # 2 second delays")
