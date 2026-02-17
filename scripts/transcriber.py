#!/usr/bin/env python3
"""
OpenDomeGA Legislature Video Transcriber
Downloads audio from YouTube videos and extracts transcripts with Whisper.

Usage:
    python transcriber.py --worker skippy --batch 5
    python transcriber.py --worker skippy --batch 10 --continuous
"""

import os
import sys
import sqlite3
import argparse
import time
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any


DB_PATH = Path(__file__).parent / "legislature.db"


class LegislatureTranscriberDB:
    """SQLite database for legislature videos"""
    
    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
    
    def claim_pending(self, worker: str, batch_size: int = 1) -> list[Dict[str, Any]]:
        """Claim pending videos for transcription"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        videos = []
        try:
            # Get pending videos
            cursor.execute("""
                SELECT id, video_id, url, title, video_date
                FROM videos
                WHERE status = 'pending'
                LIMIT ?
            """, (batch_size,))
            
            rows = cursor.fetchall()
            for row in rows:
                videos.append(dict(row))
            
            if videos:
                # Mark as claimed (status = transcribing)
                video_ids = [v['id'] for v in videos]
                placeholders = ','.join('?' * len(video_ids))
                cursor.execute(f"""
                    UPDATE videos
                    SET status = 'transcribing'
                    WHERE id IN ({placeholders})
                """, video_ids)
                conn.commit()
        finally:
            conn.close()
        
        return videos
    
    def set_transcribed(self, video_id: int, transcript: str):
        """Mark video as transcribed with transcript content"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE videos
                SET status = 'transcribed', transcript = ?
                WHERE id = ?
            """, (transcript, video_id))
            conn.commit()
        finally:
            conn.close()
    
    def set_error(self, video_id: int, error_message: str):
        """Mark video with error status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE videos
                SET status = 'error'
                WHERE id = ?
            """, (video_id,))
            conn.commit()
        finally:
            conn.close()


def extract_youtube_transcript(url: str) -> tuple[Optional[str], Optional[str]]:
    """Extract transcript from YouTube using summarize.sh"""
    try:
        # Use summarize.sh to extract YouTube captions directly (no audio download needed)
        cmd = ['summarize', url, '--extract']
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            return None, f"Extract failed: {result.stderr[:100]}"
        
        transcript = result.stdout.strip()
        
        # Remove "Transcript:" prefix if present
        if transcript.startswith("Transcript:"):
            transcript = transcript[11:].strip()
        
        if len(transcript) > 100:
            return transcript, None
        else:
            return None, "Transcript too short"
    
    except subprocess.TimeoutExpired:
        return None, "Extraction timeout"
    except Exception as e:
        return None, str(e)[:200]


def process_video(db: LegislatureTranscriberDB, video: Dict[str, Any], worker: str = "skippy") -> bool:
    """Process a single video: download and transcribe"""
    video_id = video['id']
    yt_video_id = video['video_id']
    title = video['title'] or 'Unknown'
    url = video['url']
    
    print(f"\n[{worker}] Processing {yt_video_id}: {title[:60]}")
    
    try:
        # Extract transcript from YouTube using summarize.sh (extracts captions directly)
        print(f"  Extracting transcript...")
        transcript, error = extract_youtube_transcript(url)
        
        if transcript:
            db.set_transcribed(video_id, transcript)
            print(f"  ✓ Transcribed ({len(transcript)} chars)")
            return True
        else:
            db.set_error(video_id, error or "Unknown extraction error")
            print(f"  ✗ Extraction failed: {error}")
            return False
    except Exception as e:
        db.set_error(video_id, str(e)[:200])
        print(f"  ✗ Error: {str(e)[:100]}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Transcribe legislature videos")
    parser.add_argument("--worker", default="skippy", help="Worker name for claiming")
    parser.add_argument("--batch", type=int, default=1, help="Videos per run")
    parser.add_argument("--continuous", action="store_true", help="Keep running until interrupted")
    parser.add_argument("--delay", type=int, default=5, help="Delay between videos (seconds)")
    
    args = parser.parse_args()
    db = LegislatureTranscriberDB()
    processed = 0
    succeeded = 0
    failed = 0
    
    print(f"Starting transcriber (worker: {args.worker})")
    print(f"Database: {DB_PATH}")
    print(f"Batch size: {args.batch}, Continuous: {args.continuous}")
    
    try:
        while True:
            videos = db.claim_pending(worker=args.worker, batch_size=args.batch)
            
            if not videos:
                print(f"\n[{args.worker}] No pending videos available")
                if not args.continuous:
                    break
                time.sleep(args.delay)
                continue
            
            for video in videos:
                success = process_video(db, video, args.worker)
                if success:
                    succeeded += 1
                else:
                    failed += 1
                
                processed += 1
                if len(videos) > 1 and video != videos[-1]:
                    time.sleep(args.delay)
            
            if not args.continuous:
                break
            
            print(f"\n[{args.worker}] Waiting before next batch...")
            time.sleep(args.delay)
    
    except KeyboardInterrupt:
        print("\n\nShutdown requested")
    except Exception as e:
        print(f"\n\nFatal error: {e}")
    
    print(f"\nResults - Processed: {processed}, Succeeded: {succeeded}, Failed: {failed}")


if __name__ == '__main__':
    main()
