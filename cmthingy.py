import os
import subprocess
import re
import argparse
from rich.console import Console
from rich.table import Table

#FFMPEG = "/usr/bin/ffmpeg"
FFMPEG = "C:/Users/shane/bin/ffmpeg/bin/ffmpeg.exe"

console = Console()

VIDEO_EXTENSIONS = ('.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v')

def get_video_duration(video_file):
    if not os.path.isfile(FFMPEG):
        console.print(f"[red]Error: ffmpeg not found at {FFMPEG}[/red]")
        console.print(f"[yellow]Update the FFMPEG path at the top of the script[/yellow]")
        return None

    if not os.path.isfile(video_file):
        console.print(f"[red]Error: Video file not found: {video_file}[/red]")
        return None

    command = f'{FFMPEG} -i "{video_file}"'
    process = subprocess.Popen(command, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    _, error = process.communicate()

    for line in error.decode().splitlines():
        if "Duration:" in line:
            match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', line)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                seconds = float(match.group(3))
                return hours * 3600 + minutes * 60 + seconds
    return None

def get_files(directory, extensions):
    file_list = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(extensions):
                file_list.append(os.path.join(root, file))
    return file_list

def detect_black_spaces(video_file):
    command = f'{FFMPEG} -i "{video_file}" -vf fps=24,blackdetect=d=0.1 -an -f null -'
    process = subprocess.Popen(command, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    _, error = process.communicate()

    black_spaces = []
    for line in error.decode().splitlines():
        if "black_start" in line:
            parts = {}
            for part in line.split():
                if "black_start:" in part:
                    parts["start"] = float(part.split(":")[1])
                elif "black_end:" in part:
                    parts["end"] = float(part.split(":")[1])
                elif "black_duration:" in part:
                    parts["duration"] = float(part.split(":")[1])
            if parts:
                black_spaces.append(parts)
    return black_spaces

def detect_silence(video_file, noise_tolerance="-30dB", min_duration=0.3):
    command = f'{FFMPEG} -i "{video_file}" -af silencedetect=noise={noise_tolerance}:d={min_duration} -f null -'
    process = subprocess.Popen(command, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    _, error = process.communicate()

    silences = []
    silence_start = None

    for line in error.decode().splitlines():
        if "silence_start:" in line:
            try:
                # parse out the timestamp value (can't just split on : because of the timestamp format)
                start_idx = line.index("silence_start:") + len("silence_start:")
                value_str = line[start_idx:].strip().split()[0]
                silence_start = float(value_str)
            except (ValueError, IndexError):
                continue

        elif "silence_end:" in line and silence_start is not None:
            try:
                silence_end = None
                silence_duration = None

                if "silence_end:" in line:
                    end_idx = line.index("silence_end:") + len("silence_end:")
                    value_str = line[end_idx:].strip().split()[0]
                    silence_end = float(value_str)

                if "silence_duration:" in line:
                    dur_idx = line.index("silence_duration:") + len("silence_duration:")
                    value_str = line[dur_idx:].strip().split()[0]
                    silence_duration = float(value_str)

                if silence_end is not None:
                    silences.append({
                        "start": silence_start,
                        "end": silence_end,
                        "duration": silence_duration if silence_duration else silence_end - silence_start,
                        "center": (silence_start + silence_end) / 2
                    })
            except (ValueError, IndexError):
                pass
            finally:
                silence_start = None

    return silences

def clean_black_spaces(black_spaces, video_duration, start_threshold=20.0, end_threshold=10.0):
    cleaned = []
    for black in black_spaces:
        if black['start'] <= start_threshold:
            continue
        if black['end'] >= video_duration - end_threshold:
            continue

        black_with_center = black.copy()
        black_with_center['center'] = (black['start'] + black['end']) / 2
        cleaned.append(black_with_center)
    return cleaned

def format_timestamp(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"

def write_chapters_to_video(video_file, break_points, output_file=None, overwrite=False):
    if not break_points:
        console.print("[yellow]No break points to write as chapters[/yellow]")
        return None

    if output_file is None:
        if overwrite:
            # write to temp file then replace original
            base, ext = os.path.splitext(video_file)
            output_file = f"{base}.tmp{ext}"
        else:
            base, ext = os.path.splitext(video_file)
            output_file = f"{base}.chapters{ext}"

    metadata_file = f"{video_file}.ffmetadata"

    try:
        # build ffmpeg metadata file with chapter markers
        with open(metadata_file, 'w', encoding='utf-8') as f:
            f.write(";FFMETADATA1\n")

            # add chapter 1 from start if first break is far enough in
            if break_points[0]['timestamp'] > 30:
                f.write("\n[CHAPTER]\n")
                f.write("TIMEBASE=1/1000\n")
                f.write("START=0\n")
                f.write(f"END={int(break_points[0]['timestamp'] * 1000)}\n")
                f.write("title=Chapter 1\n")

            for i, bp in enumerate(break_points):
                start_time = bp['timestamp']
                if i < len(break_points) - 1:
                    end_time = break_points[i + 1]['timestamp']
                else:
                    end_time = start_time + 999999

                chapter_num = i + 2 if break_points[0]['timestamp'] > 30 else i + 1

                f.write("\n[CHAPTER]\n")
                f.write("TIMEBASE=1/1000\n")
                f.write(f"START={int(start_time * 1000)}\n")
                f.write(f"END={int(end_time * 1000)}\n")
                f.write(f"title=Chapter {chapter_num}\n")

        console.print(f"[bold yellow]Writing chapters to video file...[/bold yellow]")
        command = f'{FFMPEG} -i "{video_file}" -i "{metadata_file}" -map_metadata 1 -codec copy -y "{output_file}"'

        process = subprocess.Popen(command, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        _, error = process.communicate()

        if process.returncode == 0:
            if overwrite and output_file.endswith('.tmp' + os.path.splitext(video_file)[1]):
                try:
                    os.replace(output_file, video_file)
                    console.print(f"[bold green]✓ Chapters written successfully![/bold green]")
                    console.print(f"[dim]Updated: {video_file}[/dim]")
                    final_output = video_file
                except Exception as e:
                    console.print(f"[red]Error replacing original file: {str(e)}[/red]")
                    console.print(f"[yellow]Temporary file saved at: {output_file}[/yellow]")
                    final_output = output_file
            else:
                console.print(f"[bold green]✓ Chapters written successfully![/bold green]")
                console.print(f"[dim]Output: {output_file}[/dim]")
                final_output = output_file

            if os.path.exists(metadata_file):
                os.remove(metadata_file)
            return final_output
        else:
            console.print(f"[red]Error writing chapters[/red]")
            error_msg = error.decode()[:500] if error else "Unknown error"
            console.print(f"[dim]{error_msg}[/dim]")
            return None

    except Exception as e:
        console.print(f"[red]Error creating chapters: {str(e)}[/red]")
        if os.path.exists(metadata_file):
            os.remove(metadata_file)
        return None

def calculate_ideal_breaks(video_duration, target_minutes=8):
    ideal_positions = []
    interval = target_minutes * 60
    position = interval
    while position < video_duration - 60:
        ideal_positions.append(position)
        position += interval
    return ideal_positions

def score_break_point(timestamp, black_spaces, silences, ideal_position):
    score = 0

    # penalize distance from ideal position
    distance_penalty = abs(timestamp - ideal_position) / 60
    score -= distance_penalty * 2

    # big bonus if near a black frame
    for black in black_spaces:
        if abs(timestamp - black['center']) < 2.0:
            score += 10
            break

    # variable bonus for silence based on duration and proximity
    best_silence_score = 0
    for silence in silences:
        distance = abs(timestamp - silence['center'])
        if distance < 3.0:
            duration_bonus = min(silence['duration'], 2.0)
            proximity_bonus = (3.0 - distance) / 3.0 * 2
            silence_score = 5 + duration_bonus + proximity_bonus
            best_silence_score = max(best_silence_score, silence_score)

    score += best_silence_score
    score += 1

    return score

def find_optimal_breaks(video_duration, black_spaces, silences, scenes,
                       max_gap_minutes=12, min_breaks=None):
    break_points = []

    # pass 1: use all black frames
    for black in black_spaces:
        break_points.append({
            'timestamp': black['center'],
            'type': 'black_frame',
            'confidence': 'high'
        })

    break_points.sort(key=lambda x: x['timestamp'])

    # pass 2: fill large gaps with scene changes
    max_gap_seconds = max_gap_minutes * 60
    gaps_to_fill = []

    if break_points:
        first_gap = break_points[0]['timestamp']
        if first_gap > max_gap_seconds:
            gaps_to_fill.append((0, break_points[0]['timestamp']))

    for i in range(len(break_points) - 1):
        gap_start = break_points[i]['timestamp']
        gap_end = break_points[i + 1]['timestamp']
        gap_size = gap_end - gap_start
        if gap_size > max_gap_seconds:
            gaps_to_fill.append((gap_start, gap_end))

    if break_points:
        last_gap = video_duration - break_points[-1]['timestamp']
        if last_gap > max_gap_seconds:
            gaps_to_fill.append((break_points[-1]['timestamp'], video_duration))
    elif video_duration > max_gap_seconds:
        gaps_to_fill.append((0, video_duration))

    for gap_start, gap_end in gaps_to_fill:
        gap_center = (gap_start + gap_end) / 2
        best_scene = None
        best_score = float('-inf')

        for scene in scenes:
            timestamp = scene['timestamp']
            # skip scenes too close to gap edges
            if timestamp <= gap_start + 30 or timestamp >= gap_end - 30:
                continue

            score = score_break_point(timestamp, black_spaces, silences, gap_center)
            if score > best_score:
                best_score = score
                best_scene = scene

        # only use scene if it has a decent score (ensures silence is nearby)
        if best_scene and best_score >= 3:
            confidence = 'high' if best_score > 5 else 'medium'
            break_points.append({
                'timestamp': best_scene['timestamp'],
                'type': 'scene_change',
                'confidence': confidence,
                'score': best_score
            })

    break_points.sort(key=lambda x: x['timestamp'])
    return break_points

def print_chapter_markers(break_points, silences=None):
    table = Table(title="Commercial Break Points", show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Timestamp", style="green", justify="center")
    table.add_column("Time (seconds)", style="yellow", justify="right")
    table.add_column("Type", style="blue", justify="center")
    table.add_column("Confidence", style="magenta", justify="center")
    table.add_column("Silence?", style="dim", justify="center")

    for i, bp in enumerate(break_points, 1):
        timestamp = bp['timestamp']
        bp_type = bp.get('type', 'unknown')
        confidence = bp.get('confidence', 'unknown')

        if confidence == 'high':
            conf_str = "[green]HIGH[/green]"
        elif confidence == 'medium':
            conf_str = "[yellow]MEDIUM[/yellow]"
        else:
            conf_str = "[red]LOW[/red]"

        has_silence = ""
        if silences:
            for silence in silences:
                if abs(timestamp - silence['center']) < 3.0:
                    has_silence = "✓"
                    break

        table.add_row(
            str(i),
            format_timestamp(timestamp),
            f"{timestamp:.2f}s",
            bp_type.replace('_', ' ').title(),
            conf_str,
            has_silence
        )

    console.print(table)

def detect_scenes(video_file):
    # use scene detect filter
    command = f'{FFMPEG} -i "{video_file}" -vf "select=\'gt(scene,0.4)\',showinfo" -vsync vfr -f null -'
    process = subprocess.Popen(command, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    _, error = process.communicate()

    scenes = []
    for line in error.decode().splitlines():
        if "showinfo" in line and "pts_time:" in line:
            parts = line.split()
            timestamp = None
            for part in parts:
                if part.startswith("pts_time:"):
                    timestamp = float(part.split(":")[1])
                    break

            if timestamp is not None:
                scenes.append({
                    "timestamp": timestamp,
                    "score": None
                })
    #calc the durations
    for i in range(len(scenes)):
        if i < len(scenes) - 1:
            scenes[i]["duration"] = scenes[i + 1]["timestamp"] - scenes[i]["timestamp"]
        else:
            scenes[i]["duration"] = None

    return scenes

def process_video_file(video_file, max_gap_minutes=12, write_chapters=False, overwrite=False):
    #run through each operation
    console.print(f"\n[bold magenta]Processing:[/bold magenta] {os.path.basename(video_file)}")
    console.print(f"[dim]{video_file}[/dim]")

    duration = get_video_duration(video_file)
    if duration is None:
        console.print("[red]Error: Could not determine video duration[/red]")
        return None

    console.print(f"[bold cyan]Video duration:[/bold cyan] {duration:.2f} seconds ({duration/60:.2f} minutes)")

    console.print("[bold yellow]Detecting black spaces...[/bold yellow]")
    black_spaces = detect_black_spaces(video_file)
    console.print(f"[green]Found {len(black_spaces)} black periods[/green]")

    console.print("[bold yellow]Detecting silence periods...[/bold yellow]")
    silences = detect_silence(video_file)
    console.print(f"[green]Found {len(silences)} silence periods[/green]")

    console.print("[bold yellow]Detecting scene changes...[/bold yellow]")
    scenes = detect_scenes(video_file)
    console.print(f"[green]Found {len(scenes)} scene changes[/green]")

    cleaned_black_spaces = clean_black_spaces(black_spaces, duration)
    console.print(f"[bold cyan]Cleaned to {len(cleaned_black_spaces)} natural break points (black frames)[/bold cyan]")

    console.print("[bold yellow]Analyzing optimal break points...[/bold yellow]")
    optimal_breaks = find_optimal_breaks(
        video_duration=duration,
        black_spaces=cleaned_black_spaces,
        silences=silences,
        scenes=scenes,
        max_gap_minutes=max_gap_minutes
    )

    console.print(f"[bold green]Selected {len(optimal_breaks)} commercial break points[/bold green]")

    print()
    print_chapter_markers(optimal_breaks, silences)

    if write_chapters and optimal_breaks:
        print()
        write_chapters_to_video(video_file, optimal_breaks, overwrite=overwrite)

    return optimal_breaks


def main():
    parser = argparse.ArgumentParser(
        description='Detect commercial break points in video files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cmthingy.py -f video.mp4
  python cmthingy.py -d /path/to/videos
  python cmthingy.py -f video.mp4 --max-gap 15
  python cmthingy.py -f video.mp4 --write-chapters
  python cmthingy.py -f video.mp4 --write-chapters --overwrite
  python cmthingy.py -d /path/to/videos --write-chapters --overwrite
        """
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-f', '--file', type=str, help='Process a single video file')
    group.add_argument('-d', '--dir', type=str, help='Process all video files in directory (recursive)')

    parser.add_argument('--max-gap', type=int, default=12,
                       help='Maximum gap in minutes before inserting scene-based break (default: 12)')
    parser.add_argument('--write-chapters', action='store_true',
                       help='Write chapter markers to video file')
    parser.add_argument('--overwrite', action='store_true',
                       help='Overwrite original file instead of creating .chapters file')

    args = parser.parse_args()

    if args.file:
        if not os.path.isfile(args.file):
            console.print(f"[red]Error: File not found: {args.file}[/red]")
            return 1
        process_video_file(args.file, max_gap_minutes=args.max_gap, write_chapters=args.write_chapters, overwrite=args.overwrite)

    elif args.dir:
        if not os.path.isdir(args.dir):
            console.print(f"[red]Error: Directory not found: {args.dir}[/red]")
            return 1

        video_files = get_files(args.dir, VIDEO_EXTENSIONS)
        if not video_files:
            console.print(f"[yellow]No video files found in {args.dir}[/yellow]")
            return 0

        console.print(f"[bold cyan]Found {len(video_files)} video file(s)[/bold cyan]")
        for i, video_file in enumerate(video_files, 1):
            console.print(f"\n[bold]═══ File {i}/{len(video_files)} ═══[/bold]")
            process_video_file(video_file, max_gap_minutes=args.max_gap, write_chapters=args.write_chapters, overwrite=args.overwrite)

    return 0


if __name__ == "__main__":
    exit(main())