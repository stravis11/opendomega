#!/usr/bin/env python3
"""
Georgia Legislature Video Processor
Downloads, transcribes, and prepares videos for summarization
"""

import os
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "legislature.db"
AUDIO_DIR = Path(__file__).parent / "audio"
TRANSCRIPT_DIR = Path(__file__).parent / "transcripts"

# Ensure directories exist
AUDIO_DIR.mkdir(exist_ok=True)
TRANSCRIPT_DIR.mkdir(exist_ok=True)


def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def download_audio(video_id: str, url: str) -> Path:
    """Download audio from YouTube video"""
    output_path = AUDIO_DIR / f"{video_id}.m4a"
    
    if output_path.exists():
        print(f"  Audio already exists: {output_path}")
        return output_path
    
    print(f"  Downloading audio for {video_id}...")
    
    cmd = [
        "yt-dlp",
        "-f", "140",  # Medium bitrate m4a (128kbps, better quality for transcription)
        "-o", str(output_path),
        url
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    
    if result.returncode != 0:
        raise Exception(f"yt-dlp failed: {result.stderr}")
    
    return output_path


def transcribe_audio(audio_path: Path, video_id: str, model: str = "base") -> str:
    """Transcribe audio using Whisper"""
    transcript_path = TRANSCRIPT_DIR / f"{video_id}.txt"
    
    if transcript_path.exists():
        print(f"  Transcript already exists: {transcript_path}")
        return transcript_path.read_text()
    
    print(f"  Transcribing {audio_path.name} with Whisper {model}...")
    
    # Run whisper with hallucination prevention
    cmd = [
        "whisper",
        str(audio_path),
        "--model", model,
        "--language", "en",
        "--output_format", "txt",
        "--output_dir", str(TRANSCRIPT_DIR),
        "--condition_on_previous_text", "False",  # Prevents hallucination loops
        "--no_speech_threshold", "0.6",  # Better silence detection
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)  # 2hr timeout
    
    if result.returncode != 0:
        raise Exception(f"Whisper failed: {result.stderr}")
    
    # Whisper outputs to {basename}.txt
    whisper_output = TRANSCRIPT_DIR / f"{audio_path.stem}.txt"
    if whisper_output.exists():
        # Rename to video_id.txt
        transcript_path = TRANSCRIPT_DIR / f"{video_id}.txt"
        whisper_output.rename(transcript_path)
        return transcript_path.read_text()
    
    return ""


def update_video_status(video_id: str, status: str, transcript: str = None, summary: str = None):
    """Update video status in database"""
    conn = get_db()
    cursor = conn.cursor()
    
    if transcript:
        cursor.execute("""
            UPDATE videos 
            SET status = ?, transcript = ?, updated_at = CURRENT_TIMESTAMP
            WHERE video_id = ?
        """, (status, transcript, video_id))
    elif summary:
        cursor.execute("""
            UPDATE videos 
            SET status = ?, summary = ?, updated_at = CURRENT_TIMESTAMP
            WHERE video_id = ?
        """, (status, summary, video_id))
    else:
        cursor.execute("""
            UPDATE videos 
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE video_id = ?
        """, (status, video_id))
    
    conn.commit()
    conn.close()


def get_video_duration(url: str) -> int:
    """Get video duration in seconds"""
    cmd = ["yt-dlp", "--no-download", "-j", url]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    
    if result.returncode == 0:
        data = json.loads(result.stdout)
        return data.get("duration", 0)
    return 0


def process_video(video: dict, whisper_model: str = "base") -> bool:
    """Process a single video: download, transcribe"""
    video_id = video["video_id"]
    url = video["url"]
    
    print(f"\nProcessing: {video['title'] or video['raw_text']}")
    print(f"  ID: {video_id}")
    
    try:
        # Check duration first
        duration = get_video_duration(url)
        print(f"  Duration: {duration}s ({duration//60}min)")
        
        # Skip very long videos for now (> 4 hours)
        if duration > 14400:
            print(f"  Skipping: video too long ({duration//3600}h)")
            update_video_status(video_id, "skipped")
            return False
        
        # Update duration in DB
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE videos SET duration_seconds = ? WHERE video_id = ?", 
                      (duration, video_id))
        conn.commit()
        conn.close()
        
        # Download audio
        audio_path = download_audio(video_id, url)
        
        # Transcribe
        transcript = transcribe_audio(audio_path, video_id, whisper_model)
        
        # Save transcript to database
        update_video_status(video_id, "transcribed", transcript=transcript)
        
        print(f"  ✓ Transcribed: {len(transcript)} characters")
        return True
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        update_video_status(video_id, "error")
        return False


def process_batch(limit: int = 5, whisper_model: str = "base", 
                  chamber: str = None, session_type: str = None) -> dict:
    """Process a batch of pending videos"""
    conn = get_db()
    cursor = conn.cursor()
    
    query = "SELECT * FROM videos WHERE status = 'pending'"
    params = []
    
    if chamber:
        query += " AND chamber = ?"
        params.append(chamber)
    
    if session_type:
        query += " AND session_type = ?"
        params.append(session_type)
    
    query += " ORDER BY session_year DESC, day_number DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    videos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    results = {"processed": 0, "errors": 0, "skipped": 0}
    
    for video in videos:
        success = process_video(video, whisper_model)
        if success:
            results["processed"] += 1
        else:
            # Check if skipped or error
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM videos WHERE video_id = ?", 
                          (video["video_id"],))
            status = cursor.fetchone()[0]
            conn.close()
            
            if status == "skipped":
                results["skipped"] += 1
            else:
                results["errors"] += 1
    
    return results


def get_transcribed_videos(limit: int = 100) -> list[dict]:
    """Get videos that have been transcribed but not summarized"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM videos 
        WHERE status = 'transcribed' 
        ORDER BY session_year DESC, day_number DESC
        LIMIT ?
    """, (limit,))
    
    videos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return videos


def export_for_summary(video_id: str) -> dict:
    """Export video data for LLM summarization"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    video = dict(row)
    return {
        "video_id": video["video_id"],
        "title": video["title"] or video["raw_text"],
        "chamber": video["chamber"],
        "session_type": video["session_type"],
        "session_year": video["session_year"],
        "day_number": video["day_number"],
        "video_date": video["video_date"],
        "duration_seconds": video["duration_seconds"],
        "transcript": video["transcript"],
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "batch":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            model = sys.argv[3] if len(sys.argv) > 3 else "base"
            results = process_batch(limit=limit, whisper_model=model)
            print(f"\nBatch complete:")
            print(f"  Processed: {results['processed']}")
            print(f"  Skipped: {results['skipped']}")
            print(f"  Errors: {results['errors']}")
            
        elif cmd == "single":
            video_id = sys.argv[2]
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                process_video(dict(row))
            else:
                print(f"Video not found: {video_id}")
                
        elif cmd == "export":
            video_id = sys.argv[2]
            data = export_for_summary(video_id)
            if data:
                print(json.dumps(data, indent=2))
            else:
                print(f"Video not found: {video_id}")
                
        elif cmd == "transcribed":
            videos = get_transcribed_videos()
            for v in videos:
                print(f"{v['video_id']}: {v['title'] or v['raw_text']}")
    else:
        print("Usage:")
        print("  python processor.py batch [limit] [model]  - Process batch of pending videos")
        print("  python processor.py single <video_id>      - Process single video")
        print("  python processor.py export <video_id>      - Export video for summarization")
        print("  python processor.py transcribed            - List transcribed videos")
