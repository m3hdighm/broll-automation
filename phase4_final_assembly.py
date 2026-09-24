import subprocess
import logging
from pathlib import Path
from typing import Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

def time_to_seconds(time_str: str) -> float:
    h, m, s = map(float, time_str.split(':'))
    return h * 3600 + m * 60 + s

def get_video_dimensions(video_path: Path):
    """Detects the exact width and height of the source video."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0", 
        "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(video_path)
    ]
    try:
        out = subprocess.check_output(cmd, text=True).strip()
        w, h = map(int, out.split('x'))
        return w, h
    except Exception as e:
        logger.warning(f"Could not probe dimensions, defaulting to 1920x1080. Error: {e}")
        return 1920, 1080

def assemble_final_video(main_video_path: Path, manifest: Dict[str, str], output_path: Path) -> Path:
    if not main_video_path.exists():
        raise FileNotFoundError(f"Main video not found at {main_video_path}")

    # Dynamically detect original video dimensions to prevent deformation
    main_w, main_h = get_video_dimensions(main_video_path)
    logger.info(f"Detected main video dimensions: {main_w}x{main_h}")
    
    sorted_manifest = dict(sorted(manifest.items(), key=lambda item: time_to_seconds(item[0])))
    
    cmd = ["ffmpeg", "-y", "-i", str(main_video_path)]
    for time_str, broll_path in sorted_manifest.items():
        cmd.extend(["-i", str(broll_path)])

    filter_chains = []
    
    # Map the main video natively without forcing 1920x1080
    filter_chains.append(f"[0:v]copy[bg]" if False else f"[0:v]format=yuv420p[bg]") # Ensure format is clean
    
    last_overlay_out = "bg"
    
    for idx, (time_str, broll_path) in enumerate(sorted_manifest.items(), start=1):
        start_sec = time_to_seconds(time_str)
        
        # ELITE B-ROLL PROCESSING:
        # 1. scale=increase -> Scales the B-roll so the smallest side matches the main video (no black bars).
        # 2. crop -> Center crops the B-roll to exactly match the main video dimensions (NO DEFORMATION).
        # 3. fade -> Adds a 0.5s cinematic fade-in effect using the alpha channel.
        broll_prep = (
            f"[{idx}:v]scale={main_w}:{main_h}:force_original_aspect_ratio=increase,"
            f"crop={main_w}:{main_h}:(in_w-{main_w})/2:(in_h-{main_h})/2,setsar=1,"
            f"format=yuva420p,"
            f"fade=t=in:st=0:d=0.5:alpha=1,"
            f"setpts=PTS-STARTPTS+{start_sec}/TB[b{idx}]"
        )
        filter_chains.append(broll_prep)
        
        # Overlay on the main video
        overlay_out = f"ov{idx}"
        overlay_filter = (
            f"[{last_overlay_out}][b{idx}]overlay=x=0:y=0:enable='gte(t,{start_sec})':"
            f"eof_action=pass[{overlay_out}]"
        )
        filter_chains.append(overlay_filter)
        last_overlay_out = overlay_out

    filter_complex_str = ";".join(filter_chains)
    
    cmd.extend([
        "-filter_complex", filter_complex_str,
        "-map", f"[{last_overlay_out}]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "21", # Slightly better quality for elite output
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path)
    ])

    logger.info("Executing Cinematic FFmpeg Render...")
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        logger.info(f"Successfully rendered final video to {output_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed with error code {e.returncode}")
        logger.error(f"FFmpeg STDERR:\n{e.stderr}")
        raise RuntimeError("Video assembly failed during FFmpeg execution.") from e

    return output_path