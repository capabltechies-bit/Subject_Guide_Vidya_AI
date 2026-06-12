import os
import json
import requests
import google.generativeai as genai
import streamlit as st

def call_llm(
    system_prompt: str,
    user_message: str,
    model_name: str = "gemini-2.5-flash",
    gemini_key: str = None,
    groq_key: str = None,
    openrouter_key: str = None
) -> str:
    """
    Executes a chat completion query with a multi-provider failover chain:
    1. Try Gemini key(s).
    2. Fall back to Groq (using llama-3.1-70b-versatile) if Gemini is exhausted.
    3. Fall back to OpenRouter (using llama-3-8b-instruct:free) if Groq is exhausted.
    """
    # ══════════════════════════════════════════════════════════════════════════
    #  STAGE 1: GOOGLE GEMINI
    # ══════════════════════════════════════════════════════════════════════════
    raw_gemini_key = gemini_key or os.environ.get("GOOGLE_API_KEY", "")
    gemini_keys = [k.strip() for k in raw_gemini_key.split(",") if k.strip()]
    
    last_gemini_err = None
    if gemini_keys:
        print(f"Attempting Gemini generation (model={model_name}) with {len(gemini_keys)} keys...")
        for key in gemini_keys:
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_prompt,
                )
                return model.generate_content(user_message).text
            except Exception as e:
                err_msg = str(e).lower()
                # Check for rate limit or quota errors
                if any(word in err_msg for word in ["quota", "exhausted", "429", "rate_limit", "resource_exhausted", "limit"]):
                    last_gemini_err = e
                    print(f"Gemini API Key starting with '{key[:8]}' exhausted. Trying next key...")
                    continue
                else:
                    # Reraise other errors immediately (e.g. invalid query syntax)
                    raise e
    else:
        print("No Gemini API keys found.")

    # ══════════════════════════════════════════════════════════════════════════
    #  STAGE 2: GROQ FALLBACK
    # ══════════════════════════════════════════════════════════════════════════
    # Retrieve groq keys from argument, session state, or environment
    raw_groq_key = groq_key
    if not raw_groq_key and "api_settings" in st.session_state and st.session_state.api_settings:
        raw_groq_key = st.session_state.api_settings.get("groq_api_key", "")
    if not raw_groq_key:
        raw_groq_key = os.environ.get("GROQ_API_KEY", "")
        
    groq_keys = [k.strip() for k in raw_groq_key.split(",") if k.strip()]
    last_groq_err = None
    
    if groq_keys:
        print(f"Gemini failed or unconfigured. Attempting Groq fallback with {len(groq_keys)} keys...")
        # LLaMA 3.1 70B is free and smart enough for academic tasks
        groq_model = "llama-3.1-70b-versatile" 
        url = "https://api.groq.com/openai/v1/chat/completions"
        
        for key in groq_keys:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": groq_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0.3
            }
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                elif response.status_code in (429, 403, 503):
                    # Rate limit or quota errors
                    print(f"Groq API Key starting with '{key[:8]}' exhausted (HTTP {response.status_code}). Trying next Groq key...")
                    last_groq_err = Exception(f"Groq error: {response.text}")
                    continue
                else:
                    raise Exception(f"Groq API Error {response.status_code}: {response.text}")
            except Exception as e:
                err_msg = str(e).lower()
                if any(word in err_msg for word in ["timeout", "connection", "429", "rate"]):
                    last_groq_err = e
                    continue
                else:
                    raise e
    else:
        print("No Groq API keys found.")

    # ══════════════════════════════════════════════════════════════════════════
    #  STAGE 3: OPENROUTER FALLBACK
    # ══════════════════════════════════════════════════════════════════════════
    # Retrieve openrouter keys from argument, session state, or environment
    raw_or_key = openrouter_key
    if not raw_or_key and "api_settings" in st.session_state and st.session_state.api_settings:
        raw_or_key = st.session_state.api_settings.get("openrouter_api_key", "")
    if not raw_or_key:
        raw_or_key = os.environ.get("OPENROUTER_API_KEY", "")
        
    or_keys = [k.strip() for k in raw_or_key.split(",") if k.strip()]
    last_or_err = None
    
    if or_keys:
        print(f"Gemini and Groq failed. Attempting OpenRouter fallback with {len(or_keys)} keys...")
        # Using llama-3-8b-instruct:free as it is stable and permanently free
        or_model = "meta-llama/llama-3-8b-instruct:free"
        url = "https://openrouter.ai/api/v1/chat/completions"
        
        for key in or_keys:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://scholar.ai", # Optional OpenRouter branding
                "X-Title": "Scholar AI"
            }
            payload = {
                "model": or_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0.3
            }
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                elif response.status_code in (429, 403, 503):
                    print(f"OpenRouter API Key starting with '{key[:8]}' exhausted (HTTP {response.status_code}). Trying next key...")
                    last_or_err = Exception(f"OpenRouter error: {response.text}")
                    continue
                else:
                    raise Exception(f"OpenRouter API Error {response.status_code}: {response.text}")
            except Exception as e:
                err_msg = str(e).lower()
                if any(word in err_msg for word in ["timeout", "connection", "429", "rate"]):
                    last_or_err = e
                    continue
                else:
                    raise e
    else:
        print("No OpenRouter API keys found.")

    # ══════════════════════════════════════════════════════════════════════════
    #  NO ACTIVE KEYS REMAINING
    # ══════════════════════════════════════════════════════════════════════════
    # Report the details of the errors
    if last_gemini_err or last_groq_err or last_or_err:
        err_msg = "All available API Key pools were exhausted.\n"
        if last_gemini_err:
            err_msg += f"- Gemini Error: {last_gemini_err}\n"
        if last_groq_err:
            err_msg += f"- Groq Error: {last_groq_err}\n"
        if last_or_err:
            err_msg += f"- OpenRouter Error: {last_or_err}\n"
        raise Exception(err_msg)
        
    raise Exception("No active API keys were configured. Please add a Gemini, Groq, or OpenRouter API key in settings.")
