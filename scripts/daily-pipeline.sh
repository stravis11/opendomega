#!/bin/bash
# OpenDomeGA Daily Pipeline Orchestration
# Runs: Scraper → Transcriber (via summarize.sh) → Summarizer → Export

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="/tmp/opendomega"

mkdir -p "$LOG_DIR"

# Load environment
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(cat "$SCRIPT_DIR/.env" | xargs)
else
    echo "ERROR: .env file not found at $SCRIPT_DIR/.env"
    exit 1
fi

# Ensure required env vars
if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_KEY" ] || [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ERROR: Missing required environment variables"
    exit 1
fi

# Color output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

# Step 1: Scrape new videos
log "Step 1/4: Scraping for new videos..."
if cd "$SCRIPT_DIR" && python3 scraper.py >> "$LOG_DIR/scraper.log" 2>&1; then
    success "Scraper complete"
else
    error "Scraper failed (see $LOG_DIR/scraper.log)"
    exit 1
fi

# Step 2: Extract transcripts from pending videos
log "Step 2/4: Extracting transcripts via summarize.sh..."
if cd "$SCRIPT_DIR" && python3 recover_errors.py >> "$LOG_DIR/recover_errors.log" 2>&1; then
    success "Transcript extraction complete"
else
    error "Transcript extraction failed (see $LOG_DIR/recover_errors.log)"
    exit 1
fi

# Step 3: Summarize transcribed videos
log "Step 3/4: Summarizing videos with Claude..."
if cd "$SCRIPT_DIR" && python3 summarizer.py --worker nagatha --batch 10 >> "$LOG_DIR/summarizer.log" 2>&1; then
    success "Summarizer complete"
else
    error "Summarizer error (see $LOG_DIR/summarizer.log)"
    # Don't exit — continue to export anyway
    log "Continuing to export despite summarizer error..."
fi

# Step 4: Export to website
log "Step 4/4: Exporting to GitHub + Vercel..."
if cd "$WORKSPACE_DIR" && bash export_and_push.sh >> "$LOG_DIR/export.log" 2>&1; then
    success "Export complete — website updated"
else
    error "Export failed (see $LOG_DIR/export.log)"
    exit 1
fi

log "=== Pipeline Complete ==="
success "All steps finished successfully"
echo "Logs: $LOG_DIR"
