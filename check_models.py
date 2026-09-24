import os
from groq import Groq
from dotenv import load_dotenv

# Load the API key from .env
load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

try:
    print("Fetching active models from Groq...")
    models = client.models.list()
    
    print("\n--- ACTIVE GROQ MODELS ---")
    # Sort models by ID for readability
    active_models = sorted([model.id for model in models.data])
    for m in active_models:
        print(f"- {m}")
        
except Exception as e:
    print(f"Error fetching models: {e}")