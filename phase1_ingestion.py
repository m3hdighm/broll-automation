import os
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from groq import Groq, APIError, APIConnectionError

# ==========================================
# CONFIGURATION & LOGGING
# ==========================================

class Settings(BaseSettings):
    """Environment variables configuration using pydantic-settings."""
    groq_api_key: str = Field(default="mock_key_for_local_testing")
    log_level: str = Field(default="INFO")
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Phase1_AudioIngestion")

# ==========================================
# DATA CONTRACTS
# ==========================================

class WordTimestamp(BaseModel):
    """Phase 1 Output Schema for word-level timestamps."""
    word: str
    start: float
    end: float

# ==========================================
# MOCK SERVICES
# ==========================================

class MockGroqTranscriptionResponse:
    """Mocks the Groq SDK response object for verbose_json."""
    def __init__(self, words: List[Dict[str, Any]]):
        self.words = words
        self.text = " ".join([w["word"] for w in words])

def mock_groq_transcription() -> MockGroqTranscriptionResponse:
    """
    Returns deterministic dummy JSON data for local execution 
    without consuming API limits.
    """
    logger.info("Using MOCK Groq API for transcription.")
    dummy_words = [
        {"word": "Welcome", "start": 0.0, "end": 0.5},
        {"word": "to", "start": 0.5, "end": 0.7},
        {"word": "the", "start": 0.7, "end": 0.8},
        {"word": "B-Roll", "start": 0.8, "end": 1.2},
        {"word": "Automation", "start": 1.2, "end": 1.8},
        {"word": "Pipeline.", "start": 1.8, "end": 2.5},
    ]
    return MockGroqTranscriptionResponse(words=dummy_words)

# ==========================================
# CORE FUNCTIONS
# ==========================================

def extract_audio_with_ffmpeg(video_path: Path, output_dir: Path) -> Path:
    """
    Extracts audio from a video file and converts it to a 16kHz mono WAV file.
    Idempotent: Skips extraction if the valid WAV file already exists.
    
    Args:
        video_path (Path): Path to the input video file.
        output_dir (Path): Directory to save the output WAV file.
        
    Returns:
        Path: Path to the extracted WAV file.
    """
    if not video_path.exists():
        logger.error(f"Video file not found: {video_path}")
        raise FileNotFoundError(f"Video file not found: {video_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / f"{video_path.stem}.wav"

    # Idempotency check
    if wav_path.exists() and wav_path.stat().st_size > 0:
        logger.info(f"Idempotency hit: Audio already extracted at {wav_path}")
        return wav_path

    # FFmpeg command: -vn (no video), -ac 1 (mono), -ar 16000 (16kHz sample rate)
    command = [
        "ffmpeg",
        "-y",                  # Overwrite output files
        "-i", str(video_path), # Input file
        "-vn",                 # Disable video
        "-ac", "1",            # Audio channels: 1 (Mono)
        "-ar", "16000",        # Audio sample rate: 16000 Hz
        str(wav_path)          # Output file
    ]

    logger.info(f"Starting FFmpeg extraction for {video_path.name}...")
    
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        logger.info(f"Successfully extracted audio to {wav_path}")
        return wav_path
        
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg extraction failed. Stderr: {e.stderr}")
        raise RuntimeError(f"FFmpeg failed to extract audio: {e.stderr}") from e
    except FileNotFoundError as e:
        logger.error("FFmpeg is not installed or not found in PATH.")
        raise RuntimeError("FFmpeg is required but not found.") from e


def transcribe_with_groq(wav_path: Path, use_mock: bool = False) -> List[Dict[str, Any]]:
    """
    Transcribes a WAV file using Groq's Whisper-large-v3 model.
    Forces verbose_json to extract word-level timestamps.
    
    Args:
        wav_path (Path): Path to the WAV file.
        use_mock (bool): If True, uses the mock function instead of the real API.
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries matching the Phase 1 Output Schema.
    """
    if not wav_path.exists():
        logger.error(f"Audio file not found: {wav_path}")
        raise FileNotFoundError(f"Audio file not found: {wav_path}")

    # Check file size (Groq limit is typically 25MB)
    file_size_mb = wav_path.stat().st_size / (1024 * 1024)
    if file_size_mb > 25.0:
        logger.warning(f"Audio file size ({file_size_mb:.2f}MB) exceeds standard 25MB API limits.")

    logger.info(f"Starting transcription for {wav_path.name} (Mock: {use_mock})...")

    try:
        if use_mock:
            transcription = mock_groq_transcription()
        else:
            client = Groq(api_key=settings.groq_api_key, timeout=300.0)
            with open(wav_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    file=(wav_path.name, audio_file.read()),
                    model="whisper-large-v3",
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
        
        # Extract words from the verbose_json response
        # The Groq SDK returns an object where words can be accessed via attribute
        raw_words = getattr(transcription, 'words', [])
        
        if not raw_words:
            logger.warning("No word-level timestamps found in the response.")
            return []

        # Map and validate against the Data Contract
        validated_words: List[Dict[str, Any]] = []
        for w in raw_words:
            # Handle both dict (mock) and object (SDK) access
            word_text = w.get("word") if isinstance(w, dict) else getattr(w, "word", "")
            start_time = w.get("start") if isinstance(w, dict) else getattr(w, "start", 0.0)
            end_time = w.get("end") if isinstance(w, dict) else getattr(w, "end", 0.0)
            
            try:
                valid_word = WordTimestamp(
                    word=word_text.strip(),
                    start=start_time,
                    end=end_time
                )
                validated_words.append(valid_word.model_dump())
            except ValidationError as ve:
                logger.warning(f"Skipping invalid word data {w}: {ve}")

        logger.info(f"Successfully transcribed {len(validated_words)} words.")
        return validated_words

    except APIConnectionError as e:
        logger.error("Failed to connect to Groq API.")
        raise RuntimeError("Groq API connection error.") from e
    except APIError as e:
        logger.error(f"Groq API returned an error: {e}")
        raise RuntimeError(f"Groq API error: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error during transcription: {e}")
        raise

# ==========================================
# EXECUTION ENTRY POINT (For Testing)
# ==========================================

if __name__ == "__main__":
    # Example usage
    BASE_DIR = Path(__file__).parent
    SAMPLE_VIDEO = BASE_DIR / "sample_input.mp4"
    OUTPUT_DIR = BASE_DIR / "temp_audio"
    
    # Create a dummy video file for local testing if it doesn't exist
    if not SAMPLE_VIDEO.exists():
        logger.info("Creating a dummy video file for testing...")
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "testsrc=duration=3:size=1280x720:rate=30", 
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=3", 
            "-c:v", "libx264", "-c:a", "aac", str(SAMPLE_VIDEO)
        ], capture_output=True)

    try:
        # Step 1: Extract Audio
        extracted_wav = extract_audio_with_ffmpeg(
            video_path=SAMPLE_VIDEO, 
            output_dir=OUTPUT_DIR
        )
        
        # Step 2: Transcribe (Using Mock to save API limits)
        transcription_data = transcribe_with_groq(
            wav_path=extracted_wav, 
            use_mock=True
        )
        
        # Output Phase 1 Schema
        print("\n--- Phase 1 Output Schema ---")
        print(json.dumps(transcription_data, indent=2))
        print("-----------------------------\n")
        
    except Exception as err:
        logger.critical(f"Pipeline Phase 1 failed: {err}")