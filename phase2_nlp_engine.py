import json
import logging
import math
from typing import List, Dict, Any, Literal, Optional
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("Phase2_SemanticNLPEngine")

# ==========================================
# Configuration & Settings
# ==========================================
class Settings(BaseSettings):
    groq_api_key: str = "dummy_key_for_local_testing"
    model_name: str = "llama3-70b-8192"
    use_mock_api: bool = True
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
logger.setLevel(settings.log_level.upper())

# Try importing Groq, handle gracefully if not installed for mock testing
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    logger.warning("Groq library not found. Mock API must be used.")

# ==========================================
# Pydantic Schemas
# ==========================================
class WordTimestamp(BaseModel):
    """Schema for Phase 1 Input Data"""
    word: str
    start: float
    end: float

class BRollTimelineSchema(BaseModel):
    """Schema for individual B-Roll insertion points"""
    start_time: str = Field(..., description="Start time in HH:MM:SS format")
    end_time: str = Field(..., description="End time in HH:MM:SS format")
    visual_prompt: str = Field(..., description="Detailed visual description for the B-Roll")
    source: Literal["stock", "generation"] = Field(..., description="Source of the B-Roll")

class LLMResponseSchema(BaseModel):
    """Wrapper schema to enforce valid JSON object return from LLM"""
    timeline: List[BRollTimelineSchema]

# ==========================================
# Helper Functions
# ==========================================
def seconds_to_hhmmss(seconds: float) -> str:
    """Converts float seconds to HH:MM:SS string format."""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(math.floor(seconds % 60))
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def prepare_transcript_for_llm(words: List[WordTimestamp]) -> str:
    """
    Groups words into chunks with start/end timestamps to give the LLM 
    temporal context without overwhelming it with per-word timestamps.
    """
    if not words:
        return ""
    
    # Simple chunking: group every 10 words to provide temporal anchors
    chunk_size = 10
    transcript_blocks = []
    
    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        chunk_text = " ".join([w.word for w in chunk])
        start_ts = seconds_to_hhmmss(chunk[0].start)
        end_ts = seconds_to_hhmmss(chunk[-1].end)
        transcript_blocks.append(f"[{start_ts} - {end_ts}] {chunk_text}")
        
    return "\n".join(transcript_blocks)

# ==========================================
# Mock API Function
# ==========================================
def mock_groq_api(prompt: str) -> str:
    """
    Mock function simulating the Groq API response.
    Returns deterministic dummy JSON data matching LLMResponseSchema.
    """
    logger.info("Using Mock Groq API for text generation.")
    dummy_response = {
        "timeline": [
            {
                "start_time": "00:00:00",
                "end_time": "00:00:03",
                "visual_prompt": "Cinematic wide shot of a bustling futuristic city at sunset, neon lights turning on.",
                "source": "generation"
            },
            {
                "start_time": "00:00:05",
                "end_time": "00:00:08",
                "visual_prompt": "Close up of a person typing rapidly on a glowing holographic keyboard.",
                "source": "stock"
            }
        ]
    }
    return json.dumps(dummy_response)

# ==========================================
# Core Logic
# ==========================================
def analyze_transcript(transcript_data: List[Dict[str, Any]]) -> List[BRollTimelineSchema]:
    """
    Analyzes timestamped transcript data, detects narrative peaks, 
    and determines B-Roll insertion points using an LLM.
    """
    logger.info(f"Starting transcript analysis for {len(transcript_data)} words.")
    
    try:
        # 1. Validate Input Data
        validated_words = [WordTimestamp(**item) for item in transcript_data]
        
        # 2. Format for LLM
        formatted_transcript = prepare_transcript_for_llm(validated_words)
        logger.debug(f"Formatted Transcript:\n{formatted_transcript}")
        
        # 3. Construct Prompts
        system_prompt = (
            "You are an expert AI Video Editor and Narrative Strategist. "
            "Your task is to analyze the provided timestamped transcript and design a B-Roll timeline. "
            "1. Group the text into logical sentences and identify visual narrative peaks. "
            "2. Decide exactly when to insert B-Roll to create a 'Pattern Interrupt' (typically every 3-5 seconds of dialogue) to maximize viewer retention. "
            "3. For each B-Roll segment, provide a highly descriptive 'visual_prompt' and decide if the 'source' should be 'stock' or 'generation'. "
            "4. You MUST output a valid JSON object containing a single key 'timeline' which holds an array of objects. "
            "Each object must have: 'start_time' (HH:MM:SS), 'end_time' (HH:MM:SS), 'visual_prompt' (string), and 'source' ('stock' or 'generation'). "
            "Do not include any markdown formatting, preamble, or conversational text. Output ONLY raw JSON."
        )
        
        user_prompt = f"Transcript Data:\n{formatted_transcript}"

        # 4. Call LLM (Mock or Real)
        llm_response_text = ""
        if settings.use_mock_api or not GROQ_AVAILABLE:
            llm_response_text = mock_groq_api(user_prompt)
        else:
            logger.info(f"Calling Groq API using model: {settings.model_name}")
            client = Groq(api_key=settings.groq_api_key)
            response = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model=settings.model_name,
                temperature=0.2, # Low temperature for deterministic, structured output
                response_format={"type": "json_object"}
            )
            llm_response_text = response.choices[0].message.content

        # 5. Parse and Validate Output
        logger.debug(f"Raw LLM Response: {llm_response_text}")
        parsed_json = json.loads(llm_response_text)
        
        # Validate against Pydantic Schema
        validated_response = LLMResponseSchema(**parsed_json)
        
        logger.info(f"Successfully generated {len(validated_response.timeline)} B-Roll insertion points.")
        return validated_response.timeline

    except ValidationError as ve:
        logger.error(f"Data Validation Error: {ve}")
        raise
    except json.JSONDecodeError as je:
        logger.error(f"Failed to parse JSON from LLM response: {je}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during transcript analysis: {str(e)}", exc_info=True)
        raise

# ==========================================
# Execution Block
# ==========================================
if __name__ == "__main__":
    # Dummy Output from Phase 1
    phase_1_dummy_output = [
        {"word": "Welcome", "start": 0.0, "end": 0.5},
        {"word": "to", "start": 0.5, "end": 0.7},
        {"word": "the", "start": 0.7, "end": 0.9},
        {"word": "future", "start": 0.9, "end": 1.5},
        {"word": "of", "start": 1.5, "end": 1.7},
        {"word": "artificial", "start": 1.7, "end": 2.2},
        {"word": "intelligence.", "start": 2.2, "end": 3.0},
        {"word": "Today,", "start": 3.5, "end": 4.0},
        {"word": "we", "start": 4.0, "end": 4.2},
        {"word": "are", "start": 4.2, "end": 4.4},
        {"word": "building", "start": 4.4, "end": 4.9},
        {"word": "autonomous", "start": 4.9, "end": 5.5},
        {"word": "systems", "start": 5.5, "end": 6.0},
        {"word": "that", "start": 6.0, "end": 6.2},
        {"word": "think", "start": 6.2, "end": 6.7},
        {"word": "faster", "start": 6.7, "end": 7.2},
        {"word": "than", "start": 7.2, "end": 7.5},
        {"word": "humans.", "start": 7.5, "end": 8.2}
    ]

    try:
        logger.info("--- Starting Phase 2: Semantic NLP Engine ---")
        
        # Execute the core function
        b_roll_timeline = analyze_transcript(phase_1_dummy_output)
        
        # Output the result
        logger.info("--- Phase 2 Output ---")
        print(json.dumps([item.model_dump() for item in b_roll_timeline], indent=2))
        
    except Exception as e:
        logger.critical(f"Phase 2 execution failed: {e}")