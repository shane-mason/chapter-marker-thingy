# Commercial Break Detector

Automatically finds good places to put chapter markers in videos by detecting black frames, silence, and scene changes.

## What it does

If you've got old TV recordings with commercials still in them, this tool finds the commercial breaks and can add chapter markers so you can skip through them easily. It uses a two-pass approach:

1. First it looks for black frames (the natural commercial breaks)
2. Then it fills in any big gaps with scene changes that also have silence nearby

## Requirements

- Python 3.x
- ffmpeg (configured in the script)
- `pip install rich`

## Usage

Process a single video:
```bash
python cmthingy.py -f video.mp4
```

Process a whole directory:
```bash
python cmthingy.py -d /path/to/videos
```

Write chapter markers to the videos:
```bash
python cmthingy.py -f video.mp4 --write-chapters
```

Overwrite the original files instead of creating `.chapters` files:
```bash
python cmthingy.py -f video.mp4 --write-chapters --overwrite
```

Adjust the maximum gap before it inserts a scene-based break (default is 12 minutes):
```bash
python cmthingy.py -f video.mp4 --max-gap 15
```

## How it works

The script runs ffmpeg to detect:
- **Black frames**: Usually indicate commercial breaks
- **Silence**: Helps confirm break points
- **Scene changes**: Used to fill large gaps when there aren't enough black frames

It scores each potential break point based on:
- Distance from ideal position (8 minute intervals)
- Presence of black frames (+10 points)
- Presence and duration of silence (+5-9 points)
- Scene changes (baseline)

Only scene changes with a score of 3+ are used (ensures silence is nearby).

## Output

Shows a nice table with:
- Timestamp
- Type (black frame or scene change)
- Confidence level
- Whether silence was detected nearby
```
                         Commercial Break Points
┏━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ # ┃ Timestamp ┃ Time (seconds) ┃     Type     ┃ Confidence ┃ Silence? ┃
┡━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━┩
│ 1 │   12:52   │        772.92s │ Scene Change │    HIGH    │    ✓     │
│ 2 │   27:22   │       1642.52s │ Black Frame  │    HIGH    │    ✓     │
│ 3 │   50:45   │       3045.62s │ Scene Change │    HIGH    │    ✓     │
│ 4 │   72:41   │       4361.65s │ Black Frame  │    HIGH    │    ✓     │
│ 5 │   74:08   │       4448.69s │ Black Frame  │    HIGH    │    ✓     │
│ 6 │  105:48   │       6348.71s │ Scene Change │    HIGH    │    ✓     │
│ 7 │  140:20   │       8420.90s │ Black Frame  │    HIGH    │          │
└───┴───────────┴────────────────┴──────────────┴────────────┴──────────┘

```
If you use `--write-chapters`:
- Creates chapter markers in FFMETADATA format and adds them to the video file
- By default, creates a new file with `.chapters` added to the name (e.g., `video.chapters.mp4`)
- With `--overwrite`, replaces the original file (writes to a temp file first, then swaps it)
- Original quality is preserved - it's just copying streams and adding metadata

## Notes

- Update the `FFMPEG` path at the top of the script to match your system
- Black frames at the very start/end of videos are ignored (not real commercial breaks)
- Use `--overwrite` carefully - it replaces your original files (though it does use a temp file for safety)
