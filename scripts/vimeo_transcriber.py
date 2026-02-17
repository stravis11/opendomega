#!/usr/bin/env python3
"""
Vimeo Video Transcriber
Downloads audio from Vimeo videos and extracts transcripts using summarize.sh + Groq
"""

import os
import sys
import subprocess
import tempfile
from pathlib import Path
from supabase import create_client

# Groq API key (should be set in environment)
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

# Supabase config
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://czpackoyubllazezhhii.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

if not SUPABASE_KEY:
    print("Error: SUPABASE_KEY environment variable required")
    sys.exit(1)

if not GROQ_API_KEY:
    print("Warning: GROQ_API_KEY not set, will use local Whisper (slower)")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_pending_vimeo_videos(limit: int = 10):
    """Get Vimeo videos in PENDING status from Supabase"""
    result = supabase.table('legislature_videos').select(
        'video_id,url,title,platform'
    ).eq('status', 'pending').eq('platform', 'vimeo').limit(limit).execute()
    
    return result.data


def download_vimeo_audio(url: str, output_path: str) -> bool:
    """Download audio from Vimeo URL using yt-dlp"""
    try:
        cmd = [
            'yt-dlp',
            '-f', 'bestaudio/best',
            '-x',
            '--audio-format', 'mp3',
            '-o', output_path,
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode == 0 and os.path.exists(output_path):
            return True
        else:
            print(f"  ❌ Download failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def extract_transcript(audio_path: str) -> tuple[str, str]:
    """Extract transcript from audio file using summarize.sh + Groq"""
    try:
        cmd = ['summarize', audio_path, '--extract']
        
        # Add Groq API key if available
        env = os.environ.copy()
        if GROQ_API_KEY:
            env['GROQ_API_KEY'] = GROQ_API_KEY
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
            env=env
        )
        
        if result.returncode != 0:
            return None, result.stderr
        
        transcript = result.stdout.strip()
        
        # Remove "Transcript:" prefix if present
        if transcript.startswith("Transcript:"):
            transcript = transcript[11:].strip()
        
        if len(transcript) < 100:
            return None, "Transcript too short"
        
        return transcript, None
        
    except subprocess.TimeoutExpired:
        return None, "Timeout"
    except Exception as e:
        return None, str(e)


def update_video_transcribed(video_id: str, transcript: str):
    """Update video status to transcribed with transcript"""
    supabase.table('legislature_videos').update({
        'status': 'transcribed',
        'transcript': transcript,
    }).eq('video_id', video_id).execute()


def update_video_error(video_id: str, error_msg: str):
    """Update video status to error"""
    supabase.table('legislature_videos').update({
        'status': 'error',
        'error_message': error_msg,
    }).eq('video_id', video_id).execute()


def process_vimeo_batch(limit: int = 10):
    """Process a batch of pending Vimeo videos"""
    print("=== Vimeo Video Transcriber ===")
    print(f"Processing up to {limit} videos...\n")
    
    videos = get_pending_vimeo_videos(limit)
    print(f"Found {len(videos)} pending Vimeo videos\n")
    
    processed = 0
    succeeded = 0
    failed = 0
    
    for video in videos:
        video_id = video['video_id']
        title = video['title'][:50]
        url = video['url']
        
        print(f"[{processed + 1}/{len(videos)}] {title}...")
        
        # Create temp file for audio
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
            audio_path = tmp.name
        
        try:
            # Step 1: Download audio from Vimeo
            print(f"  Downloading audio...")
            if not download_vimeo_audio(url, audio_path):
                update_video_error(video_id, "Download failed")
                failed += 1
                continue
            
            # Step 2: Extract transcript
            print(f"  Extracting transcript...")
            transcript, error = extract_transcript(audio_path)
            
            if transcript:
                # Save transcript to database
                update_video_transcribed(video_id, transcript)
                print(f"  ✅ Success ({len(transcript)} chars)")
                succeeded += 1
            else:
                print(f"  ❌ Failed: {error}")
                update_video_error(video_id, error or "Unknown error")
                failed += 1
        
        finally:
            # Clean up temp file
            if os.path.exists(audio_path):
                os.remove(audio_path)
        
        processed += 1
    
    # Summary
    print(f"\n=== Results ===")
    print(f"Processed: {processed}")
    print(f"Succeeded: {succeeded}")
    print(f"Failed: {failed}")
    
    if succeeded > 0:
        print(f"\n{succeeded} videos now in TRANSCRIBED status, ready for Claude summarization!")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    process_vimeo_batch(limit)
