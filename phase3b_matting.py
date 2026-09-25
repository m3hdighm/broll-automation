import cv2
import numpy as np
from rembg import remove, new_session
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Phase3b_Matting")

def generate_alpha_matte(input_video_path: Path) -> Path:
    """
    Studio-Grade Semantic Segmentation using U^2-Net (rembg).
    Creates a flawless cinematic alpha matte for depth compositing.
    """
    if not input_video_path.exists():
        raise FileNotFoundError(f"Input video not found: {input_video_path}")

    output_matte_path = input_video_path.with_name(f"{input_video_path.stem}_matte.mp4")
    
    if output_matte_path.exists() and output_matte_path.stat().st_size > 0:
        logger.info(f"Matte already exists at {output_matte_path}. Skipping generation.")
        return output_matte_path

    logger.info("Initializing Elite Studio-Grade AI Matting (U^2-Net)...")
    # استفاده از نسخه بهینه‌شده (u2netp) برای سرعت بالا در پردازش ویدیو
    session = new_session("u2netp") 
    
    cap = cv2.VideoCapture(str(input_video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # استفاده از فرمت رنگی استاندارد برای جلوگیری از خطاهای کانال در مک‌بوک
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(output_matte_path), fourcc, fps, (w, h), isColor=True)

    frame_count = 0
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
        
        # ELITE MATTING: استخراج مستقیم ماسک (Mask) از تصویر با دقت بالا
        mask = remove(frame, session=session, only_mask=True)
        
        # CINEMATIC FEATHERING: محو کردن لبه‌ها برای جلوگیری از دندانه‌دار شدن و ترکیب طبیعی
        mask = cv2.GaussianBlur(mask, (11, 11), 0)
        
        # تبدیل ماسک خاکستری به ۳ کانال رنگی برای تطابق با انکودر FFmpeg
        mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        
        out.write(mask_bgr)
        frame_count += 1
        
        if frame_count % 50 == 0:
            logger.info(f"Rotoscoped {frame_count} frames... (Applying U^2-Net Magic)")

    cap.release()
    out.release()
    logger.info(f"Successfully generated Studio Alpha Matte ({frame_count} frames) at {output_matte_path}")
    
    return output_matte_path

if __name__ == "__main__":
    generate_alpha_matte(Path("test_video.mp4"))