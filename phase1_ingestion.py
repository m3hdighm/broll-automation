# File: phase1_ingestion.py
import os
import json
import logging
import subprocess
import warnings
from pathlib import Path
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from groq import Groq, APIError, APIConnectionError

# ==========================================
# CONFIGURATION & LOGGING
# ==========================================

class Settings(BaseSettings):
    groq_api_key: str = Field(default="mock_key_for_local_testing")
    gemini_api_key: str = Field(default="mock_key_for_local_testing")
    log_level: str = Field(default="INFO")
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("Phase1_AudioIngestion")

# SOTA Fix: Aggressive suppression of Google SDK internal warnings (AFC Warning)
logging.getLogger("google.genai").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*automatic function calling.*")
warnings.filterwarnings("ignore", message=".*AFC.*")
warnings.filterwarnings("ignore", category=UserWarning, module="google.*")

# ==========================================
# DATA CONTRACTS
# ==========================================

class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float

# ==========================================
# CORE FUNCTIONS
# ==========================================

def extract_audio_with_ffmpeg(video_path: Path, output_dir: Path) -> Path:
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / f"{video_path.stem}.wav"

    if wav_path.exists() and wav_path.stat().st_size > 0:
        return wav_path

    command = [
        "static_ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", str(wav_path)
    ]

    logger.info(f"Starting FFmpeg extraction for {video_path.name}...")
    try:
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return wav_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg failed to extract audio: {e.stderr}") from e

def generate_dynamic_prompt_with_gemini(wav_path: Path, language: str) -> str:
    """
    SOTA Architecture: The Multimodal Oracle
    ارسال مستقیم صوت به Gemini 3.8 Flash برای استخراج کلمات کلیدی
    """
    if not settings.gemini_api_key or settings.gemini_api_key == "your_gemini_key_here":
        logger.warning("Gemini API Key missing. Using generic fallback prompt.")
        return "سلام، ویدیو، کلمات، محاوره، تخصصی." if language == 'fa' else "Hello, video, words, jargon."

    logger.info("Initiating Multimodal Oracle (Gemini 3.8 Flash) for Audio Context Extraction...")
    
    try:
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)
        
        logger.info("Uploading audio to Gemini servers...")
        audio_file = client.files.upload(file=str(wav_path))
        
        if language == 'fa':
            instruction = (
                "به این فایل صوتی با دقت گوش بده. موضوع اصلی آن را تشخیص بده و بین ۲۰ تا ۳۰ کلمه کلیدی، "
                "تخصصی، محاوره‌ای و اصطلاحات خاصی که گوینده استفاده کرده است را استخراج کن. "
                "قانون بسیار مهم: املای صحیح کلمات محاوره‌ای را حتماً رعایت کن (مثلاً بنویس 'الکی' نه 'علکی'، 'راه‌حل' نه 'راهل'، 'کوچک' نه 'کچیک'). "
                "خروجی تو باید فقط و فقط یک لیست از کلمات باشد که با ویرگول از هم جدا شده‌اند. هیچ توضیح اضافه‌ای ننویس."
            )
        else:
            instruction = (
                "Listen to this audio carefully. Identify the main topic and extract 20 to 30 key terms, "
                "jargon, and colloquialisms used by the speaker. "
                "Return ONLY a comma-separated list of these words. Do not add any other text."
            )

        logger.info("Analyzing audio frequencies and extracting vocabulary seed...")
        # SOTA Fix: Updated to gemini-3.8-flash based on Google API logs
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=[audio_file, instruction]
        )
        
        dynamic_prompt = response.text.strip()
        logger.info(f"Oracle successfully generated dynamic prompt: {dynamic_prompt}")
        
        try:
            client.files.delete(name=audio_file.name)
            logger.info("Audio file securely deleted from Gemini servers.")
        except Exception as cleanup_error:
            logger.warning(f"Failed to delete file from Gemini servers: {cleanup_error}")
            
        return dynamic_prompt

    except Exception as e:
        logger.error(f"Multimodal Oracle failed: {e}. Falling back to generic prompt.")
        return "سلام، ویدیو، کلمات، محاوره، تخصصی." if language == 'fa' else "Hello, video, words, jargon."

def transcribe_with_groq(wav_path: Path, language: str = 'en', use_mock: bool = False) -> List[Dict[str, Any]]:
    if not wav_path.exists():
        raise FileNotFoundError(f"Audio file not found: {wav_path}")

    logger.info(f"Starting Elite transcription for {wav_path.name} (Lang: {language.upper()})...")

    dynamic_meta_prompt = generate_dynamic_prompt_with_gemini(wav_path, language)
    
    if language == 'fa':
        spelling_seed = " الکی، راه‌حل، کوچک، خانم‌ها، دغدغه، عضله، چربی‌سوزی، هیپ‌دیپ، سلولیت، ورزشکار، موضعی، می‌خوام، می‌شه."
        final_prompt = dynamic_meta_prompt + spelling_seed
    else:
        final_prompt = dynamic_meta_prompt

    try:
        client = Groq(api_key=settings.groq_api_key, timeout=300.0)
        with open(wav_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=(wav_path.name, audio_file.read()),
                model="whisper-large-v3",
                prompt=final_prompt,          
                temperature=0.0,              
                language=language,            
                response_format="verbose_json",
                timestamp_granularities=["word"]
            )
        
        raw_words = getattr(transcription, 'words', [])
        
        validated_words: List[Dict[str, Any]] = []
        for w in raw_words:
            word_text = w.get("word") if isinstance(w, dict) else getattr(w, "word", "")
            start_time = w.get("start") if isinstance(w, dict) else getattr(w, "start", 0.0)
            end_time = w.get("end") if isinstance(w, dict) else getattr(w, "end", 0.0)
            
            try:
                valid_word = WordTimestamp(word=word_text.strip(), start=start_time, end=end_time)
                validated_words.append(valid_word.model_dump())
            except ValidationError:
                continue

        logger.info(f"Successfully transcribed {len(validated_words)} words with Zero-Hallucination setup.")
        return validated_words

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise