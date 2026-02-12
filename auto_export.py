#!/usr/bin/env python3
"""
Auto-export summarized videos to GitHub in batches.
Runs continuously, checking every 5 minutes.
Exports and pushes when 10+ new summaries are ready.
"""

import os
import sys
import time
import subprocess
import json
from pathlib import Path
from datetime import datetime

# Add parent dir for imports
sys.path.insert(0, str(Path(__file__).parent))

from supabase import create_client

SUPABASE_URL = "https://czpackoyubllazezhhii.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN6cGFja295dWJsbGF6ZXpoaGlpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA1NDExMjMsImV4cCI6MjA4NjExNzEyM30.3vtLLbGy0FQN0syklHGpbWihlu_gzWv8l_AE1zBaZ_E")

STATE_FILE = Path(__file__).parent / ".export_state.json"
BATCH_SIZE = 10  # Export when this many new summaries exist
CHECK_INTERVAL = 300  # 5 minutes

def get_summary_count():
    """Get current count of summarized videos from Supabase."""
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    result = client.table('legislature_videos').select('id', count='exact').eq('status', 'summarized').execute()
    return result.count

def load_state():
    """Load last exported count."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_exported_count": 0, "last_export_time": None}

def save_state(count):
    """Save current exported count."""
    with open(STATE_FILE, 'w') as f:
        json.dump({
            "last_exported_count": count,
            "last_export_time": datetime.now().isoformat()
        }, f, indent=2)

def run_export():
    """Run the export script."""
    script = Path(__file__).parent / "export_site_data_supabase.py"
    result = subprocess.run(
        ["python3", str(script)],
        cwd=script.parent,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"Export failed: {result.stderr}")
        return False
    print(result.stdout)
    return True

def git_push(count):
    """Commit and push changes."""
    repo_dir = Path(__file__).parent
    
    # Add all data files
    subprocess.run(["git", "add", "web/data/"], cwd=repo_dir, check=True)
    
    # Check if there are changes to commit
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo_dir
    )
    if result.returncode == 0:
        print("No changes to commit")
        return True
    
    # Commit
    msg = f"Auto-export: {count} videos summarized"
    subprocess.run(["git", "commit", "-m", msg], cwd=repo_dir, check=True)
    
    # Push
    result = subprocess.run(
        ["git", "push"],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"Push failed: {result.stderr}")
        return False
    
    print(f"Pushed: {msg}")
    return True

def main():
    print(f"[auto_export] Starting batch export loop (batch size: {BATCH_SIZE})")
    print(f"[auto_export] Checking every {CHECK_INTERVAL}s")
    
    while True:
        try:
            state = load_state()
            current_count = get_summary_count()
            last_count = state["last_exported_count"]
            new_count = current_count - last_count
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Summarized: {current_count} (new: {new_count})")
            
            if new_count >= BATCH_SIZE:
                print(f"[auto_export] {new_count} new summaries, exporting...")
                if run_export() and git_push(current_count):
                    save_state(current_count)
                    print(f"[auto_export] Successfully exported {current_count} summaries")
            
        except Exception as e:
            print(f"[auto_export] Error: {e}")
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
