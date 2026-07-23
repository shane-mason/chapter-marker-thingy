import os
import re
import random
import subprocess
import argparse
from rich.console import Console

FFMPEG = "/usr/bin/ffmpeg"
FFPROBE = "/usr/bin/ffprobe"

console = Console()


def get_chapters(video_file):
    command = [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_chapters", video_file]
    process = subprocess.Popen(command, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    stdout, _ = process.communicate()
    if process.returncode != 0:
        return None
    import json
    data = json.loads(stdout.decode())
    return data.get("chapters", [])


def dump_metadata(video_file):
    command = [FFMPEG, "-i", video_file, "-f", "ffmetadata", "-"]
    process = subprocess.Popen(command, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    stdout, _ = process.communicate()
    if process.returncode != 0:
        return None
    return stdout.decode()


def parse_chapter_blocks(metadata):
    """Split metadata into a preamble and a list of chapter blocks."""
    # Split on [CHAPTER] boundaries
    parts = re.split(r'(?=\[CHAPTER\])', metadata)
    preamble = parts[0]
    chapters = parts[1:]
    return preamble, chapters


def reapply_metadata(video_file, metadata_text, output_file):
    metadata_path = video_file + ".ffmetadata"
    with open(metadata_path, "w", encoding="utf-8") as f:
        f.write(metadata_text)

    command = [
        FFMPEG,
        "-i", video_file,
        "-i", metadata_path,
        "-map_metadata", "1",
        "-map_chapters", "1",
        "-c", "copy",
        "-y",
        output_file,
    ]
    process = subprocess.Popen(command, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    _, error = process.communicate()
    os.remove(metadata_path)
    return process.returncode == 0, error.decode()


def remove_chapter(video_file, index, output_file):
    chapters = get_chapters(video_file)
    if chapters is None:
        console.print("[red]Error: could not read chapters[/red]")
        return 1

    if not chapters:
        console.print("[yellow]No chapters found in file[/yellow]")
        return 1

    if index < 1 or index > len(chapters):
        console.print(f"[red]Error: chapter index {index} out of range (file has {len(chapters)} chapters)[/red]")
        return 1

    metadata = dump_metadata(video_file)
    if metadata is None:
        console.print("[red]Error: could not dump metadata[/red]")
        return 1

    preamble, chapter_blocks = parse_chapter_blocks(metadata)

    if len(chapter_blocks) != len(chapters):
        console.print(f"[red]Error: chapter count mismatch ({len(chapter_blocks)} blocks vs {len(chapters)} from ffprobe)[/red]")
        return 1

    removed = chapter_blocks.pop(index - 1)
    console.print(f"[dim]Removing:[/dim]\n{removed.strip()}")

    new_metadata = preamble + "".join(chapter_blocks)
    ok, error = reapply_metadata(video_file, new_metadata, output_file)

    if ok:
        console.print(f"[green]✓ Written to {output_file}[/green]")
        return 0
    else:
        console.print(f"[red]✗ Failed[/red]\n[dim]{error[-500:]}[/dim]")
        return 1


def has_chapters(video_file):
    """Return True if the file has chapter markers, False if not, None on error."""
    chapters = get_chapters(video_file)
    if chapters is None:
        return None
    return len(chapters) > 0


def detect_chapters(video_file):
    """Report whether a file has chapter markers.

    Exit codes: 0 = has chapters, 1 = none, 2 = error (script-friendly).
    """
    result = has_chapters(video_file)
    if result is None:
        console.print("[red]Error: could not read chapters[/red]")
        return 2

    if result:
        console.print("[green]✓ Chapter markers present[/green]")
        return 0
    else:
        console.print("[yellow]No chapter markers[/yellow]")
        return 1


def generate_chapters(video_file, output_file, skip_existing=False):
    import json

    if skip_existing:
        existing = has_chapters(video_file)
        if existing is None:
            console.print("[red]Error: could not read chapters[/red]")
            return 1
        if existing:
            console.print(f"[yellow]Skipping {video_file}: already has chapter markers[/yellow]")
            return 2

    command = [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", video_file]
    process = subprocess.Popen(command, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    stdout, _ = process.communicate()
    if process.returncode != 0:
        console.print("[red]Error: could not read video duration[/red]")
        return 1

    data = json.loads(stdout.decode())
    duration = float(data["format"]["duration"])
    duration_ms = int(duration * 1000)

    first = random.randint(40, 60) * 1000
    num_extra = random.randint(2, 3)

    # spread remaining chapters evenly with some randomness
    segment = (duration_ms - first) // (num_extra + 1)
    starts = [first]
    for i in range(1, num_extra + 1):
        midpoint = first + segment * i
        jitter = random.randint(-30, 30) * 1000
        starts.append(max(first + 10000, min(duration_ms - 10000, midpoint + jitter)))
    starts = sorted(set(starts))

    metadata = ";FFMETADATA1\n"
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else duration_ms
        metadata += f"\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={start}\nEND={end}\ntitle=Chapter {i + 1}\n"

    for s in starts:
        m, sec = divmod(s // 1000, 60)
        console.print(f"  Chapter {starts.index(s) + 1} at {m}:{sec:02d}")

    ok, error = reapply_metadata(video_file, metadata, output_file)
    if ok:
        console.print(f"[green]✓ Written to {output_file}[/green]")
        return 0
    else:
        console.print(f"[red]✗ Failed[/red]\n[dim]{error[-500:]}[/dim]")
        return 1


def list_chapters(video_file):
    chapters = get_chapters(video_file)
    if chapters is None:
        console.print("[red]Error: could not read chapters[/red]")
        return 1

    if not chapters:
        console.print("[yellow]No chapters found[/yellow]")
        return 0

    for i, ch in enumerate(chapters, 1):
        start = float(ch["start_time"])
        title = ch.get("tags", {}).get("title", "(untitled)")
        minutes = int(start // 60)
        secs = int(start % 60)
        console.print(f"  [cyan]{i}[/cyan]  {minutes}:{secs:02d}  [dim]{title}[/dim]")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Inspect and edit chapter markers in a video file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cmchapter.py list -f video.mp4
  python cmchapter.py detect -f video.mp4
  python cmchapter.py remove -f video.mp4 --index 1
  python cmchapter.py remove -f video.mp4 --index 1 -o out.mp4
  python cmchapter.py generate -f video.mp4 --skip-existing
        """,
    )

    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list", help="List chapters in a file")
    list_p.add_argument("-f", "--file", required=True)

    detect_p = sub.add_parser("detect", help="Detect whether a file has chapter markers")
    detect_p.add_argument("-f", "--file", required=True)

    rm_p = sub.add_parser("remove", help="Remove a chapter by index")
    rm_p.add_argument("-f", "--file", required=True)
    rm_p.add_argument("--index", type=int, default=1, help="Chapter number to remove (default: 1)")
    rm_p.add_argument("-o", "--output", help="Output file (default: overwrites input via temp file)")

    gen_p = sub.add_parser("generate", help="Write random test chapters to a file")
    gen_p.add_argument("-f", "--file", required=True)
    gen_p.add_argument("-o", "--output", help="Output file (default: overwrites input via temp file)")
    gen_p.add_argument("--skip-existing", action="store_true",
                       help="Do not modify the file if it already has chapter markers")

    args = parser.parse_args()

    if args.command == "list":
        return list_chapters(os.path.expanduser(args.file))

    if args.command == "detect":
        return detect_chapters(os.path.expanduser(args.file))

    if args.command == "remove":
        video_file = os.path.expanduser(args.file)
        if args.output:
            output_file = os.path.expanduser(args.output)
        else:
            base, ext = os.path.splitext(video_file)
            output_file = base + ".tmp" + ext

        ret = remove_chapter(video_file, args.index, output_file)

        if ret == 0 and not args.output:
            os.replace(output_file, video_file)
            console.print(f"[dim]Replaced original: {video_file}[/dim]")

        return ret

    if args.command == "generate":
        video_file = os.path.expanduser(args.file)
        if args.output:
            output_file = os.path.expanduser(args.output)
        else:
            base, ext = os.path.splitext(video_file)
            output_file = base + ".tmp" + ext

        ret = generate_chapters(video_file, output_file, skip_existing=args.skip_existing)

        if ret == 0 and not args.output:
            os.replace(output_file, video_file)
            console.print(f"[dim]Replaced original: {video_file}[/dim]")

        return ret


if __name__ == "__main__":
    exit(main())