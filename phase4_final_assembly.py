# File: phase4_final_assembly.py
import subprocess
import logging
import os
from pathlib import Path
from typing import Dict, Tuple

# Elite Logging Configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Phase4_FinalAssembly")

def time_to_seconds(time_str: str) -> float:
    """تبدیل فرمت زمان به ثانیه اعشاری"""
    h, m, s = map(float, time_str.split(':'))
    return h * 3600 + m * 60 + s

def get_video_info(video_path: Path) -> Tuple[int, int, float]:
    """استخراج دقیق ابعاد و فریم‌ریت ویدیو پایه با ffprobe"""
    cmd = [
        "static_ffprobe", "-v", "error", 
        "-select_streams", "v:0", 
        "-show_entries", "stream=width,height,r_frame_rate", 
        "-of", "csv=s=x:p=0", 
        str(video_path)
    ]
    out = subprocess.check_output(cmd, text=True).strip().split('x')
    num, den = map(float, out[2].split('/'))
    return int(out[0]), int(out[1]), (num / den if den != 0 else 30.0)

def assemble_final_video(main_video_path: Path, manifest: Dict[str, str], words_ass_path: Path, output_path: Path) -> Path:
    """
    موتور رندر نهایی (Elite Cinematic Compositing Engine)
    دارای معماری Zero-Hard-Cut و Static Font Sandboxing
    """
    main_w, main_h, main_fps = get_video_info(main_video_path)
    sorted_manifest = list(sorted(manifest.items(), key=lambda item: time_to_seconds(item[0])))
    
    cmd = ["static_ffmpeg", "-y", "-i", str(main_video_path)]
    for time_str, broll_path in sorted_manifest:
        cmd.extend(["-i", str(broll_path)])

    filter_chains = [f"[0:v]fps={main_fps},format=yuv420p[base]"]
    last_out = "base"
    
    # 1. Overlay B-Rolls (Double-SETPTS Architecture)
    for idx, (time_str, broll_path) in enumerate(sorted_manifest, start=1):
        start_sec = max(0.0, time_to_seconds(time_str) - 0.5)
        duration = 3.0 
        fade_dur = 0.25 
        frames = int(duration * main_fps)
        
        # SOTA Fix: Temporal Padding (tpad) Injection
        pad_start = 0.1
        pad_end = 0.5
        adjusted_start = max(0.0, start_sec - pad_start)
        
        broll_prep = (
            f"[{idx}:v]trim=0:{duration},setpts=PTS-STARTPTS,"
            f"scale={main_w}:{main_h}:force_original_aspect_ratio=increase,"
            f"crop={main_w}:{main_h}:(in_w-{main_w})/2:(in_h-{main_h})/2,"
            f"zoompan=z='min(zoom+0.002,1.3)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={main_w}x{main_h}:fps={main_fps},"
            f"format=yuva420p,"
            f"tpad=start_duration={pad_start}:stop_duration={pad_end}:color=black@0,"
            f"fade=t=in:st={pad_start}:d={fade_dur}:alpha=1,"
            f"fade=t=out:st={pad_start + duration - fade_dur}:d={fade_dur}:alpha=1,"
            f"setpts=PTS-STARTPTS+{adjusted_start}/TB[b_prep_{idx}]" 
        )
        filter_chains.append(broll_prep)
        
        overlay_out = f"ov_{idx}"
        overlay_filter = f"[{last_out}][b_prep_{idx}]overlay=x=0:y=0:eof_action=pass[{overlay_out}]"
        filter_chains.append(overlay_filter)
        last_out = overlay_out

    # 2. ELITE ASS KARAOKE SUBTITLES (Zero-Reshaper Native HarfBuzz + Static Font Sandboxing)
    if words_ass_path and words_ass_path.exists():
        final_out = "with_ass_subs"
        
        # ایمن‌سازی مسیر فایل ASS
        ass_path_safe = str(words_ass_path.absolute()).replace('\\', '/').replace(':', '\\:')
        
        # SOTA Fix: Static Font Sandboxing
        # اتصال مستقیم به پوشه fonts که توسط شما به صورت دستی ساخته شده است
        project_root = words_ass_path.parent
        fonts_dir = project_root / "fonts"
        fonts_dir_safe = str(fonts_dir.absolute()).replace('\\', '/').replace(':', '\\:')
        
        # تزریق fontsdir به فیلتر subtitles
        filter_chains.append(f"[{last_out}]subtitles='{ass_path_safe}':fontsdir='{fonts_dir_safe}'[{final_out}]")
        last_out = final_out

    filter_complex = ";".join(filter_chains)
    
    filter_script_path = main_video_path.with_name("filter_script.txt")
    with open(filter_script_path, "w", encoding="utf-8") as f:
        f.write(filter_complex)
    
    # پیکربندی سخت‌افزاری Apple Silicon (h264_videotoolbox)
    cmd.extend([
        "-filter_complex_script", str(filter_script_path),
        "-map", f"[{last_out}]", "-map", "0:a",
        "-c:v", "h264_videotoolbox", 
        "-b:v", "8000k", 
        "-profile:v", "high",
        "-c:a", "aac", 
        "-b:a", "320k",
        str(output_path)
    ])

    logger.info("Initiating True Elite Cinematic Compositing Engine on Apple Silicon...")
    try:
        subprocess.run(cmd, check=True)
        logger.info(f"Render completed successfully: {output_path}")
    except subprocess.CalledProcessError as e:
        logger.error("CRITICAL: FFmpeg Render Failed. Check filter_script.txt for syntax errors.")
        raise

    return output_path