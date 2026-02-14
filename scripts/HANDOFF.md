# OpenDomeGA Handoff to Nagatha

## Overview

Full ownership of the Georgia Legislature video summarization pipeline.

**Website:** https://opendomega.vercel.app  
**Repo:** https://github.com/stravis11/opendomega  
**Database:** Supabase (721 videos, 100% summarized as of 2026-02-14)

## Scripts

### 1. `scraper.py`
**Purpose:** Find new videos from GA legislature sources  
**Sources:**
- house.ga.gov archive page
- @GPBLawmakers YouTube channel
- @GeorgiaStateSenate YouTube channel

**Run:** `python3 scraper.py`  
**Output:** Inserts new videos as `status=pending` in Supabase  
**Dependencies:** None (uses stdlib only)

### 2. `recover_errors.py`
**Purpose:** Extract transcripts using `summarize.sh` (YouTube captions)  
**Run:** `python3 recover_errors.py`  
**Input:** Pulls all `status=pending` or `status=error` videos  
**Output:** Updates to `status=transcribed` with transcript  
**Dependencies:** `npm i -g @steipete/summarize`, `pip install supabase`

**Note:** Despite the name, this works for ALL videos needing transcription, not just error recovery.

### 3. `summarizer.py`
**Purpose:** Summarize transcripts using Claude  
**Run:** `python3 summarizer.py --worker nagatha --continuous --delay 5`  
**Input:** Pulls all `status=transcribed` videos  
**Output:** Updates to `status=summarized` with summary  
**Dependencies:** `pip install supabase anthropic`

**Flags:**
- `--worker NAME` — Identifies the worker (for logging)
- `--continuous` — Keep polling for new work
- `--delay N` — Seconds between polls
- `--once` — Process one video and exit

### 4. `export_site_data_supabase.py`
**Purpose:** Export summarized videos to JSON for the website  
**Run:** `python3 export_site_data_supabase.py`  
**Output:** Creates JSON files in `web/data/`, updates `web/data/index.json`  
**Dependencies:** `pip install supabase`

### 5. `export_and_push.sh` (in repo root)
**Purpose:** Run export + git push to deploy  
**Run:** `./export_and_push.sh`  
**Note:** Vercel auto-deploys on push to main

## Credentials

```bash
export SUPABASE_URL="https://czpackoyubllazezhhii.supabase.co"
export SUPABASE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN6cGFja295dWJsbGF6ZXpoaGlpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA1NDExMjMsImV4cCI6MjA4NjExNzEyM30.3vtLLbGy0FQN0syklHGpbWihlu_gzWv8l_AE1zBaZ_E"
export ANTHROPIC_API_KEY="<your key>"
```

**GitHub push:** Token is embedded in repo remote URL:
```
https://<GITHUB_TOKEN>@github.com/stravis11/opendomega.git
```
Get the actual token from Skippy or Steve's credentials store.

## Recommended Daily Pipeline

```bash
#!/bin/bash
# daily-pipeline.sh

set -e
cd /path/to/opendomega/scripts

# Load env
source config.env

# 1. Scrape for new videos
echo "=== Scraping for new videos ==="
python3 scraper.py

# 2. Extract transcripts
echo "=== Extracting transcripts ==="
python3 recover_errors.py

# 3. Summarize
echo "=== Summarizing ==="
python3 summarizer.py --worker nagatha --continuous --delay 5 &
SUMMARIZER_PID=$!

# Wait for summarizer to finish (no more transcribed videos)
sleep 30
while python3 -c "from supabase_client import LegislatureDB; db=LegislatureDB(); print(db.get_transcribed_count())" | grep -v "^0$"; do
  sleep 10
done
kill $SUMMARIZER_PID 2>/dev/null || true

# 4. Export and push
echo "=== Exporting and pushing ==="
cd ..
./export_and_push.sh

echo "=== Done ==="
```

## Cron Setup

```bash
# Daily at 6 AM EST
0 6 * * * cd /path/to/opendomega/scripts && ./daily-pipeline.sh >> /tmp/opendomega.log 2>&1
```

## Known Issues / Edge Cases

1. **Supabase timeouts** — Large queries (721+ rows) can timeout. The export script may need a retry.

2. **Long videos (5+ hours)** — `summarize.sh` handles these fine via YouTube captions. No special handling needed.

3. **Removed YouTube videos** — These will fail transcript extraction. Skip them (error status).

4. **Rate limits** — Claude API has rate limits. The summarizer has a `--delay` flag to space out requests.

5. **Git push conflicts** — Unlikely but possible if manual edits happen. Pull before push if needed.

## Status Workflow

```
pending → transcribed → summarized
                ↓
              error (if extraction/summarization fails)
```

## Monitoring

Check database status:
```python
from supabase_client import LegislatureDB
db = LegislatureDB()
print(db.get_status_counts())
```

## History

- **2026-02-11:** Project started, initial scraping
- **2026-02-12:** Parallel processing with Skippy (transcription) + Nagatha (summarization)
- **2026-02-14:** 100% completion (721/721) using `summarize.sh` for transcript extraction
- **2026-02-14:** Full handoff to Nagatha

## Contact

Questions? Ping Skippy in #bot-hangout. 🍺
