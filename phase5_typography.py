# File: phase5_typography.py
import os
import re
import math
import logging
import subprocess
import difflib
import warnings
from pathlib import Path
from fractions import Fraction
from groq import Groq
from dotenv import load_dotenv
import pysubs2

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Phase5_Typography")

# SOTA Fix: Aggressive suppression of Google SDK internal warnings
logging.getLogger("google.genai").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*automatic function calling.*")
warnings.filterwarnings("ignore", message=".*AFC.*")
warnings.filterwarnings("ignore", category=UserWarning, module="google.*")

# ==========================================
# ELITE LLM ROUTER (Multi-Provider Fallback)
# ==========================================

class EliteLLMRouter:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")

    def correct_text(self, text: str, prompt: str) -> str:
        if self.gemini_key and self.gemini_key != "your_gemini_key_here":
            try:
                from google import genai
                logger.info("Attempting LLM Correction with [Gemini 3.8 Flash]...")
                client = genai.Client(api_key=self.gemini_key)
                # SOTA Fix: Updated to gemini-3.8-flash
                response = client.models.generate_content(
                    model='gemini-3.8-flash',
                    contents=f"{prompt}\n\nمتن خام:\n{text}"
                )
                logger.info("LLM Correction successful using Gemini.")
                return response.text.strip()
            except Exception as e:
                logger.warning(f"Gemini failed: {e}")

        if self.openrouter_key and self.openrouter_key != "your_openrouter_key_here":
            try:
                from openai import OpenAI
                logger.info("Attempting LLM Correction with [OpenRouter Llama-3.3-70B]...")
                client = OpenAI(api_key=self.openrouter_key, base_url="https://openrouter.ai/api/v1")
                response = client.chat.completions.create(
                    model="meta-llama/llama-3.3-70b-instruct",
                    messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
                    temperature=0.0 
                )
                logger.info("LLM Correction successful using OpenRouter.")
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"OpenRouter failed: {e}")

        raise Exception("CRITICAL: All Enterprise LLM providers failed.")

# ==========================================
# CORE ENGINE FUNCTIONS
# ==========================================

def get_video_info_fps(video_path: Path) -> tuple[int, int]:
    try:
        cmd = ["static_ffprobe", "-v", "error", "-select_streams", "v:0", 
               "-show_entries", "stream=r_frame_rate", "-of", "default=noprint_wrappers=1:nokey=1", 
               str(video_path)]
        out = subprocess.check_output(cmd, text=True).strip()
        num, den = map(int, out.split('/'))
        return num, den
    except Exception:
        return 30000, 1001

def quantize_timestamps(cues: list, fps_num: int, fps_den: int = 1) -> list:
    fps = Fraction(fps_num, fps_den)
    for cue in cues:
        start_sec = Fraction(str(cue['start']))
        end_sec = Fraction(str(cue['end']))
        cue['start'] = float(math.floor(start_sec * fps + Fraction(1, 2)) / fps)
        cue['end'] = float(math.floor(end_sec * fps + Fraction(1, 2)) / fps)
    return cues

def elite_persian_normalizer(text: str) -> str:
    if not text:
        return text
        
    corrections = {
        r'\bعلکی\b': 'الکی',
        r'\bراهل\b': 'راه‌حل',
        r'\bکچیک\b': 'کوچک',
        r'\bدقدقه\b': 'دغدغه',
        r'\bخانوم\b': 'خانم',
        r'\bخاهش\b': 'خواهش',
        r'\bواسه\b': 'برای',
        r'\bموزعی\b': 'موضعی',
        r'\bهیپتیپ\b': 'هیپ‌دیپ',
        r'\bهیپ\sتیپ\b': 'هیپ‌دیپ',
        r'\bسرویز\b': 'سرویس',
        r'\bفازله\b': 'فاصله',
        r'\bآنتومی\b': 'آناتومی',
        r'\bجنازی\b': 'شناسی'
    }
    for wrong, right in corrections.items():
        text = re.sub(wrong, right, text)
        
    text = re.sub(r'\b(می|نمی)\s+', r'\1' + '\u200c', text)
    text = re.sub(r'\s+(ها|های|تر|ترین)\b', '\u200c' + r'\1', text)
    text = re.sub(r'([،.؟!])', r'\1' + '\u200f', text)
    return text

def correct_transcript_with_router(raw_words: list) -> list:
    original_text = " ".join([w['word'] for w in raw_words])
    prompt = (
        "تو یک ویراستار ارشد زبان فارسی هستی. متن زیر خروجی خام یک هوش مصنوعی است. "
        "وظیفه تو اصلاح اشتباهات املایی و تخصصی است.\n"
        "قوانین حیاتی:\n"
        "۱. به هیچ وجه کلمه‌ای را حذف یا اضافه نکن.\n"
        "۲. تعداد کلمات خروجی باید دقیقاً برابر با متن اصلی باشد.\n"
        "۳. فقط کلمات اصلاح شده را با فاصله برگردان."
    )
    
    router = EliteLLMRouter()
    try:
        corrected_text = router.correct_text(original_text, prompt)
        corrected_words = corrected_text.split()
        
        if len(corrected_words) == len(raw_words):
            for i in range(len(raw_words)):
                raw_words[i]['word'] = corrected_words[i]
        else:
            matcher = difflib.SequenceMatcher(None, [w['word'] for w in raw_words], corrected_words)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag in ('equal', 'replace'):
                    for idx in range(i2 - i1):
                        if j1 + idx < len(corrected_words):
                            raw_words[i1 + idx]['word'] = corrected_words[j1 + idx]
    except Exception as e:
        logger.error(f"LLM Router failed: {e}")
        
    return raw_words

def build_rtl_karaoke_line_native(chunk_words: list, active_logical_idx: int) -> str:
    r"""
    SOTA Fixes Applied:
    - Bug 1 & 3: Alpha-Masking (\alpha&HFF&) for Cumulative Pop-in without Jitter.
    - Bug 2: ASS Bounce Math (\fscx120\fscy120\t...) for Cinematic Pop.
    - Bug 6: Clean ASS Resets (\c\fscx\fscy and \alpha) instead of hardcoded hex.
    - Bug 8: Safe Zone Calibration (\pos(360,820)\an5).
    """
    RLE = '\u202b' 
    PDF = '\u202c' 
    
    words = []
    for i, w in enumerate(chunk_words):
        if i < active_logical_idx:
            words.append(w['word'])
        elif i == active_logical_idx:
            words.append(f"{{\\c&HFFFF00&\\fscx120\\fscy120\\t(0,100,\\fscx100\\fscy100)}}{w['word']}{{\\c\\fscx\\fscy}}")
        else:
            words.append(f"{{\\alpha&HFF&}}{w['word']}{{\\alpha}}")
            
    logical_payload = " ".join(words)
    return f"{{\\pos(360,820)\\an5}}{RLE}{logical_payload}{PDF}"

# ==========================================
# MAIN TYPOGRAPHY PIPELINE
# ==========================================

def generate_ass_subtitles(audio_path: Path, output_ass_path: Path, lang: str = 'en') -> Path:
    if output_ass_path.exists():
        return output_ass_path

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise ValueError("CRITICAL: GROQ_API_KEY is missing.")
        
    client = Groq(api_key=groq_api_key)
    
    meta_prompt = "سلام. ورزش، فیتنس، مربی، باشگاه، شکم، پهلو، چربی‌سوزی، عضله، هیپ‌دیپ، سلولیت، بانوان، تمرین، رژیم، تغذیه، استوری، پست، دغدغه، خانم‌ها، ورزشکار، کات، موضعی." if lang == 'fa' else ""
    
    logger.info(f"Calling Groq Whisper for {lang.upper()} Transcription...")
    with open(audio_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            file=(audio_path.name, f.read()),
            model="whisper-large-v3",
            language=lang, 
            prompt=meta_prompt,
            temperature=0.0,
            response_format="verbose_json",
            timestamp_granularities=["word"]
        )
    
    video_path = audio_path.with_suffix('.mp4')
    fps_num, fps_den = get_video_info_fps(video_path)
    
    subs = pysubs2.SSAFile()
    subs.info["PlayResX"] = "720"
    subs.info["PlayResY"] = "1280"
    subs.info["WrapStyle"] = "2" 
    
    style = pysubs2.SSAStyle()
    style.fontname = "Vazirmatn" 
    style.bold = -1
    style.fontsize = 65
    style.primarycolor = pysubs2.Color(255, 255, 255)      
    style.secondarycolor = pysubs2.Color(255, 255, 255)  
    style.outlinecolor = pysubs2.Color(0, 0, 0)
    style.backcolor = pysubs2.Color(0, 0, 0, 180)
    style.outline = 6
    style.shadow = 5
    subs.styles["EliteKaraoke"] = style

    raw_words = []
    for w in transcription.words:
        word_text = getattr(w, 'word', w.get('word', '') if isinstance(w, dict) else '')
        start = getattr(w, 'start', w.get('start', 0) if isinstance(w, dict) else 0)
        end = getattr(w, 'end', w.get('end', 0) if isinstance(w, dict) else 0)
        if word_text.strip():
            clean_word = word_text.strip().replace("'", "\u2019").replace(":", "")
            raw_words.append({"word": clean_word, "start": start, "end": end})

    if not raw_words:
        return output_ass_path

    if lang == 'fa':
        raw_words = correct_transcript_with_router(raw_words)
        for w in raw_words:
            w['word'] = elite_persian_normalizer(w['word'])

    raw_words = quantize_timestamps(raw_words, fps_num, fps_den)

    # ==========================================
    # SOTA DYNAMIC CHUNKING (Bug 4: Semantic Cleaving)
    # ==========================================
    chunks = []
    current_chunk = []
    current_length = 0
    
    MAX_CHARS = 22  
    MAX_WORDS = 5   
    MAX_GAP = 0.5
    
    hanging_words = {'و', 'که', 'از', 'به', 'در', 'با', 'تا', 'برای', 'یا', 'هم'}
    punctuation = {'.', '،', '!', '؟'}

    for i, w in enumerate(raw_words):
        clean_w = w['word']
        word_len = len(clean_w) + 1 
        gap = w['start'] - current_chunk[-1]['end'] if current_chunk else 0
        
        last_word_hanging = False
        if current_chunk:
            last_w_clean = re.sub(r'[،.؟!]', '', current_chunk[-1]['word']).replace('\u200c', '').strip()
            if last_w_clean in hanging_words:
                last_word_hanging = True
                
        force_break = False
        if current_chunk and any(p in current_chunk[-1]['word'] for p in punctuation):
            force_break = True
            
        if force_break or (not last_word_hanging and ((current_length + word_len > MAX_CHARS) or (len(current_chunk) >= MAX_WORDS) or (gap > MAX_GAP))):
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = [w]
            current_length = word_len
        else:
            current_chunk.append(w)
            current_length += word_len
            
    if current_chunk:
        chunks.append(current_chunk)

    # ==========================================
    # SOTA: STATIC BLOCK KARAOKE ENGINE
    # ==========================================
    for c_idx, chunk in enumerate(chunks):
        if lang == 'fa':
            chunk_start_ms = int(chunk[0]['start'] * 1000)
            base_end = int(chunk[-1]['end'] * 1000) + 200 
            
            if c_idx < len(chunks) - 1:
                next_chunk_start = int(chunks[c_idx + 1][0]['start'] * 1000)
                chunk_end_ms = min(base_end, next_chunk_start - 50)
            else:
                chunk_end_ms = base_end

            for idx, w in enumerate(chunk):
                ev_start = int(w['start'] * 1000)
                
                if idx < len(chunk) - 1:
                    ev_end = int(chunk[idx + 1]['start'] * 1000)
                else:
                    ev_end = chunk_end_ms
                    
                if ev_start >= ev_end:
                    ev_end = ev_start + 10
                
                text_payload = build_rtl_karaoke_line_native(chunk, idx)
                event = pysubs2.SSAEvent(start=ev_start, end=ev_end, text=text_payload, style="EliteKaraoke")
                subs.append(event)
        else:
            start_ms = int(chunk[0]['start'] * 1000)
            base_end = int(chunk[-1]['end'] * 1000) + 200
            if c_idx < len(chunks) - 1:
                next_chunk_start = int(chunks[c_idx + 1][0]['start'] * 1000)
                end_ms = min(base_end, next_chunk_start - 50)
            else:
                end_ms = base_end
                
            text_payload = "{\\pos(360,820)\\an5}"
            current_time = chunk[0]['start']
            
            for idx, w in enumerate(chunk):
                gap = w['start'] - current_time
                if gap > 0:
                    text_payload += f"{{\\k{int(gap * 100)}}}"
                if idx > 0:
                    text_payload += " "
                dur_cs = int((w['end'] - w['start']) * 100)
                text_payload += f"{{\\k{dur_cs}}}{w['word'].upper()}"
                current_time = w['end']
                
            event = pysubs2.SSAEvent(start=start_ms, end=end_ms, text=text_payload, style="EliteKaraoke")
            subs.append(event)

    subs.save(str(output_ass_path))
    logger.info(f"Elite .ASS Subtitle File ({lang.upper()}) generated via Cinematic Static Block Engine!")
    return output_ass_path