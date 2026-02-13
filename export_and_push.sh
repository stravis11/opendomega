#!/bin/bash
# Export from Supabase and push to GitHub

cd /home/steve/.openclaw/workspace/opendomega

export SUPABASE_URL='https://czpackoyubllazezhhii.supabase.co'
export SUPABASE_KEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN6cGFja295dWJsbGF6ZXpoaGlpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA1NDExMjMsImV4cCI6MjA4NjExNzEyM30.3vtLLbGy0FQN0syklHGpbWihlu_gzWv8l_AE1zBaZ_E'

# Run export
python3 export_site_data_supabase.py 2>&1

# Check if there are changes
if git diff --quiet && git diff --staged --quiet; then
    echo "[$(date)] No changes to push"
    exit 0
fi

# Commit and push
git add -A
SUMMARY_COUNT=$(python3 -c "import json; print(json.load(open('web/data/stats.json'))['summarized'])" 2>/dev/null || echo "?")
git commit -m "Export: $SUMMARY_COUNT summarized"
git push origin main

echo "[$(date)] Pushed $SUMMARY_COUNT videos"
