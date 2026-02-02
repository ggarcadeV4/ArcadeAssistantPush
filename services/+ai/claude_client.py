# @agent: ClaudeCloudClient
# @role: Sends secure, permission-checked requests to Claude API (Anthropic)
# @depends_on: Hermes, Janus
# @fallbacks: Local LLM (not included here)

import requests
from services.+api_keys.hermes import load_api_key
from services.+api_keys.janus import enforce_key_check
from services.+logging.agent_log_writer import log_agent_event

CLAUDE_ENDPOINT = "https://api.anthropic.com/v1/messages"

def call_claude(prompt: str, model="claude-3-sonnet-20240229") -> str:
    """
    Make secure API call to Claude with Janus permission check
    """
    check = enforce_key_check("Claude")

    if not check["allowed"]:
        log_agent_event(f"Janus blocked Claude API call: {check['reason']}")
        return "[Local Only Mode] Claude call blocked: " + check["reason"]

    api_key = load_api_key("Claude")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": model,
        "max_tokens": 400,
        "temperature": 0.7,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        response = requests.post(CLAUDE_ENDPOINT, headers=headers, json=payload, timeout=8)
        if response.status_code == 200:
            content = response.json().get("content", [])
            log_agent_event("Claude call succeeded")
            return content[0]["text"] if content else "[Claude returned no content]"
        else:
            log_agent_event(f"Claude API error: {response.status_code} — {response.text}")
            return f"[Claude error {response.status_code}]"
    except Exception as e:
        log_agent_event(f"Claude API exception: {str(e)}")
        return "[Claude request failed — fallback to local]"

def call_claude_with_system(prompt: str, system_prompt: str = "", model="claude-3-sonnet-20240229") -> str:
    """
    Make Claude API call with system prompt for enhanced control
    """
    check = enforce_key_check("Claude")

    if not check["allowed"]:
        log_agent_event(f"Janus blocked Claude API call (with system): {check['reason']}")
        return "[Local Only Mode] Claude call blocked: " + check["reason"]

    api_key = load_api_key("Claude")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": model,
        "max_tokens": 400,
        "temperature": 0.7,
        "messages": [{"role": "user", "content": prompt}]
    }

    if system_prompt:
        payload["system"] = system_prompt

    try:
        response = requests.post(CLAUDE_ENDPOINT, headers=headers, json=payload, timeout=8)
        if response.status_code == 200:
            content = response.json().get("content", [])
            log_agent_event("Claude call (with system) succeeded")
            return content[0]["text"] if content else "[Claude returned no content]"
        else:
            log_agent_event(f"Claude API error: {response.status_code} — {response.text}")
            return f"[Claude error {response.status_code}]"
    except Exception as e:
        log_agent_event(f"Claude API exception: {str(e)}")
        return "[Claude request failed — fallback to local]"

def test_claude_connection() -> dict:
    """
    Test Claude API connectivity for key validation
    """
    check = enforce_key_check("Claude")

    if not check["allowed"]:
        return {
            "status": check["status"],
            "message": check["reason"]
        }

    try:
        result = call_claude("Hello", model="claude-3-haiku-20240307")  # Use cheaper model for tests
        if not result.startswith("["):  # Not an error message
            return {
                "status": "Valid",
                "message": "Connection successful"
            }
        else:
            return {
                "status": "Error",
                "message": result
            }
    except Exception as e:
        return {
            "status": "Error",
            "message": str(e)
        }