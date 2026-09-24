import os
import time
import logging
import requests
from pathlib import Path
from functools import wraps
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, field_validator

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ==========================================
# SCHEMAS
# ==========================================

class Phase2Item(BaseModel):
    """Schema for the input data coming from Phase 2."""
    start_time: str
    end_time: str
    visual_prompt: str
    source: str

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        if len(v.split(":")) != 3:
            raise ValueError("Time must be in HH:MM:SS format")
        return v

class AssetManifestSchema(BaseModel):
    """Schema for the output data of Phase 3."""
    manifest: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="Mapping of start_time to the downloaded local file path (or None if not found/applicable)."
    )

# ==========================================
# UTILITIES & DECORATORS
# ==========================================

def exponential_backoff(max_retries: int = 3, base_delay: float = 1.0):
    """
    Decorator to retry a function with exponential backoff if a RequestException occurs.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.RequestException as e:
                    retries += 1
                    if retries >= max_retries:
                        logger.error(f"Max retries ({max_retries}) reached for {func.__name__}. Failing.")
                        raise e
                    delay = base_delay * (2 ** (retries - 1))
                    logger.warning(f"Network error in {func.__name__}: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
        return wrapper
    return decorator

# ==========================================
# PEXELS API INTEGRATION
# ==========================================

class PexelsClient:
    """Client to interact with the Pexels API for fetching stock videos."""
    
    BASE_URL = "https://api.pexels.com/videos/search"

    def __init__(self, api_key: str):
        self.headers = {"Authorization": api_key}

    @exponential_backoff(max_retries=3, base_delay=2.0)
    def search_best_video_url(self, query: str, max_height: int = 1080) -> Optional[str]:
        """
        Searches Pexels for a video matching the query and returns the URL 
        of the highest quality file that does not exceed max_height.
        """
        params = {"query": query, "per_page": 3, "orientation": "landscape"}
        response = requests.get(self.BASE_URL, headers=self.headers, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        videos = data.get("videos", [])
        
        if not videos:
            return None

        # Get the first (most relevant) video's files
        video_files = videos[0].get("video_files", [])
        
        # Filter files by max_height and sort descending to get the best allowed quality
        valid_files = [f for f in video_files if f.get("height") and f.get("height") <= max_height]
        valid_files.sort(key=lambda x: x.get("height", 0), reverse=True)

        if not valid_files:
            return None
            
        return valid_files[0].get("link")

    @exponential_backoff(max_retries=3, base_delay=2.0)
    def download_video(self, url: str, dest_path: Path) -> bool:
        """Downloads a video from a URL to the specified destination path."""
        response = requests.get(url, stream=True, timeout=15)
        response.raise_for_status()
        
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True

# ==========================================
# CORE PIPELINE FUNCTIONS
# ==========================================

def fetch_stock_video(prompts: List[Dict[str, Any]], api_key: str) -> AssetManifestSchema:
    """
    Phase 3 Pipeline: Iterates through prompts, fetches stock videos from Pexels,
    downloads them, and returns an AssetManifestSchema.
    """
    manifest_data: Dict[str, Optional[str]] = {}
    download_dir = Path.cwd() / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    
    client = PexelsClient(api_key=api_key)

    for item_dict in prompts:
        try:
            item = Phase2Item(**item_dict)
        except Exception as e:
            logger.error(f"Invalid input item: {item_dict}. Error: {e}")
            continue

        if item.source != "stock":
            logger.info(f"Skipping non-stock item at {item.start_time} (Source: {item.source})")
            manifest_data[item.start_time] = None
            continue

        safe_time = item.start_time.replace(":", "_")
        filename = f"{safe_time}.mp4"
        dest_path = download_dir / filename

        logger.info(f"Searching Pexels for: '{item.visual_prompt}'")
        try:
            video_url = client.search_best_video_url(query=item.visual_prompt, max_height=1080)
            
            if not video_url:
                logger.warning(f"No suitable video found for prompt: '{item.visual_prompt}'")
                manifest_data[item.start_time] = None
                continue

            logger.info(f"Downloading video to {dest_path}...")
            client.download_video(url=video_url, dest_path=dest_path)
            manifest_data[item.start_time] = str(dest_path.resolve())
            logger.info(f"Successfully procured asset for {item.start_time}")

        except Exception as e:
            logger.error(f"Failed to procure asset for {item.start_time}: {e}")
            manifest_data[item.start_time] = None

    return AssetManifestSchema(manifest=manifest_data)


def mock_fetch_stock_video(prompts: List[Dict[str, Any]]) -> AssetManifestSchema:
    """
    Mock Function for Testing: Simulates the Pexels API search and download 
    by creating dummy .mp4 files using Path.touch() without network requests.
    """
    manifest_data: Dict[str, Optional[str]] = {}
    download_dir = Path.cwd() / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Running MOCK Asset Procurement Pipeline...")

    for item_dict in prompts:
        item = Phase2Item(**item_dict)
        
        if item.source != "stock":
            manifest_data[item.start_time] = None
            continue

        safe_time = item.start_time.replace(":", "_")
        filename = f"{safe_time}.mp4"
        dest_path = download_dir / filename

        logger.info(f"[MOCK] Searching and downloading for prompt: '{item.visual_prompt}'")
        
        # Simulate network delay
        time.sleep(0.5) 
        
        # Create dummy file
        dest_path.touch(exist_ok=True)
        
        manifest_data[item.start_time] = str(dest_path.resolve())
        logger.info(f"[MOCK] Created dummy asset at {dest_path}")

    return AssetManifestSchema(manifest=manifest_data)

# ==========================================
# EXECUTION BLOCK
# ==========================================

if __name__ == "__main__":
    # Dummy Data from Phase 2 Output
    phase2_mock_output = [
        {
            "start_time": "00:00:00",
            "end_time": "00:00:05",
            "visual_prompt": "A futuristic city skyline at sunset",
            "source": "generation"
        },
        {
            "start_time": "00:00:05",
            "end_time": "00:00:12",
            "visual_prompt": "Close up of a person typing on a mechanical keyboard",
            "source": "stock"
        },
        {
            "start_time": "00:00:12",
            "end_time": "00:00:20",
            "visual_prompt": "Server racks in a dark data center with blinking blue lights",
            "source": "stock"
        }
    ]

    logger.info("Starting Phase 3: Asset Procurement Pipeline (Mock Mode)")
    
    # Execute the mock pipeline
    manifest = mock_fetch_stock_video(prompts=phase2_mock_output)
    
    logger.info("Pipeline Execution Complete. Output Manifest:")
    print(manifest.model_dump_json(indent=2))