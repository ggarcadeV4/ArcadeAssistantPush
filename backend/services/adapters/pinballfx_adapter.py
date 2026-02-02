from typing import Any, Dict

def is_enabled(manifest: Dict[str, Any]) -> bool:
    return False

def can_handle(game: Any, manifest: Dict[str, Any]) -> bool:
    return False

def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    return {}

def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    return {"success": False, "message": "Pinball FX adapter stub (not enabled)"}

