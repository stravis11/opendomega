#!/usr/bin/env python3
"""
OpenDomeGA Legislature Video Summarizer
Pulls transcribed videos from Supabase and generates summaries with Claude.

Usage:
    python summarizer.py --worker nagatha --batch 5
    python summarizer.py --worker skippy --batch 10 --continuous
"""

import os
import sys
import argparse
import time
import json
import re
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
import anthropic

# Load .env file
env_file = Path(__file__).parent / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()


class MockLegislatureDB:
    """Mock DB for testing without Supabase."""
    
    def claim_transcribed(self, worker: str) -> Optional[Dict[str, Any]]:
        return None
    
    def set_summarized(self, video_id: str, summary: str):
        print(f"[MOCK] Updated {video_id} with summary")
    
    def set_error(self, video_id: str, error_message: str):
        print(f"[MOCK] Set error for {video_id}: {error_message}")


def get_db():
    """Get database connection - real Supabase or mock for testing."""
    try:
        from supabase_client import LegislatureDB
        return LegislatureDB()
    except Exception:
        print("WARNING: Supabase not available, using mock DB")
        return MockLegislatureDB()


def chunk_transcript(transcript: str, chunk_size: int = 3000) -> list[str]:
    """Split transcript into manageable chunks for processing."""
    chunks = []
    current_chunk = ""
    sentences = transcript.split('. ')
    for sentence in sentences:
        if len(current_chunk) + len(sentence) > chunk_size:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence
        else:
            current_chunk += (". " if current_chunk else "") + sentence
    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def extract_bills_and_votes(transcript: str) -> tuple[list[str], list[str]]:
    """Extract bill numbers and vote keywords from transcript."""
    bills = []
    votes = []
    
    # Find bill references (HB, HR, SB, SR followed by numbers)
    bill_pattern = r'([HS][BR]\s*\d+)'
    bills = list(set(re.findall(bill_pattern, transcript)))
    
    # Find vote-related keywords
    vote_keywords = ['passed', 'failed', 'voted', 'unanimous', 'opposed']
    for keyword in vote_keywords:
        if keyword in transcript.lower():
            votes.append(keyword)
    
    return sorted(list(set(bills))), list(set(votes))


def generate_summary(transcript: str, title: str, video_date: str) -> str:
    """Generate a structured summary using Claude."""
    client = anthropic.Anthropic()
    bills, votes = extract_bills_and_votes(transcript)
    
    system_prompt = """You are an expert legislative summarizer.
    
Given a Georgia legislature floor session transcript, generate structured markdown:
- **Overview**: 1-2 sentences on notable aspects
- **Key Actions**: Bills passed/referred (format: "**HR XXX**: description")
- **Bills Introduced (First Reading)**: Bills introduced
- **Notable Moments**: Speeches, recognitions, procedural drama
- **Votes**: Recorded votes with outcomes
- **Attendance**: Quorum notes
- **Adjournment**: When and next session date

Focus on substantive legislation. Skip routine procedures.
Format as markdown with proper headers."""

    user_prompt = f"""Summarize this Georgia {title} session from {video_date}.
Bills mentioned: {', '.join(bills) if bills else 'None detected'}
Vote keywords: {', '.join(votes) if votes else 'None detected'}

TRANSCRIPT:
{transcript[:8000]}"""

    try:
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        return message.content[0].text
    except Exception as e:
        raise Exception(f"Claude API error: {str(e)}")


def process_video(db, video: Dict[str, Any], worker: str = "nagatha") -> bool:
    """Process a single video: generate summary and update database."""
    video_id = video.get('video_id')
    title = video.get('title', 'Unknown')
    video_date = video.get('video_date', 'Unknown')
    transcript = video.get('transcript', '')
    
    if not transcript:
        db.set_error(video_id, "Empty transcript")
        return False
    
    print(f"\n[{worker}] Processing {video_id}: {title}")
    print(f"  Transcript: {len(transcript)} chars")
    
    try:
        summary = generate_summary(transcript, title, video_date)
        db.set_summarized(video_id, summary)
        print(f"  ✓ Summary generated ({len(summary)} chars)")
        return True
    except Exception as e:
        error_msg = str(e)[:200]
        db.set_error(video_id, error_msg)
        print(f"  ✗ Error: {error_msg}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Summarize legislature videos")
    parser.add_argument("--worker", default="nagatha", help="Worker name for claiming")
    parser.add_argument("--batch", type=int, default=1, help="Videos per run")
    parser.add_argument("--continuous", action="store_true", help="Keep running until interrupted")
    parser.add_argument("--delay", type=int, default=5, help="Delay between videos (seconds)")
    
    args = parser.parse_args()
    db = get_db()
    processed = 0
    failed = 0
    
    print(f"Starting summarizer (worker: {args.worker})")
    print(f"Batch size: {args.batch}, Continuous: {args.continuous}")
    
    try:
        while True:
            for i in range(args.batch):
                video = db.claim_transcribed(worker=args.worker)
                if not video:
                    print(f"\n[{args.worker}] No transcribed videos available")
                    break
                
                success = process_video(db, video, args.worker)
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
