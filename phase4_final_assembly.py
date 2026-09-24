import subprocess
import logging
import json
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
    """
    Converts a time string in 'HH:MM:SS' format to total seconds.
    """
    try:
        h, m, s = map(float, time_str.split(':'))
        return h * 3600 + m * 60 + s
    except ValueError as e:
        logger.error(f"Invalid time format: {time_str}. Expected HH:MM:SS.")
        raise e


def assemble_final_video(main_video_path: Path, manifest: Dict[str, str], output_path: Path) -> Path:
    """
    Assembles the final video by overlaying B-rolls onto the main video at specified timestamps.
    
    Args:
        main_video_path (Path): Path to the original input video.
        manifest (Dict[str, str]): Dictionary mapping "HH:MM:SS" to B-roll file paths.
        output_path (Path): Path to save the final rendered video.
        
    Returns:
        Path: The path to the successfully rendered final video.
    """
    if not main_video_path.exists():
        raise FileNotFoundError(f"Main video not found at {main_video_path}")

    logger.info(f"Starting final video assembly. Output will be saved to {output_path}")
    
    # Sort manifest by time to maintain a logical order in the filtergraph
    sorted_manifest = dict(sorted(manifest.items(), key=lambda item: time_to_seconds(item[0])))
    
    # Base FFmpeg command
    cmd = [
        "ffmpeg", "-y",
        "-i", str(main_video_path)
    ]
    
    # Add all B-rolls as inputs
    for time_str, broll_path in sorted_manifest.items():
        if not Path(broll_path).exists():
            raise FileNotFoundError(f"B-roll not found at {broll_path}")
        cmd.extend(["-i", str(broll_path)])

    filter_chains = []
    
    # 1. Scale main video to a standard 1920x1080 canvas to ensure consistency
    filter_chains.append("[0:v]scale=1920:1080,setsar=1[bg]")
    
    last_overlay_out = "bg"
    
    # 2. Process and overlay each B-roll
    for idx, (time_str, broll_path) in enumerate(sorted_manifest.items(), start=1):
        start_sec = time_to_seconds(time_str)
        
        # Scale B-roll to fit 1920x1080 (preserving aspect ratio, padding with black if needed)
        # Delay the start of the B-roll stream using setpts
        broll_prep = (
            f"[{idx}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:-1:-1,setsar=1,"
            f"setpts=PTS-STARTPTS+{start_sec}/TB[b{idx}]"
        )
        filter_chains.append(broll_prep)
        
        # Overlay the B-roll onto the current background
        # eof_action=pass ensures the main video resumes when the B-roll ends
        overlay_out = f"ov{idx}"
        overlay_filter = (
            f"[{last_overlay_out}][b{idx}]overlay=enable='gte(t,{start_sec})':"
            f"eof_action=pass[{overlay_out}]"
        )
        filter_chains.append(overlay_filter)
        
        last_overlay_out = overlay_out

    # Join all filter chains with semicolons
    filter_complex_str = ";".join(filter_chains)
    
    # Complete the FFmpeg command
    cmd.extend([
        "-filter_complex", filter_complex_str,
        "-map", f"[{last_overlay_out}]",  # Map the final video output
        "-map", "0:a?",                   # Map the main video's audio (if it exists)
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path)
    ])

    # Log the exact command for debugging purposes
    safe_cmd = " ".join(cmd)
    logger.info(f"Executing FFmpeg command:\n{safe_cmd}")

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        logger.info(f"Successfully rendered final video to {output_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed with error code {e.returncode}")
        logger.error(f"FFmpeg STDERR:\n{e.stderr}")
        raise RuntimeError("Video assembly failed during FFmpeg execution.") from e

    return output_path


if __name__ == "__main__":
    # ==========================================
    # TESTING BLOCK
    # ==========================================
    import tempfile
    
    def create_dummy_video(path: Path, duration: int, color: str, text: str, has_audio: bool = False):
        """Helper to generate dummy videos for testing (Text rendering removed for compatibility)."""
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=1920x1080:d={duration}"
        ]
        if has_audio:
            # Add a 440Hz sine wave audio track
            cmd.extend(["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"])
            cmd.extend(["-c:v", "libx264", "-c:a", "aac", "-shortest"])
        else:
            cmd.extend(["-c:v", "libx264"])
            
        cmd.append(str(path))
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_dir = Path(tmpdir)
        
        # 1. Create dummy main video (15 seconds, Blue, with Audio)
        main_video = temp_dir / "sample_input.mp4"
        logger.info("Generating dummy main video...")
        create_dummy_video(main_video, duration=15, color="blue", text="MAIN VIDEO", has_audio=True)
        
        # 2. Create dummy B-rolls (3 seconds each, Red and Green, no Audio)
        broll_1 = temp_dir / "broll_1.mp4"
        broll_2 = temp_dir / "broll_2.mp4"
        logger.info("Generating dummy B-roll videos...")
        create_dummy_video(broll_1, duration=3, color="red", text="B-ROLL 1 (Starts 00:00:02)")
        create_dummy_video(broll_2, duration=4, color="green", text="B-ROLL 2 (Starts 00:00:08)")
        
        # 3. Create dummy manifest (Phase 3 Output)
        dummy_manifest = {
            "00:00:02": str(broll_1),
            "00:00:08": str(broll_2)
        }
        
        # 4. Run Assembly Engine
        final_output = Path("final_rendered_portfolio.mp4")
        
        logger.info("Starting Phase 4: Final Video Assembly Engine...")
        assemble_final_video(
            main_video_path=main_video,
            manifest=dummy_manifest,
            output_path=final_output
        )
        
        logger.info(f"Test complete. Please check '{final_output}' to verify the results.")