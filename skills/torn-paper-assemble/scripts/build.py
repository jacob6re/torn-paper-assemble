#!/usr/bin/env python3
"""Build four complementary torn-paper pieces and a seekable HyperFrames project."""
import argparse
import html
import json
import math
import random
import platform
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageDraw


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def number(value, name, low=0, high=1e7):
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite and in [{low}, {high}]")
    return value


def polygons(config, width, height):
    """Jitter each shared segment once, reversing it for adjacent pieces."""
    cache = {}
    result = []
    for piece in config:
        points = piece["polygon"]
        path = []
        for a, b in zip(points, points[1:] + points[:1]):
            a, b = tuple(a), tuple(b)
            key = tuple(sorted((a, b)))
            if key not in cache:
                p, q = key
                x, y = p[0] * width, p[1] * height
                dx, dy = (q[0] - p[0]) * width, (q[1] - p[1]) * height
                length = math.hypot(dx, dy)
                if length < 0.01:
                    raise ValueError("Duplicate polygon vertex")
                n = max(1, math.ceil(length / max(2, width / 260)))
                rng = random.Random(repr(key))
                edge = (p[0] == q[0] and p[0] in (0, 1)) or (p[1] == q[1] and p[1] in (0, 1))
                cache[key] = []
                for i in range(n + 1):
                    if i in (0, n):
                        endpoint = p if i == 0 else q
                        cache[key].append((endpoint[0] * width, endpoint[1] * height))
                        continue
                    offset = 0 if edge else rng.uniform(-1, 1) * max(1.2, width / 450)
                    cache[key].append((x + dx * i / n - dy / length * offset,
                                       y + dy * i / n + dx / length * offset))
            segment = cache[key] if a == key[0] else list(reversed(cache[key]))
            path.extend(segment[:-1])
        result.append(path)
    return result


def validate_background_regions(masks):
    """Require one 4-connected region per final background alpha mask."""
    for i, mask in enumerate(masks, 1):
        bbox = mask.getbbox()
        if bbox is None:
            raise ValueError(f"Background {i} is empty; exactly three complete background regions are required")
        remaining = mask.crop(bbox)
        first = remaining.tobytes().find(b"\xff")
        ImageDraw.floodfill(remaining, (first % remaining.width, first // remaining.width), 0)
        if remaining.getbbox():
            raise ValueError(
                f"Background {i} has disconnected fragments after subtracting the person "
                f"({remaining.histogram()[255]} pixels outside its first connected region). "
                "Move the shared boundary or merge fragments into an adjacent background; "
                "inspect the person mask for enclosed noise. Three layers alone are insufficient."
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--pieces", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--frame", type=float, default=0)
    parser.add_argument("--resume-duration", type=float, default=3)
    parser.add_argument("--crop", help="Explicit recording crop: x,y,width,height in source pixels")
    parser.add_argument("--person-mask", type=Path, help="Frame-sized grayscale mask: white person, black background")
    args = parser.parse_args()
    if not args.input.is_file():
        raise ValueError("Input file does not exist")
    if args.output.exists():
        raise ValueError("Output directory already exists; choose a new directory")
    config = json.loads(args.pieces.read_text())
    mode = config.get("mode", "scene")
    if mode not in ("scene", "person"):
        raise ValueError("mode must be scene or person")
    person_mode = mode == "person"
    if args.person_mask and not person_mode:
        raise ValueError("--person-mask requires mode: person")
    pieces = config["pieces"]
    if len(pieces) != 4:
        raise ValueError("Exactly four pieces are required")
    for i, piece in enumerate(pieces):
        is_person = person_mode and i == 0
        if is_person and "polygon" in piece:
            raise ValueError("Person piece uses a silhouette mask, not a polygon")
        if not is_person and len(piece["polygon"]) < 3:
            raise ValueError("Each polygon needs at least three vertices")
        for point in piece.get("polygon", []):
            if len(point) != 2:
                raise ValueError("Polygon coordinates must be pairs")
            for coordinate in point:
                number(coordinate, "polygon coordinate", 0, 1)
        if len(piece["from"]) != 2:
            raise ValueError("from must be [horizontal, vertical] in frame units")
        piece["from"] = [number(x, "from", -3, 3) for x in piece["from"]]
        piece["start"] = number(piece.get("start", i * 0.22), "start", 0, 30)
        piece["duration"] = number(piece.get("duration", 0.65), "duration", 0.1, 10)
        piece["rotation"] = number(piece.get("rotation", 0), "rotation", -30, 30)
    frame_time = number(args.frame, "frame")
    resume = number(args.resume_duration, "resume-duration", 0, 3600)
    hold = number(config.get("hold", 0.35), "hold", 0, 30)
    fade = number(config.get("seam_fade", 0.16), "seam_fade", 0.04, 2)
    border = int(number(config.get("border", 4), "border", 1, 30))
    crop = None
    if args.crop:
        crop = [int(x) for x in args.crop.split(",")]
        if len(crop) != 4 or min(crop[:2]) < 0 or min(crop[2:]) <= 0:
            raise ValueError("Invalid crop")
    has_audio = False
    try:
        with Image.open(args.input) as image:
            source = ImageOps.exif_transpose(image).convert("RGB")
        is_video = False
    except (OSError, ValueError):
        is_video = True
        info = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(args.input)]))
        has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
        video_duration = float(info["format"]["duration"])
        if frame_time >= video_duration - 0.05:
            raise ValueError("Freeze time is outside usable video range")
        resume = min(resume, video_duration - frame_time)
    args.output.mkdir(parents=True)
    assets = args.output / "assets"
    assets.mkdir()
    if is_video:
        run(["ffmpeg", "-v", "error", "-ss", str(frame_time), "-i", str(args.input), "-frames:v", "1", str(assets / "frame-raw.png")])
        source = Image.open(assets / "frame-raw.png").convert("RGB")
    if crop:
        x, y, w, h = crop
        if x + w > source.width or y + h > source.height:
            raise ValueError("Crop exceeds source dimensions")
        source = source.crop((x, y, x + w, y + h))
    # H.264 requires even dimensions; apply the same last-pixel crop to still and video.
    width, height = source.width // 2 * 2, source.height // 2 * 2
    if min(width, height) < 2:
        raise ValueError("Source must be at least 2 by 2 pixels")
    source = source.crop((0, 0, width, height))
    source.save(assets / "frame.png")
    person_mask = None
    matting = None
    if person_mode:
        if args.person_mask:
            with Image.open(args.person_mask) as supplied:
                if supplied.size != source.size or supplied.mode not in ("L", "1", "I", "F", "I;16"):
                    raise ValueError("Person mask must be a grayscale image matching the processed frame exactly")
                person_mask = supplied.convert("L")
            matting = "supplied-mask"
        elif platform.system() == "Darwin":
            helper = Path(__file__).resolve().parent / "person_mask.swift"
            run(["swift", "-module-cache-path", str(args.output / "swift-cache"), str(helper),
                 str(assets / "frame.png"), str(assets / "person-mask.png")])
            person_mask = Image.open(assets / "person-mask.png").convert("L")
            matting = "apple-vision-person"
        else:
            raise ValueError("Automatic person matting needs macOS 14+ and Swift; supply --person-mask on this platform")
        # A disjoint binary partition reconstructs the source exactly under normal alpha compositing.
        person_mask = person_mask.point(lambda x: 255 if x >= 128 else 0)
        occupied = person_mask.histogram()[255]
        if occupied < width * height * 0.001 or occupied > width * height * 0.995:
            raise ValueError("Empty, tiny or full-frame person mask; inspect and repair the mask")
        person_mask.save(assets / "person-mask.png")
    labels = Image.new("L", source.size, 0)
    overlap = Image.new("L", source.size, 0)
    background_pieces = pieces[1:] if person_mode else pieces
    for i, path in enumerate(polygons(background_pieces, width - 1, height - 1)):
        mask = Image.new("L", source.size, 0)
        ImageDraw.Draw(mask).polygon(path, fill=255)
        overlap = ImageChops.add(overlap, mask.point(lambda x: 1 if x else 0))
        labels.paste(i + 1, mask=mask)
    histogram = labels.histogram()
    if histogram[0] or sum(overlap.histogram()[2:]) > width * height * 0.025:
        raise ValueError("Polygons must cover the entire image and share matching boundaries; gaps or substantial overlaps found")
    masks = [labels.point(lambda x, label=i + 1: 255 if x == label else 0) for i in range(len(background_pieces))]
    if person_mode:
        remaining = ImageChops.invert(person_mask)
        masks = [person_mask] + [ImageChops.multiply(mask, remaining) for mask in masks]
        validate_background_regions(masks[1:])
    for i, mask in enumerate(masks):
        if not mask.getbbox():
            raise ValueError("Empty piece")
        layer = source.copy().convert("RGBA")
        layer.putalpha(mask)
        layer.save(assets / f"piece-{i}.png")
        paper_mask = mask.filter(ImageFilter.MaxFilter(border * 2 + 1))
        paper = Image.new("RGBA", source.size, "#f6f2e9")
        paper.putalpha(paper_mask)
        paper.save(assets / f"paper-{i}.png")
        bbox = mask.getbbox()
        pieces[i]["origin"] = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
    assembled = max(p["start"] + p["duration"] for p in pieces)
    seam_start = assembled + hold
    live_start = seam_start + fade
    total = live_start + (resume if is_video and resume else 0.8)
    if is_video and resume:
        vf = []
        if crop:
            vf.append("crop=" + ":".join(map(str, crop[2:] + crop[:2])))
        vf.append(f"crop={width}:{height}:0:0,setsar=1")
        run(["ffmpeg", "-v", "error", "-ss", str(frame_time), "-i", str(args.input), "-t", str(resume),
             "-vf", ",".join(vf), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-map", "0:v:0", "-map", "0:a?", "-movflags", "+faststart", str(assets / "resume.mp4")])
    shutil.copyfile(Path(__file__).resolve().parent.parent / "assets/gsap.min.js", assets / "gsap.min.js")
    markup, motion = [], []
    for i, p in enumerate(pieces):
        track = ([4, 1, 2, 3] if person_mode else [1, 2, 3, 4])[i]
        markup.append(f'<section id="piece-track-{i}" class="clip" data-start="0" data-duration="{live_start}" data-track-index="{track}" style="z-index:{track}"><div id="move-{i}" class="piece" style="transform-origin:{p["origin"][0]}px {p["origin"][1]}px"><img class="paper" src="assets/paper-{i}.png"><img src="assets/piece-{i}.png"></div></section>')
        motion.append(f'tl.fromTo("#move-{i}", {{x:{p["from"][0]*width},y:{p["from"][1]*height},rotation:{p["rotation"]}}}, {{x:0,y:0,rotation:0,duration:{p["duration"]},ease:"power3.out"}}, {p["start"]});')
    sound = 'data-has-audio="true"' if has_audio else 'muted'
    live = f'<video id="live" class="clip" data-start="{live_start}" data-duration="{resume}" data-track-index="6" src="assets/resume.mp4" {sound} playsinline preload="auto"></video>' if is_video and resume else ""
    page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>Four-piece torn-paper assembly</title>
<script src="assets/gsap.min.js"></script><style>
*{{box-sizing:border-box}} html,body{{margin:0;width:100%;height:100%;background:#000}}
#root{{position:relative;width:100%;height:100%;overflow:hidden}}
.clip,.piece,img,video{{position:absolute;inset:0;width:100%;height:100%}}
#clean-track{{z-index:5}} #live{{z-index:6}}
img,video{{object-fit:fill}} .piece{{will-change:transform}} #clean{{opacity:0}}
</style></head><body><div id="root" data-composition-id="torn-paper" data-width="{width}" data-height="{height}" data-duration="{total}" data-fps="30">
<div id="background" class="clip" data-start="0" data-duration="{total}" data-track-index="0" style="background:{html.escape(config.get('background','#000000'), quote=True)}"></div>
{''.join(markup)}
<section id="clean-track" class="clip" data-start="0" data-duration="{total}" data-track-index="5"><img id="clean" src="assets/frame.png"></section>{live}
</div><script>window.__timelines=window.__timelines||{{}}; const tl=gsap.timeline({{paused:true}});
{''.join(motion)}
tl.to("#clean",{{opacity:1,duration:{fade},ease:"none"}},{seam_start});
window.__timelines["torn-paper"]=tl;</script></body></html>'''
    (args.output / "index.html").write_text(page)
    (args.output / "hyperframes.json").write_text(json.dumps({"paths": {"assets": "assets"}}, indent=2))
    package = {"name": "torn-paper-project", "private": True, "scripts": {
        "check": "npx --yes hyperframes@0.8.161 check",
        "preview": "npx --yes hyperframes@0.8.161 preview",
        "render": "npx --yes hyperframes@0.8.161 render --quality looks"}}
    (args.output / "package.json").write_text(json.dumps(package, indent=2))
    (args.output / "pieces.json").write_text(json.dumps(config, ensure_ascii=False, indent=2))
    manifest = {"width": width, "height": height, "duration": total, "assembled": assembled,
                "seam_start": seam_start, "live_start": live_start, "source_frame": frame_time,
                "resume_duration": resume if is_video else 0, "audio": "Original resumed clip audio only; frozen introduction is silent",
                "coverage": "complete; four complementary masks", "mode": mode, "matting": matting,
                "pieces": ["person", "background-1", "background-2", "background-3"] if person_mode else ["scene-1", "scene-2", "scene-3", "scene-4"]}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as error:
        detail = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) and error.stderr else str(error)
        raise SystemExit(f"Build failed: {detail}")
