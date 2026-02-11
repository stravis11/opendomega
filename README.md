# Georgia Legislature Video Transcription Project

## Goal
Download, transcribe, and summarize Georgia General Assembly committee hearings and floor sessions.

## Video Sources

### House Floor Sessions
- **Archive page**: https://www.house.ga.gov/en-US/HouseFloorVideoArchives.aspx
- **Format**: YouTube links (moved from Livestream which shut down)
- **Years available**: 2021-2026

### Senate Floor Sessions  
- **Archive page**: https://www.senate.ga.gov (Senate Press Office)
- **YouTube channel**: Georgia State Senate

### Committee Meetings
- **Main portal**: https://www.legis.ga.gov/video/all (requires JS rendering)
- **GPB coverage**: https://www.gpb.org/general-assembly

## Technical Setup

### Tools installed (whisper-env)
- `yt-dlp` — YouTube/video downloading
- `openai-whisper` — Audio transcription (local, no API key needed)

### Workflow
1. **Scrape** YouTube URLs from archive pages
2. **Download** audio (mp3) using yt-dlp
3. **Transcribe** using Whisper (base/small/medium model)
4. **Summarize** key points, bills discussed, votes

### Commands

```bash
# Activate environment
cd /home/steve/.openclaw/workspace/ga-legislature
source ../whisper-env/bin/activate

# Get video info
yt-dlp --no-download -j "https://youtu.be/VIDEO_ID"

# Download audio only (faster than full video)
yt-dlp -x --audio-format mp3 -o "%(title)s.%(ext)s" "https://youtu.be/VIDEO_ID"

# Transcribe with Whisper
whisper audio.mp3 --model base --language en --output_format txt
```

## Status
- [x] Identified video sources
- [x] Set up yt-dlp and Whisper
- [ ] Test full download + transcribe pipeline
- [ ] Build scraper for YouTube URLs
- [ ] Create summarization workflow

## Notes
- Livestream.com shut down — all videos migrated to YouTube
- legis.ga.gov API requires auth (401) — scrape HTML instead
- Floor sessions run 2-4 hours; use audio-only download to save time
