import subprocess
import logging
from pathlib import Path
from typing import Dict, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def time_to_seconds(time_str: str) -> float:
    h, m, s = map(float, time_str.split(':'))
    return h * 3600 + m * 60 + s

def get_video_info(video_path: Path) -> Tuple[int, int, float]:
    """Dynamically extracts Width, Height, and exact FPS to ensure perfect sync."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0", 
        "-show_entries", "stream=width,height,r_frame_rate", "-of", "csv=s=x:p=0", str(video_path)
    ]
    try:
        out = subprocess.check_output(cmd, text=True).strip().split('x')
        w, h = int(out[0]), int(out[1])
        # محاسبه FPS از کسر (مثلاً 30000/1001 -> 29.97)
        num, den = map(float, out[2].split('/'))
        fps = num / den if den != 0 else 30.0
        return w, h, fps
    except Exception as e:
        logger.warning(f"Could not probe video info. Defaulting to 1080x1920@30fps. Error: {e}")
        return 1080, 1920, 30.0

def assemble_final_video(main_video_path: Path, matte_video_path: Path, manifest: Dict[str, str], output_path: Path) -> Path:
    main_w, main_h, main_fps = get_video_info(main_video_path)
    logger.info(f"Master Sequence: {main_w}x{main_h} @ {main_fps:.2f} FPS")
    
    sorted_manifest = list(sorted(manifest.items(), key=lambda item: time_to_seconds(item[0])))
    
    cmd = ["ffmpeg", "-y", "-i", str(main_video_path), "-i", str(matte_video_path)]
    for time_str, broll_path in sorted_manifest:
        cmd.extend(["-i", str(broll_path)])

    filter_chains = []
    
    # 1. Base Background & Transparent Foreground (Unified FPS & RGBA Color Space)
    filter_chains.append(f"[0:v]fps={main_fps},format=rgba[orig_rgba]")
    filter_chains.append(f"[1:v]fps={main_fps},format=gray[matte]")
    filter_chains.append(f"[orig_rgba][matte]alphamerge[transparent_fg]")
    
    filter_chains.append(f"[0:v]fps={main_fps},format=rgba[base_bg]")
    last_bg_out = "base_bg"
    
    # 2. Dynamic B-Roll Processing
    for idx, (time_str, broll_path) in enumerate(sorted_manifest, start=2):
        start_sec = time_to_seconds(time_str)
        list_idx = idx - 2
        
        gap = time_to_seconds(sorted_manifest[list_idx + 1][0]) - start_sec if list_idx < len(sorted_manifest) - 1 else 3.5
        is_micro_cut = gap < 2.0
        duration = gap if is_micro_cut else min(3.5, gap - 0.2)
        
        # ELITE MEMORY FIX: Trim first!
        base_prep = f"[{idx}:v]trim=0:{duration},fps={main_fps},format=rgba"
        
        if is_micro_cut:
            # ELITE ZOOMPAN: کاملاً امن بدون ارور Out-of-bounds + رنگ‌های پاپ‌شده
            broll_prep = (
                f"{base_prep},"
                f"scale={main_w}:{main_h}:force_original_aspect_ratio=increase,"
                f"crop={main_w}:{main_h}:(in_w-{main_w})/2:(in_h-{main_h})/2,"
                f"zoompan=z='min(zoom+0.003,1.3)':d={int(duration*main_fps)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={main_w}x{main_h},"
                f"eq=contrast=1.2:saturation=1.3:brightness=-0.02,"
                f"noise=alls=15:allf=t+u,"
                f"setpts=PTS-STARTPTS+{start_sec}/TB[b_processed_{idx}]"
            )
        else:
            # CINEMATIC FADE: حرکت ملایم، پس‌زمینه تیره
            broll_prep = (
                f"{base_prep},"
                f"scale={main_w}:{main_h}:force_original_aspect_ratio=increase,"
                f"crop={main_w}:{main_h}:(in_w-{main_w})/2:(in_h-{main_h})/2,"
                f"eq=contrast=1.1:saturation=0.6:brightness=-0.05,"
                f"noise=alls=10:allf=t+u,"
                f"fade=t=in:st=0:d=0.3:alpha=1,"
                f"fade=t=out:st={duration - 0.3}:d=0.3:alpha=1,"
                f"setpts=PTS-STARTPTS+{start_sec}/TB[b_processed_{idx}]"
            )
            
        filter_chains.append(broll_prep)
        
        # ELITE OVERLAY FIX: حذف shortest=1 و جایگزینی با eof_action=pass
        overlay_bg = f"bg_{idx}"
        overlay_filter = (
            f"[{last_bg_out}][b_processed_{idx}]overlay=x=0:y=0:enable='between(t,{start_sec},{start_sec+duration})':eof_action=pass[{overlay_bg}]"
        )
        filter_chains.append(overlay_filter)
        last_bg_out = overlay_bg

    # 3. Ultimate Composite: قرار دادن لایه شفافِ بدن شما روی همه‌چیز
    filter_chains.append(f"[{last_bg_out}][transparent_fg]overlay=0:0:eof_action=pass,format=yuv420p[final_v]")

    # 4. Audio Ducking (آهسته کردن صدای اصلی حین پخش B-Roll برای فوکوس بیشتر)
    audio_ducking_chains = []
    for idx, (time_str, _) in enumerate(sorted_manifest):
        start_sec = time_to_seconds(time_str)
        # اعمال افکت کم شدن صدا روی هر بازه B-Roll
        audio_ducking_chains.append(f"volume=enable='between(t,{start_sec},{start_sec+1.5})':volume=0.4")
    
    audio_filter = ",".join(audio_ducking_chains) if audio_ducking_chains else "anull"

    filter_complex_str = ";".join(filter_chains)
    
    cmd.extend([
        "-filter_complex", filter_complex_str,
        "-af", audio_filter,
        "-map", "[final_v]",
        "-map", "0:a", 
        "-c:v", "libx264",
        "-preset", "fast", 
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "320k",
        str(output_path)
    ])

    logger.info("Initiating Bug-Free Elite Compositing Engine (RAM-Optimized + Sync-Locked)...")
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg CRASH DETECTED. STDERR:\n{e.stderr}")
        raise RuntimeError("Elite Video assembly failed during FFmpeg execution.") from e

    return output_path