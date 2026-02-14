#!/usr/bin/env python3
"""
Supabase client for OpenDomeGA legislature video processing.
Used by both Skippy and Nagatha for parallel processing.

Usage:
    from supabase_client import LegislatureDB
    
    db = LegislatureDB()
    
    # Claim next pending video for transcription
    video = db.claim_pending(worker='skippy')
    
    # Claim next transcribed video for summarization
    video = db.claim_transcribed(worker='nagatha')
    
    # Update with transcript
    db.set_transcribed(video_id, transcript)
    
    # Update with summary
    db.set_summarized(video_id, summary)
"""

import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from supabase import create_client, Client

# Configuration - set these environment variables
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://czpackoyubllazezhhii.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

TABLE = 'legislature_videos'
STALE_HOURS = 2  # Reclaim jobs older than this


class LegislatureDB:
    def __init__(self, url: str = None, key: str = None):
        self.url = url or SUPABASE_URL
        self.key = key or SUPABASE_KEY
        if not self.key:
            raise ValueError("SUPABASE_KEY environment variable required")
        self.client: Client = create_client(self.url, self.key)
    
    def claim_pending(self, worker: str) -> Optional[Dict[str, Any]]:
        """
        Atomically claim the next pending video for transcription.
        Returns the video record or None if no pending videos.
        """
        # First, reclaim any stale jobs
        self._reclaim_stale()
        
        # Get next pending video (prioritize recent years)
        result = self.client.table(TABLE) \
            .select('*') \
            .eq('status', 'pending') \
            .order('session_year', desc=True) \
            .order('video_date', desc=True) \
            .limit(1) \
            .execute()
        
        if not result.data:
            return None
        
        video = result.data[0]
        video_id = video['video_id']
        
        # Try to claim it (atomic update with condition)
        update_result = self.client.table(TABLE) \
            .update({
                'status': 'processing',
                'claimed_by': worker,
                'claimed_at': datetime.utcnow().isoformat()
            }) \
            .eq('video_id', video_id) \
            .eq('status', 'pending') \
            .execute()
        
        if update_result.data:
            return update_result.data[0]
        else:
            # Someone else claimed it, try again
            return self.claim_pending(worker)
    
    def claim_transcribed(self, worker: str) -> Optional[Dict[str, Any]]:
        """
        Atomically claim the next transcribed video for summarization.
        Returns the video record or None if no transcribed videos.
        """
        self._reclaim_stale()
        
        result = self.client.table(TABLE) \
            .select('*') \
            .eq('status', 'transcribed') \
            .order('session_year', desc=True) \
            .order('video_date', desc=True) \
            .limit(1) \
            .execute()
        
        if not result.data:
            return None
        
        video = result.data[0]
        video_id = video['video_id']
        
        update_result = self.client.table(TABLE) \
            .update({
                'status': 'summarizing',
                'claimed_by': worker,
                'claimed_at': datetime.utcnow().isoformat()
            }) \
            .eq('video_id', video_id) \
            .eq('status', 'transcribed') \
            .execute()
        
        if update_result.data:
            return update_result.data[0]
        else:
            return self.claim_transcribed(worker)
    
    def set_transcribed(self, video_id: str, transcript: str, duration_seconds: int = None):
        """Mark video as transcribed with the transcript text."""
        update = {
            'transcript': transcript,
            'status': 'transcribed',
            'claimed_by': None,
            'claimed_at': None,
            'updated_at': datetime.utcnow().isoformat()
        }
        if duration_seconds:
            update['duration_seconds'] = duration_seconds
        
        self.client.table(TABLE) \
            .update(update) \
            .eq('video_id', video_id) \
            .execute()
    
    def set_summarized(self, video_id: str, summary: str):
        """Mark video as summarized with the summary text."""
        self.client.table(TABLE) \
            .update({
                'summary': summary,
                'status': 'summarized',
                'claimed_by': None,
                'claimed_at': None,
                'updated_at': datetime.utcnow().isoformat()
            }) \
            .eq('video_id', video_id) \
            .execute()
    
    def set_error(self, video_id: str, error_message: str):
        """Mark video as errored."""
        self.client.table(TABLE) \
            .update({
                'status': 'error',
                'error_message': error_message,
                'claimed_by': None,
                'claimed_at': None,
                'updated_at': datetime.utcnow().isoformat()
            }) \
            .eq('video_id', video_id) \
            .execute()
    
    def get_stats(self) -> Dict[str, int]:
        """Get counts by status."""
        result = self.client.table(TABLE) \
            .select('status') \
            .execute()
        
        stats = {}
        for row in result.data:
            status = row['status']
            stats[status] = stats.get(status, 0) + 1
        return stats
    
    def get_by_status(self, status: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get videos by status."""
        result = self.client.table(TABLE) \
            .select('*') \
            .eq('status', status) \
            .order('session_year', desc=True) \
            .order('video_date', desc=True) \
            .limit(limit) \
            .execute()
        return result.data
    
    def _reclaim_stale(self):
        """Reclaim jobs that have been processing for too long."""
        stale_time = (datetime.utcnow() - timedelta(hours=STALE_HOURS)).isoformat()
        
        self.client.table(TABLE) \
            .update({
                'status': 'pending',
                'claimed_by': None,
                'claimed_at': None
            }) \
            .eq('status', 'processing') \
            .lt('claimed_at', stale_time) \
            .execute()
        
        self.client.table(TABLE) \
            .update({
                'status': 'transcribed',
                'claimed_by': None,
                'claimed_at': None
            }) \
            .eq('status', 'summarizing') \
            .lt('claimed_at', stale_time) \
            .execute()


if __name__ == '__main__':
    # Quick test
    db = LegislatureDB()
    stats = db.get_stats()
    print("Current status counts:")
    for status, count in sorted(stats.items()):
        print(f"  {status}: {count}")
