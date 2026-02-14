# @agent: Hermes
# @role: Secure API key storage, test, and access system
# @linked_panels: B2_ApiKeyManagerPanel, DebugPanel

import os
import json
from cryptography.fernet import Fernet
import requests

KEY_FILE = "secure/api_keys.json"
FERNET_KEY_ENV = "ARCADIA_FERNET_KEY"
FALLBACK_ENV_KEYS = {
    "Claude": ["CLAUDE_API_KEY", "ANTHROPIC_API_KEY"],
    "Anthropic": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
    "OpenAI": ["OPENAI_API_KEY"],
}

if not os.path.exists("secure"):
    os.makedirs("secure")

def _get_cipher():
    """Get Fernet cipher instance from environment variable"""
    key = os.getenv(FERNET_KEY_ENV)
    if not key:
        raise RuntimeError("❌ Missing Fernet encryption key for Hermes.")
    return Fernet(key.encode())

def store_api_key(provider, key_value):
    """Store encrypted API key for given provider"""
    data = load_all_keys()
    cipher = _get_cipher()
    data[provider] = cipher.encrypt(key_value.encode()).decode()
    with open(KEY_FILE, "w") as f:
        json.dump(data, f)

def _fallback_env_key(provider):
    """Check environment variables for a matching key."""
    env_keys = FALLBACK_ENV_KEYS.get(provider, [])
    for env_key in env_keys:
        value = os.getenv(env_key)
        if value:
            return value.strip()
    return None


def load_api_key(provider):
    """Load and decrypt API key for given provider (with environment fallback)."""
    data = load_all_keys()
    encrypted_value = data.get(provider)
    if encrypted_value:
        cipher = _get_cipher()
        try:
            return cipher.decrypt(encrypted_value.encode()).decode()
        except Exception:
            return None
    return _fallback_env_key(provider)

def load_all_keys():
    """Load raw encrypted key data from file"""
    if not os.path.exists(KEY_FILE):
        return {}
    with open(KEY_FILE, "r") as f:
        return json.load(f)

def test_api_key(provider):
    """Test API key validity by calling provider's test endpoint"""
    test_urls = {
        "Claude": "https://api.anthropic.com/v1/models",
        "OpenAI": "https://api.openai.com/v1/models",
        "Anthropic": "https://api.anthropic.com/v1/models"
    }

    key = load_api_key(provider)
    if not key:
        return "Missing"

    try:
        headers = {
            "Authorization": f"Bearer {key}"
        }

        url = test_urls[provider]
        response = requests.get(url, headers=headers, timeout=3)

        if response.status_code == 200:
            return "Valid"
        elif response.status_code == 401:
            return "Invalid"
        elif response.status_code in [403, 429]:
            return "Expired"
        else:
            return "Error"
    except Exception:
        return "Error"

def get_key_status_summary():
    """Get overall status summary for all providers"""
    providers = ["Claude", "OpenAI", "Anthropic"]
    statuses = []

    for provider in providers:
        status = test_api_key(provider)
        statuses.append(status)

    if all(s == "Valid" for s in statuses):
        return "All Valid"
    elif all(s == "Missing" for s in statuses):
        return "Missing"
    else:
        return "Partial"

def clear_all_keys():
    """Clear all stored API keys (for security purposes)"""
    if os.path.exists(KEY_FILE):
        os.remove(KEY_FILE)
    return True
