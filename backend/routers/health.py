from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.routers.config_ops import log_change
from backend.services.system_health import health_service


def _is_wsl() -> bool:
    try:
        if platform.system().lower() != "linux":
            return False
        with open("/proc/version", "r", encoding="utf-8") as f:
            data = f.read().lower()
            return "microsoft" in data or "wsl" in data
    except Exception:
        return False


def _get_vault_status() -> dict:
    """Report DPAPI vault state without exposing secret values."""
    import os
    from pathlib import Path

    drive_root = os.environ.get("AA_DRIVE_ROOT", "A:\\Arcade Assistant Local")
    vault_path = Path(drive_root) / ".aa" / "credentials.dat"

    if not vault_path.exists():
        return {"status": "missing", "path": str(vault_path)}

    tier1_keys = [
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "AA_PROVISIONING_TOKEN",
        "AA_SERVICE_TOKEN",
    ]
    loaded_keys = [
        k for k in tier1_keys
        if os.environ.get(k) not in (None, "", "VAULT_MANAGED")
    ]

    return {
        "status": "loaded" if loaded_keys else "present_not_loaded",
        "secrets_active": len(loaded_keys),
        "path": str(vault_path),
    }


def _require_mutation_headers(request: Request) -> None:
    scope = request.headers.get("x-scope")
    if not scope or scope.lower() != "state":
        raise HTTPException(status_code=400, detail="x-scope=state required for this operation")
    device_id = request.headers.get("x-device-id")
    if not device_id:
        raise HTTPException(status_code=400, detail="x-device-id header required")
    panel = request.headers.get("x-panel")
    if not panel or panel.lower() != "doc":
        raise HTTPException(status_code=403, detail="x-panel must be 'doc' for Doc panel actions")


def _build_summary_payload(request: Request, hardware_status: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
    drive_root: Path = request.app.state.drive_root
    manifest = request.app.state.manifest or {}
    policies = request.app.state.policies or {}
    manifest_path = drive_root / ".aa" / "manifest.json"
    policies_path = drive_root / ".aa" / "policies.json"
    sanctioned_paths = manifest.get("sanctioned_paths", [])
    return {
        "status": "ok",
        "timestamp": timestamp,
        "drive_root": str(drive_root),
        "manifest_exists": manifest_path.exists(),
        "policies_exists": policies_path.exists(),
        "sanctioned_paths": sanctioned_paths,
        "sanctioned_paths_count": len(sanctioned_paths),
        "emulators": list(policies.keys()),
        "backup_on_write": request.app.state.backup_on_write,
        "dry_run_default": request.app.state.dry_run_default,
        "platform": platform.system(),
        "wsl": _is_wsl(),
        "usb_backend": hardware_status.get("usb_backend"),
        "hardware_status": hardware_status,
        "vault_status": _get_vault_status(),
        "stt_configured": bool(
            os.getenv("DEEPGRAM_API_KEY")
            or os.getenv("WHISPER_LOCAL")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("WHISPER_API_KEY")
        ),
        "stt_provider": (
            "deepgram"
            if os.getenv("DEEPGRAM_API_KEY")
            else (
                "whisper_local"
                if os.getenv("WHISPER_LOCAL")
                else (
                    "whisper_openai"
                    if (os.getenv("OPENAI_API_KEY") or os.getenv("WHISPER_API_KEY"))
                    else "unconfigured"
                )
            )
        ),
        "tts_usage": None,
        "llm_provider": "gemini",
    }


def _log_health_action(
    request: Request,
    target_suffix: str,
    payload: Dict[str, Any],
    result: str = "recorded",
) -> None:
    drive_root: Optional[Path] = getattr(request.app.state, "drive_root", None)
    if not drive_root:
        return
    log_change(
        request,
        drive_root,
        f"health/{target_suffix}",
        "state",
        payload,
        backup_path=None,
        result=result,
    )


router = APIRouter()


@router.get("")
async def health_check(request: Request):
    try:
        performance = health_service.collect_performance_snapshot(request.app.state)
        hardware = health_service.collect_hardware()
        return JSONResponse(content=_build_summary_payload(request, hardware, performance["timestamp"]))
    except Exception as exc:  # pragma: no cover - defensive
        return JSONResponse(status_code=500, content={"status": "error", "error": str(exc)})


@router.get("/summary")
async def health_summary(request: Request):
    performance = health_service.collect_performance_snapshot(request.app.state)
    hardware = health_service.collect_hardware()
    return _build_summary_payload(request, hardware, performance["timestamp"])


@router.get("/performance")
async def health_performance(request: Request):
    return health_service.collect_performance_snapshot(request.app.state)


@router.get("/performance/timeseries")
async def health_performance_timeseries(request: Request):
    return {"samples": health_service.get_performance_timeseries(request.app.state)}


@router.get("/processes")
async def health_processes():
    return health_service.collect_processes()


@router.get("/hardware")
async def health_hardware():
    return health_service.collect_hardware()


@router.get("/alerts/active")
async def health_alerts_active(request: Request):
    performance = health_service.collect_performance_snapshot(request.app.state)
    hardware = health_service.collect_hardware()
    drive_root: Path = request.app.state.drive_root
    alerts = health_service.get_active_alerts(drive_root, performance, hardware)
    return {
        "alerts": alerts,
        "timestamp": performance.get("timestamp"),
        "performance": performance,
        "hardware": hardware,
    }


@router.get("/alerts/history")
async def health_alerts_history(request: Request):
    drive_root: Path = request.app.state.drive_root
    return {"alerts": health_service.get_alert_history(drive_root)}


@router.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str, request: Request, payload: Dict[str, Any] = Body(default_factory=dict)):
    _require_mutation_headers(request)
    drive_root: Path = request.app.state.drive_root
    reason = payload.get("reason")
    result = health_service.dismiss_alert(drive_root, alert_id, reason)
    _log_health_action(request, f"alerts/{alert_id}/dismiss", {"reason": reason}, result="dismissed")
    return result


@router.post("/actions/optimize")
async def optimize_action(request: Request, payload: Dict[str, Any] = Body(default_factory=dict)):
    _require_mutation_headers(request)
    action_payload = {"action": "optimize", "parameters": payload or {}}
    _log_health_action(request, "actions/optimize", action_payload, result="queued")
    return {
        "status": "queued",
        "message": "Optimization request recorded",
        "action": action_payload,
    }


@router.get("/diagnose")
async def diagnose_all(request: Request):
    """
    Unified diagnostic endpoint - "What's wrong?"
    
    Aggregates health status from all panels into a single, human-readable
    response. This is the endpoint to call when someone at the cabinet
    asks "What's wrong?" or "Is everything working?"
    
    Returns:
        issues: List of detected problems with suggested fixes
        status: overall | degraded | critical
        summary: Human-readable summary for voice/chat
        panels: Per-panel status breakdown
    """
    issues = []
    panels = {}
    
    drive_root: Path = request.app.state.drive_root
    
    # 1. Check Controller Health
    try:
        from ..services.usb_detector import detect_usb_devices, USBBackendError, USBPermissionError
        try:
            devices = detect_usb_devices(include_unknown=False, use_cache=True)
            panels["controller"] = {"status": "ok", "devices": len(devices)}
        except USBBackendError:
            panels["controller"] = {"status": "degraded", "error": "usb_backend_unavailable"}
            issues.append({
                "panel": "Controller Chuck",
                "severity": "warning",
                "problem": "USB backend unavailable - controller detection limited",
                "fix": "Run on Windows or attach USB device via usbipd on WSL"
            })
        except USBPermissionError:
            panels["controller"] = {"status": "degraded", "error": "permission_denied"}
            issues.append({
                "panel": "Controller Chuck",
                "severity": "warning",
                "problem": "USB permission denied",
                "fix": "Run as Administrator (Windows) or add user to plugdev (Linux)"
            })
    except Exception as e:
        panels["controller"] = {"status": "unknown", "error": str(e)}
    
    # 2. Check LED Status
    try:
        led_config = drive_root / "config" / "led" / "led_config.json"
        if led_config.exists():
            panels["led"] = {"status": "ok", "config_exists": True}
        else:
            panels["led"] = {"status": "ok", "config_exists": False, "note": "simulation_mode"}
    except Exception as e:
        panels["led"] = {"status": "unknown", "error": str(e)}
    
    # 3. Check Emulator Configs
    try:
        emulators_dir = drive_root / "config" / "emulators"
        if emulators_dir.exists():
            emulator_configs = list(emulators_dir.glob("*.json"))
            panels["console_wizard"] = {"status": "ok", "configs": len(emulator_configs)}
        else:
            panels["console_wizard"] = {"status": "ok", "configs": 0}
    except Exception as e:
        panels["console_wizard"] = {"status": "unknown", "error": str(e)}
    
    # 4. Check LaunchBox/LoRa
    try:
        launchers_file = drive_root / "config" / "launchers.json"
        if launchers_file.exists():
            panels["lora"] = {"status": "ok", "launchers_configured": True}
        else:
            panels["lora"] = {"status": "degraded", "launchers_configured": False}
            issues.append({
                "panel": "LoRa",
                "severity": "info",
                "problem": "Launchers config not found",
                "fix": "Configure emulator paths in launchers.json"
            })
    except Exception as e:
        panels["lora"] = {"status": "unknown", "error": str(e)}
    
    # 5. Check Gunner (Light Guns)
    try:
        gun_config = drive_root / "config" / "gun_models.json"
        panels["gunner"] = {"status": "ok", "custom_config": gun_config.exists()}
    except Exception as e:
        panels["gunner"] = {"status": "unknown", "error": str(e)}
    
    # 6. Check ScoreKeeper
    try:
        scores_file = drive_root / "state" / "scorekeeper" / "scores.jsonl"
        tournaments_dir = drive_root / "state" / "scorekeeper" / "tournaments"
        panels["scorekeeper"] = {
            "status": "ok",
            "scores_file": scores_file.exists(),
            "tournaments": len(list(tournaments_dir.glob("*.json"))) if tournaments_dir.exists() else 0
        }
    except Exception as e:
        panels["scorekeeper"] = {"status": "unknown", "error": str(e)}
    
    # 7. Check active alerts
    try:
        performance = health_service.collect_performance_snapshot(request.app.state)
        hardware = health_service.collect_hardware()
        alerts = health_service.get_active_alerts(drive_root, performance, hardware)
        for alert in alerts:
            issues.append({
                "panel": "System",
                "severity": alert.get("severity", "warning"),
                "problem": alert.get("message", "Unknown alert"),
                "fix": alert.get("action", "Check system health panel")
            })
    except Exception:
        pass
    
    # Determine overall status
    if any(i["severity"] == "critical" for i in issues):
        overall_status = "critical"
    elif any(i["severity"] == "warning" for i in issues):
        overall_status = "degraded"
    elif issues:
        overall_status = "info"
    else:
        overall_status = "ok"
    
    # Build human-readable summary
    if not issues:
        summary = "Everything looks good! All systems are operational."
    elif len(issues) == 1:
        issue = issues[0]
        summary = f"I found 1 issue: {issue['problem']}. {issue['fix']}"
    else:
        summary = f"I found {len(issues)} issues: "
        summary += "; ".join([f"({i+1}) {issue['problem']}" for i, issue in enumerate(issues[:3])])
        if len(issues) > 3:
            summary += f" ...and {len(issues) - 3} more."
    
    return {
        "status": overall_status,
        "summary": summary,
        "issues": issues,
        "issue_count": len(issues),
        "panels": panels,
        "timestamp": health_service.collect_performance_snapshot(request.app.state).get("timestamp")
    }
