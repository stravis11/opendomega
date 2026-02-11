#!/usr/bin/env python3
"""
OpenDomeGA Video Transcriber
Downloads audio and transcribes with Whisper, updates Supabase.

Requires: whisper, yt-dlp, ffmpeg

Usage:
    python transcriber.py --worker skippy --batch 5
    python transcriber.py --worker nagatha --continuous
"""

import os
import sys
import argparse
import subprocess
import tempfile
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# Try to import supabase client
try:
    from supabase_client import LegislatureDB
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    print("WARNING: supabase_client not available")


def check_dependencies():
    """Check if required tools are installed."""
    deps = {
        'whisper': 'pip install openai-whisper',
        'yt-dlp': 'pip install yt-dlp',
        'ffmpeg': 'brew install ffmpeg / apt install ffmpeg'
    }
    
    missing = []
    for cmd, install in deps.items():
        result = subprocess.run(['which', cmd], capture_output=True)
        if result.returncode != 0:
            missing.append(f"{cmd} ({install})")
    
    if missing:
        print("Missing dependencies:")
        for m in missing:
            print(f"  - {m}")
        return False
    return True


def download_audio(video_id: str, url: str, output_dir: Path) -> Optional[Path]:
    """Download audio from YouTube video."""
    output_path = output_dir / f"{video_id}.m4a"
    
    if output_path.exists():
        print(f"  Audio already exists: {output_path}")
        return output_path
    
    # Strip timestamp from URL (e.g., ?t=1172) - it can cause issues
    clean_url = url.split('?')[0] if '?' in url else url
    
    print(f"  Downloading audio...")
    cmd = [
        "yt-dlp",
        "-f", "bestaudio[ext=m4a]/bestaudio/140",  # Flexible format selection
        "-o", str(output_path),
        "--no-playlist",
        "--retries", "3",  # Retry on failure
        "--fragment-retries", "3",
        "--socket-timeout", "30",  # 30s socket timeout
        clean_url
    ]
    
    try:
        # Increased timeout: 30 min for longer videos (~175MB at slow speeds)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            print(f"  Download error: {result.stderr[:500]}")
            return None
        return output_path
    except subprocess.TimeoutExpired:
        print("  Download timed out (>30 min)")
        return None


def transcribe_audio(audio_path: Path, model: str = "base") -> Optional[str]:
    """Transcribe audio using Whisper."""
    print(f"  Transcribing with Whisper {model}...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "whisper",
            str(audio_path),
            "--model", model,
            "--language", "en",
            "--output_format", "txt",
            "--output_dir", tmpdir,
            "--condition_on_previous_text", "False",  # Prevent hallucination
            "--no_speech_threshold", "0.6",
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
            if result.returncode != 0:
                print(f"  Transcription error: {result.stderr[:200]}")
                return None
            
            # Find output file
            txt_files = list(Path(tmpdir).glob("*.txt"))
            if txt_files:
                return txt_files[0].read_text()
            return None
        except subprocess.TimeoutExpired:
            print("  Transcription timed out (>2 hours)")
            return None


def get_video_duration(url: str) -> int:
    """Get video duration in seconds."""
    cmd = ["yt-dlp", "--no-download", "-j", url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            return data.get("duration", 0)
    except:
        pass
    return 0


def process_video(db, video: Dict[str, Any], worker: str, model: str = "base") -> bool:
    """Process a single video: download and transcribe."""
    video_id = video['video_id']
    url = video['url']
    title = video.get('title', 'Unknown')
    
    print(f"\n[{worker}] Processing: {title}")
    print(f"  Video ID: {video_id}")
    print(f"  URL: {url}")
    
    # Get duration
    duration = get_video_duration(url)
    if duration:
        print(f"  Duration: {duration//60} minutes")
    
    # Skip very long videos (> 4 hours)
    if duration > 14400:
        print(f"  Skipping: too long ({duration//3600}h)")
        db.set_error(video_id, f"Video too long: {duration//3600}h")
        return False
    
    # Create temp directory for audio
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Download audio
        audio_path = download_audio(video_id, url, tmpdir)
        if not audio_path:
            db.set_error(video_id, "Failed to download audio")
            return False
        
        # Transcribe
        transcript = transcribe_audio(audio_path, model)
        if not transcript:
            db.set_error(video_id, "Failed to transcribe")
            return False
        
        # Update database
        db.set_transcribed(video_id, transcript, duration)
        print(f"  ✓ Transcribed ({len(transcript)} chars)")
        return True


def main():
    parser = argparse.ArgumentParser(description="Transcribe legislature videos")
    parser.add_argument("--worker", default="transcriber", help="Worker name")
    parser.add_argument("--batch", type=int, default=1, help="Videos per run")
    parser.add_argument("--continuous", action="store_true", help="Keep running")
    parser.add_argument("--model", default="base", help="Whisper model (tiny/base/small/medium)")
    parser.add_argument("--delay", type=int, default=30, help="Delay between videos (default 30s to avoid rate limiting)")
    
    args = parser.parse_args()
    
    # Check dependencies
    if not check_dependencies():
        print("\nInstall missing dependencies and try again.")
        sys.exit(1)
    
    # Get database
    if not HAS_SUPABASE:
        print("ERROR: Supabase client required. Set SUPABASE_URL and SUPABASE_KEY env vars.")
        sys.exit(1)
    
    db = LegislatureDB()
    processed = 0
    failed = 0
    
    print(f"Starting transcriber (worker: {args.worker}, model: {args.model})")
    
    try:
        while True:
            for i in range(args.batch):
                video = db.claim_pending(worker=args.worker)
                if not video:
                    print(f"\n[{args.worker}] No pending videos available")
                    break
                
                success = process_video(db, video, args.worker, args.model)
                if success:
                    processed += 1
                else:
                    failed += 1
                
                if i < args.batch - 1:
                    time.sleep(args.delay)
            
            if not args.continuous:
                break
            
            print(f"\n[{args.worker}] Waiting before next batch...")
            time.sleep(args.delay)
    
    except KeyboardInterrupt:
        print("\n\nShutdown requested")
    
    print(f"\nProcessed: {processed}, Failed: {failed}")


if __name__ == '__main__':
    main()
