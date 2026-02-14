# @agent: Janus
# @role: Enforces API usage rules and fallback logic for Hermes
# @linked_panels: ApiKeyManagerPanel (B2), DebugPanel (C3)

import os
from .hermes import load_api_key, test_api_key

LOCAL_ONLY_FLAG = "secure/local_only.flag"

def is_local_only_mode():
    """Check if local-only mode is enabled"""
    return os.path.exists(LOCAL_ONLY_FLAG)

def set_local_only_mode(enabled: bool):
    """Enable or disable local-only mode"""
    if enabled:
        with open(LOCAL_ONLY_FLAG, "w") as f:
            f.write("1")
    else:
        if os.path.exists(LOCAL_ONLY_FLAG):
            os.remove(LOCAL_ONLY_FLAG)

def enforce_key_check(provider: str) -> dict:
    """
    Called before any cloud request. Returns permission and status.
    This is Janus's primary enforcement function.
    """
    if is_local_only_mode():
        return {
            "allowed": False,
            "reason": "Local-only mode enabled",
            "status": "Blocked"
        }

    key = load_api_key(provider)
    if not key:
        return {
            "allowed": False,
            "reason": "API key missing",
            "status": "Missing"
        }

    status = test_api_key(provider)
    if status != "Valid":
        return {
            "allowed": False,
            "reason": f"Key test failed: {status}",
            "status": status
        }

    return {
        "allowed": True,
        "status": "Valid",
        "reason": "API key validated"
    }

def get_api_access_summary() -> str:
    """
    Get summary of API access state for DebugPanel display
    """
    if is_local_only_mode():
        return "Local Only"

    providers = ["Claude", "OpenAI", "Anthropic"]
    valid_providers = []

    for provider in providers:
        result = enforce_key_check(provider)
        if result["allowed"]:
            valid_providers.append(provider)

    if not valid_providers:
        return "No Valid Keys"
    elif len(valid_providers) == len(providers):
        return "All Valid"
    else:
        return f"Valid ({', '.join(valid_providers)})"

def audit_api_request(provider: str, endpoint: str, success: bool):
    """
    Log API request attempts for security auditing
    """
    from services.+logging.agent_log_writer import log_agent_event

    status = "Success" if success else "Failed"
    enforcement_result = enforce_key_check(provider)

    log_message = f"Janus: {provider} API {endpoint} → {status} (Key: {enforcement_result['status']})"
    log_agent_event(log_message)

def security_violation_report(violation_type: str, details: str):
    """
    Report security violations to DebugPanel and logs
    """
    from services.+logging.agent_log_writer import log_agent_event

    log_message = f"Janus SECURITY: {violation_type} → {details}"
    log_agent_event(log_message)