# OpenDomeGA Processing Scripts

## Daily Pipeline

1. **Scrape new videos:**
   ```bash
   python3 scraper.py
   ```
   - Checks house.ga.gov + YouTube channels for new videos
   - Inserts new videos as PENDING status

2. **Extract transcripts (via summarize.sh):**
   ```bash
   # Install once:
   npm i -g @steipete/summarize
   
   # For batch processing of PENDING videos:
   python3 recover_errors.py
   ```
   - Uses YouTube captions directly (no audio download)
   - Updates status to TRANSCRIBED

3. **Summarize:**
   ```bash
   python3 summarizer.py --worker nagatha --continuous --delay 5
   ```
   - Processes all TRANSCRIBED videos
   - Uses Claude for summarization
   - Updates status to SUMMARIZED

4. **Export to website:**
   ```bash
   ./export_and_push.sh
   ```
   - Exports from Supabase to JSON files
   - Pushes to GitHub (Vercel auto-deploys)

## Environment Variables

Copy `config.env.template` to `config.env` and fill in values.
Source before running: `source config.env`

## Credentials Location

See `/memory/vercel-credentials.md` for:
- Supabase key
- GitHub token
- Vercel token

## Cron Setup

Recommended daily schedule:
```
0 6 * * * cd /path/to/scripts && ./daily-pipeline.sh
```
