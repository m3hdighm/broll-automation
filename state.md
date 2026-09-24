# System State
Completed: Phase 1 (`phase1_ingestion.py`)

# Output Contract for Next Phase (Phase 1 Output):
[
  {
    "word": "string",
    "start": float,
    "end": float
  }
]
Completed: Phase 2 (`phase2_nlp_engine.py`)

# Output Contract for Next Phase (Phase 2 Output):
[
  {
    "start_time": "HH:MM:SS",
    "end_time": "HH:MM:SS",
    "visual_prompt": "string",
    "source": "stock" | "generation"
  }
]
Completed: Phase 3 (`phase3_asset_procurement.py`)

# Output Contract for Next Phase (Phase 3 Output):
{
  "manifest": {
    "HH:MM:SS": "absolute/path/to/downloaded/file.mp4"
  }
}