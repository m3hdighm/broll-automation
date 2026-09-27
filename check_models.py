# File: check_models.py
import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def print_header(title: str):
    print(f"\n{'='*50}")
    print(f"🚀 {title}")
    print(f"{'='*50}")

def check_groq():
    print_header("GROQ API MODELS")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "your_groq_key_here":
        print("❌ GROQ_API_KEY is missing or invalid in .env")
        return

    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
        response.raise_for_status()
        models = response.json().get("data", [])
        print(f"✅ Found {len(models)} models:")
        for m in sorted([m["id"] for m in models]):
            print(f"   - {m}")
    except Exception as e:
        print(f"❌ Failed to fetch Groq models: {e}")

def check_gemini():
    print_header("GOOGLE GEMINI MODELS")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_key_here":
        print("❌ GEMINI_API_KEY is missing or invalid in .env")
        return

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        # Filter models that support text generation
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        print(f"✅ Found {len(models)} text-generation models:")
        for m in sorted(models):
            print(f"   - {m.replace('models/', '')}")
    except Exception as e:
        print(f"❌ Failed to fetch Gemini models: {e}")

def check_sambanova():
    print_header("SAMBANOVA CLOUD MODELS")
    api_key = os.getenv("SAMBANOVA_API_KEY")
    if not api_key or api_key == "your_sambanova_key_here":
        print("❌ SAMBANOVA_API_KEY is missing or invalid in .env")
        return

    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get("https://api.sambanova.ai/v1/models", headers=headers, timeout=10)
        response.raise_for_status()
        models = response.json().get("data", [])
        print(f"✅ Found {len(models)} models:")
        for m in sorted([m["id"] for m in models]):
            print(f"   - {m}")
    except Exception as e:
        print(f"❌ Failed to fetch SambaNova models: {e}")

def check_openrouter():
    print_header("OPENROUTER MODELS (Top 20 Free/Llama)")
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or api_key == "your_openrouter_key_here":
        print("❌ OPENROUTER_API_KEY is missing or invalid in .env")
        return

    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=15)
        response.raise_for_status()
        models = response.json().get("data", [])
        
        # OpenRouter has hundreds of models. Let's filter to show the most relevant ones for our pipeline.
        relevant_models = [m["id"] for m in models if "free" in m["id"].lower() or "llama-3" in m["id"].lower()]
        
        print(f"✅ Found {len(models)} total models. Showing {len(relevant_models)} relevant (Free/Llama) models:")
        for m in sorted(relevant_models)[:30]: # Limit to 30 to avoid terminal spam
            print(f"   - {m}")
        if len(relevant_models) > 30:
            print("   - ... (and more)")
    except Exception as e:
        print(f"❌ Failed to fetch OpenRouter models: {e}")

if __name__ == "__main__":
    print("\n🔍 INITIATING ELITE MODEL DISCOVERY ENGINE...")
    check_groq()
    check_gemini()
    check_sambanova()
    check_openrouter()
    print("\n" + "="*50)
    print("🏁 DISCOVERY COMPLETE")
    print("="*50 + "\n")