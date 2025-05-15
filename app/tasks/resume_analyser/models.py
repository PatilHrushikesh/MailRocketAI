import os
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
# gemma2-9b-it : missed resume
models_list = [
    {"provider": "google", "name": "gemini-2.0-flash-thinking-exp-01-21"},
    {"provider": "groq", "name": "mistral-saba-24b"},
    {"provider": "google", "name": "gemini-2.0-flash"},
    {"provider": "groq", "name": "deepseek-r1-distill-llama-70b"},
    {"provider": "groq", "name": "gemma2-9b-it"},
    {"provider": "google", "name": "gemini-2.5-pro-exp-03-25"},
    {"provider": "groq", "name": "llama-3.1-8b-instant"},
     {"provider": "google", "name": "gemini-2.0-flash-lite"},
    {"provider": "groq", "name": "llama-3.3-70b-specdec"},
    {"provider": "google", "name": "gemini-1.5-pro"},
    {"provider": "groq", "name": "llama-3.3-70b-versatile"},
    {"provider": "groq", "name": "llama3-8b-8192"},
]
    # {"provider": "groq", "name": "llama3-70b-8192"}, -> dont geneate correct json(says "Here's json ouput")

def get_llm(model_info):
    """Create LLM instance based on model provider"""
    provider = model_info["provider"]
    model_name = model_info["name"]
    
    if provider == "groq":
        return ChatGroq(
            model=model_name,
            temperature=0.4,
            max_tokens=None,
            timeout=None,
            max_retries=2
        )
    elif provider == "google":
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.7
        )
    raise ValueError(f"Unsupported provider: {provider}")
