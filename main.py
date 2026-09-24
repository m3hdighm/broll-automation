# main.py
"""
B-Roll Automation Pipeline - Orchestration Engine
Design Pattern: Serverless Microservices, Idempotent Functions
Stack: Python 3.11, pydantic-settings, dotenv
"""

import argparse
import logging
import sys
import tempfile
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Phase Imports (Corrected based on actual function names)
# ---------------------------------------------------------------------------
try:
    from phase1_ingestion import extract_audio_with_ffmpeg, transcribe_with_groq
    from phase2_nlp_engine import analyze_transcript
    from phase3_asset_procurement import fetch_stock_video
    from phase4_final_assembly import assemble_final_video
except ImportError as e:
    print(f"CRITICAL ERROR: Missing phase module. Ensure all phase scripts are in the directory. Details: {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration & Logging
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    """Environment variables configuration."""
    groq_api_key: str
    pexels_api_key: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

try:
    settings = Settings()
except Exception as e:
    print(f"CRITICAL ERROR: Failed to load environment variables. Ensure .env contains GROQ_API_KEY and PEXELS_API_KEY. Details: {e}")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BRollPipeline")

# ---------------------------------------------------------------------------
# Orchestration Engine
# ---------------------------------------------------------------------------
def run_pipeline(input_video_path: Path) -> None:
    """Master orchestration function to execute the B-Roll pipeline."""
    if not input_video_path.exists():
        logger.error(f"Input video not found at path: {input_video_path}")
        sys.exit(1)

    logger.info(f"Starting B-Roll Automation Pipeline for: {input_video_path.name}")

    try:
        # Use TemporaryDirectory to safely handle Phase 1's audio extraction
        with tempfile.TemporaryDirectory(prefix="broll_temp_") as temp_dir:
            temp_audio_dir = Path(temp_dir)
            
            # =========================================================
            # PHASE 1: Ingestion
            # =========================================================
            logger.info("=== PHASE 1: INGESTION ===")
            logger.info("Extracting audio...")
            wav_path = extract_audio_with_ffmpeg(
                video_path=input_video_path, 
                output_dir=temp_audio_dir
            )
            
            logger.info("Transcribing audio...")
            transcript_data = transcribe_with_groq(wav_path=wav_path, use_mock=False)
            
            if not transcript_data:
                raise ValueError("Phase 1 Failed: Transcript data is empty.")

            # =========================================================
            # PHASE 2: NLP Engine
            # =========================================================
            logger.info("=== PHASE 2: NLP ENGINE ===")
            logger.info("Analyzing transcript for B-Roll opportunities...")
            timeline_objects = analyze_transcript(transcript_data=transcript_data)
            
            if not timeline_objects:
                logger.warning("Phase 2 Warning: No B-Roll opportunities found. Pipeline will halt gracefully.")
                return
                
            # Convert Pydantic objects to dicts for Phase 3
            timeline_dicts = [item.model_dump() for item in timeline_objects]

            # =========================================================
            # PHASE 3: Asset Procurement
            # =========================================================
            logger.info("=== PHASE 3: ASSET PROCUREMENT ===")
            logger.info("Fetching stock video assets based on timeline...")
            manifest_obj = fetch_stock_video(
                prompts=timeline_dicts, 
                api_key=settings.pexels_api_key
            )
            
            if not manifest_obj or not manifest_obj.manifest:
                raise ValueError("Phase 3 Failed: Asset manifest is empty or invalid.")

            # Filter out None values (where no video was found) for Phase 4
            valid_manifest = {k: v for k, v in manifest_obj.manifest.items() if v is not None}
            
            if not valid_manifest:
                logger.warning("No valid B-Rolls were downloaded. Skipping Phase 4.")
                return

            # =========================================================
            # PHASE 4: Final Assembly
            # =========================================================
            logger.info("=== PHASE 4: FINAL ASSEMBLY ===")
            output_video_path = input_video_path.with_name(f"{input_video_path.stem}_with_broll.mp4")
            
            assemble_final_video(
                main_video_path=input_video_path,
                manifest=valid_manifest,
                output_path=output_video_path
            )
            
            logger.info("=== PIPELINE COMPLETE ===")
            logger.info(f"Final video successfully generated at: {output_video_path}")

    except Exception as e:
        logger.error(f"Pipeline halted due to an error: {e}", exc_info=True)
        sys.exit(1)

# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="B-Roll Automation Pipeline Orchestrator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "-i", "--input",
        type=Path,
        required=True,
        help="Path to the input video file (e.g., test_video.mp4)"
    )
    
    args = parser.parse_args()
    run_pipeline(args.input)