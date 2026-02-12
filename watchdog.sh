#!/bin/bash
# Watchdog script - checks if transcriber and auto_export are running, restarts if not
# Run via cron every 5 minutes: */5 * * * * /path/to/watchdog.sh

cd /home/steve/.openclaw/workspace/ga-legislature

# Ensure PATH includes local bin for whisper/yt-dlp
export PATH="/home/steve/.local/bin:$PATH"

export SUPABASE_URL='https://czpackoyubllazezhhii.supabase.co'
export SUPABASE_KEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN6cGFja295dWJsbGF6ZXpoaGlpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA1NDExMjMsImV4cCI6MjA4NjExNzEyM30.3vtLLbGy0FQN0syklHGpbWihlu_gzWv8l_AE1zBaZ_E'

RESTARTED=""

# Check transcriber
if ! pgrep -f "transcriber.py" > /dev/null; then
    nohup python3 -u transcriber.py --worker skippy --continuous --delay 30 >> /tmp/transcriber.log 2>&1 &
    RESTARTED="transcriber"
fi

# Check auto_export
if ! pgrep -f "auto_export.py" > /dev/null; then
    nohup python3 -u auto_export.py >> /tmp/auto_export.log 2>&1 &
    if [ -n "$RESTARTED" ]; then
        RESTARTED="$RESTARTED + auto_export"
    else
        RESTARTED="auto_export"
    fi
fi

# Log restarts
if [ -n "$RESTARTED" ]; then
    echo "[$(date)] Watchdog restarted: $RESTARTED" >> /tmp/watchdog.log
fi
