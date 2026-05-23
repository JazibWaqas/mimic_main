import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Add current folder to path
sys.path.append(str(Path(__file__).parent))

# Load environment
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

from utils.api_key_manager import get_key_manager, get_api_key
import google.generativeai as genai
import httpx
from openai import OpenAI

def test_gemini_model(model_name: str):
    print(f"\n--- Testing Gemini Model: {model_name} ---")
    key_manager = get_key_manager()
    key = key_manager.get_current_key()
    if not key:
        print("ERROR: No Gemini API Key available!")
        return False
    
    print(f"Using API Key ending in ...{key[-6:]}")
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={"temperature": 0.1, "max_output_tokens": 100}
        )
        print(f"Initialized model. Sending simple text prompt...")
        response = model.generate_content("Say 'Hello Mimic' in exactly 3 words.")
        print(f"Response Status: OK")
        print(f"Response Text: {response.text.strip()}")
        return True
    except Exception as e:
        print(f"FAILED to call {model_name}: {e}")
        return False

def test_deepseek_model(model_name: str):
    print(f"\n--- Testing DeepSeek Model: {model_name} ---")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not found in environment!")
        return False
    
    print(f"Using DeepSeek API Key ending in ...{api_key[-6:]}")
    # Let's try standard DeepSeek Chat/Reasoner API
    endpoint = "https://api.deepseek.com/v1"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": "Say 'DeepSeek Online' in exactly 3 words."}
        ],
        "max_tokens": 100,
        "temperature": 0.7
    }
    
    try:
        print(f"Calling endpoint {endpoint}/chat/completions with model {model_name}...")
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{endpoint}/chat/completions",
                headers=headers,
                json=payload
            )
            if response.status_code == 200:
                result = response.json()
                print("Response Status: OK")
                print("Response Text:", result["choices"][0]["message"]["content"].strip())
                return True
            else:
                print(f"FAILED: Status {response.status_code}, Response: {response.text}")
                return False
    except Exception as e:
        print(f"FAILED to call {model_name} via DeepSeek direct HTTP: {e}")
        return False

def test_groq_model(model_name: str):
    print(f"\n--- Testing Groq Model: {model_name} ---")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("ERROR: GROQ_API_KEY not found in environment!")
        return False
    
    print(f"Using Groq API Key ending in ...{api_key[-6:]}")
    try:
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key
        )
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": "Say 'Groq Online' in exactly 3 words."}
            ],
            max_tokens=100
        )
        print("Response Status: OK")
        print("Response Text:", response.choices[0].message.content.strip())
        return True
    except Exception as e:
        print(f"FAILED to call {model_name} via Groq: {e}")
        return False

if __name__ == "__main__":
    print("MIMIC Model Hit Tester Starting...")
    
    # 1. Gemini Models
    gemini_models = ["gemini-3.5-flash", "gemini-3-flash-preview", "gemini-1.5-flash"]
    for m in gemini_models:
        test_gemini_model(m)
        time.sleep(1)
        
    # 2. DeepSeek Models (We want to check deepseek-v4 / deepseek-chat)
    deepseek_models = ["deepseek-chat", "deepseek-reasoner"]
    for m in deepseek_models:
        test_deepseek_model(m)
        time.sleep(1)
        
    # 3. Groq/Llama Models
    groq_models = ["llama-3.3-70b-specdec"] # standard / specs
    for m in groq_models:
        test_groq_model(m)
        time.sleep(1)
