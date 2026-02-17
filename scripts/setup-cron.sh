#!/bin/bash
# Setup OpenDomeGA daily cron job

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DAILY_PIPELINE="$SCRIPT_DIR/daily-pipeline.sh"

# Make scripts executable
chmod +x "$DAILY_PIPELINE"
WORKSPACE_DIR="$(dirname "$SCRIPT_DIR")"
if [ -f "$WORKSPACE_DIR/export_and_push.sh" ]; then
    chmod +x "$WORKSPACE_DIR/export_and_push.sh"
fi

# Check if already installed
CRON_JOB="0 6 * * * cd $SCRIPT_DIR && ./daily-pipeline.sh"
CRON_EXISTS=$(crontab -l 2>/dev/null | grep -F "daily-pipeline.sh" | wc -l)

if [ "$CRON_EXISTS" -gt 0 ]; then
    echo "✅ Cron job already installed"
    echo ""
    echo "Current cron entry:"
    crontab -l | grep "daily-pipeline.sh"
else
    echo "Installing cron job: $CRON_JOB"
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "✅ Cron job installed"
    echo ""
    echo "Daily pipeline will run at 6:00 AM"
fi

echo ""
echo "To test manually:"
echo "  cd $SCRIPT_DIR && ./daily-pipeline.sh"
echo ""
echo "To view cron logs:"
echo "  tail -f /tmp/opendomega/*.log"
