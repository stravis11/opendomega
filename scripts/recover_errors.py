#!/usr/bin/env python3
"""
Recover error videos using summarize.sh transcript extraction.
Uses YouTube captions directly, bypassing audio download issues.
"""

import subprocess
import os
import sys
import json
from supabase import create_client

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Supabase config
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://czpackoyubllazezhhii.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

if not SUPABASE_KEY:
    print("Error: SUPABASE_KEY environment variable required")
    sys.exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_error_videos():
    """Get all videos in error status."""
    result = supabase.table('legislature_videos').select(
        'video_id,title,url,error_message'
    ).eq('status', 'error').execute()
    return result.data

def extract_transcript(url):
    """Use summarize.sh to extract transcript from YouTube URL."""
    try:
        result = subprocess.run(
            ['summarize', url, '--youtube', 'auto', '--extract'],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode != 0:
            return None, result.stderr
        
        transcript = result.stdout.strip()
        
        # Check if we got actual content (not just "Transcript:" header)
        if len(transcript) < 100:
            return None, "Transcript too short"
        
        # Remove the "Transcript:" prefix if present
        if transcript.startswith("Transcript:"):
            transcript = transcript[11:].strip()
        
        return transcript, None
        
    except subprocess.TimeoutExpired:
        return None, "Timeout"
    except Exception as e:
        return None, str(e)

def update_video_transcribed(video_id, transcript):
    """Update video status to transcribed with the new transcript."""
    supabase.table('legislature_videos').update({
        'status': 'transcribed',
        'transcript': transcript,
        'error_message': None
    }).eq('video_id', video_id).execute()

def main():
    print("=== OpenDomeGA Error Recovery ===")
    print("Using summarize.sh to extract YouTube transcripts\n")
    
    errors = get_error_videos()
    print(f"Found {len(errors)} error videos\n")
    
    recovered = 0
    still_failed = 0
    
    for i, video in enumerate(errors, 1):
        video_id = video['video_id']
        title = video['title'][:50]
        url = video.get('url', '')
        
        print(f"[{i}/{len(errors)}] {title}...")
        
        if not url:
            print("  ❌ No URL available")
            still_failed += 1
            continue
        
        transcript, error = extract_transcript(url)
        
        if transcript:
            # Got a transcript! Update the database
            update_video_transcribed(video_id, transcript)
            print(f"  ✅ Recovered ({len(transcript)} chars)")
            recovered += 1
        else:
            print(f"  ❌ Failed: {error}")
            still_failed += 1
    
    print(f"\n=== Results ===")
    print(f"Recovered: {recovered}")
    print(f"Still failed: {still_failed}")
    if len(errors) > 0:
        print(f"Recovery rate: {recovered}/{len(errors)} ({100*recovered/len(errors):.1f}%)")
    else:
        print(f"Recovery rate: N/A (no errors to recover)")
    
    if recovered > 0:
        print(f"\n{recovered} videos now in TRANSCRIBED status, ready for Nagatha's summarizer!")

if __name__ == "__main__":
    main()
