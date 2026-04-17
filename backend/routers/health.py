from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.constants.drive_root import (
    get_bios_root,
    get_console_roms_root,
    get_drive_root,
    get_emulators_root,
    get_launchbox_root,
    get_roms_root,
    paths_equivalent,
    resolve_drive_root_input,
    resolve_runtime_path,
)
from backend.models.emulator_config import EmulatorDefinition
from backend.routers.config_ops import log_change
from backend.services.emulator_detector import EmulatorDetector
from backend.services.launchbox_plugin_client import get_plugin_client
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

    vault_path = get_drive_root(allow_cwd_fallback=True, context="health vault status") / ".aa" / "credentials.dat"

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


def _path_exists(path: Optional[Path]) -> bool:
    try:
        return path is not None and "<AA_DRIVE_ROOT" not in str(path) and path.exists()
    except Exception:
        return False


def _path_has_entries(path: Optional[Path]) -> bool:
    if not _path_exists(path):
        return False
    try:
        next(path.iterdir())
        return True
    except StopIteration:
        return False
    except Exception:
        return False


def _status_rank(status: str) -> int:
    return {"ok": 0, "warning": 1, "error": 2}.get((status or "").lower(), 1)


def _merge_status(*statuses: str) -> str:
    if not statuses:
        return "warning"
    ranked = max(_status_rank(status) for status in statuses)
    return {0: "ok", 1: "warning", 2: "error"}[ranked]


def _trim_names(values: List[str], limit: int = 3) -> List[str]:
    trimmed = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        trimmed.append(text)
        if len(trimmed) >= limit:
            break
    return trimmed


def _check_payload(status: str, summary: str, detail: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "status": status,
        "summary": summary,
    }
    if detail:
        payload["detail"] = detail
    payload.update(extra)
    return payload


def _resolved_drive_root(request: Request) -> Optional[Path]:
    state_root = getattr(request.app.state, "drive_root", None)
    if isinstance(state_root, Path) and _path_exists(state_root):
        return state_root
    if state_root is not None:
        try:
            candidate = Path(state_root)
            if _path_exists(candidate):
                return candidate
        except Exception:
            pass

    return resolve_drive_root_input(os.getenv("AA_DRIVE_ROOT", "").strip())


def _resolve_emulator_path(
    emulator: EmulatorDefinition,
    drive_root: Path,
    launchbox_root: Path,
) -> Optional[Path]:
    resolved = resolve_runtime_path(
        emulator.executable_path,
        drive_root=drive_root,
        base=launchbox_root,
    )
    if resolved is not None:
        return resolved

    try:
        return emulator.resolve_path(launchbox_root)
    except Exception:
        return None


def _build_dependency_checks(request: Request) -> Dict[str, Any]:
    drive_root_env = os.getenv("AA_DRIVE_ROOT", "").strip()
    drive_root = _resolved_drive_root(request)
    manifest = getattr(request.app.state, "manifest", {}) or {}
    startup_errors = list(getattr(request.app.state, "startup_errors", []) or [])
    write_block_reason = getattr(request.app.state, "write_block_reason", None)

    manifest_path = drive_root / ".aa" / "manifest.json" if drive_root is not None else None
    manifest_exists = _path_exists(manifest_path)
    sanctioned_paths = manifest.get("sanctioned_paths") or []
    manifest_drive_root = str(manifest.get("drive_root") or "").strip()

    if not drive_root_env:
        configured_root = _check_payload(
            "error",
            "AA_DRIVE_ROOT is not configured.",
            "Doc cannot validate cabinet storage until a configured root is set.",
        )
    elif not _path_exists(drive_root):
        configured_root = _check_payload(
            "error",
            "Configured cabinet root is unreachable.",
            f"Expected cabinet root: {drive_root_env}",
            path=drive_root_env,
        )
    else:
        configured_root = _check_payload(
            "ok",
            "Configured cabinet root is reachable.",
            str(drive_root),
            path=str(drive_root),
        )

    if not _path_exists(drive_root):
        manifest_check = _check_payload(
            "error",
            "Manifest cannot be validated until the configured root is reachable.",
        )
    elif not manifest_exists:
        manifest_check = _check_payload(
            "error",
            "Cabinet manifest is missing.",
            f"Expected manifest at {manifest_path}",
        )
    elif not sanctioned_paths:
        manifest_check = _check_payload(
            "error",
            "Manifest is loaded but sanctioned paths are empty.",
            "Update .aa/manifest.json with the cabinet paths Doc is allowed to validate.",
        )
    elif drive_root_env and manifest_drive_root and not paths_equivalent(manifest_drive_root, drive_root_env):
        manifest_check = _check_payload(
            "error",
            "Manifest drive root does not match AA_DRIVE_ROOT.",
            f"Manifest: {manifest_drive_root} | Environment: {drive_root_env}",
        )
    else:
        manifest_check = _check_payload(
            "ok",
            f"Manifest loaded with {len(sanctioned_paths)} sanctioned paths.",
            str(manifest_path),
            path=str(manifest_path),
        )

    if not _path_exists(drive_root):
        launchbox_check = _check_payload(
            "error",
            "LaunchBox cannot be validated until the configured root is reachable.",
        )
        launchbox_root = None
    else:
        launchbox_root = get_launchbox_root(drive_root)
        platforms_dir = launchbox_root / "Data" / "Platforms"
        emulators_xml = launchbox_root / "Data" / "Emulators.xml"
        platform_xml_count = len(list(platforms_dir.glob("*.xml"))) if platforms_dir.exists() else 0

        if not launchbox_root.exists():
            launchbox_check = _check_payload(
                "error",
                "LaunchBox folder is missing.",
                str(launchbox_root),
                path=str(launchbox_root),
            )
        elif not (launchbox_root / "LaunchBox.exe").exists():
            launchbox_check = _check_payload(
                "error",
                "LaunchBox.exe is missing.",
                str(launchbox_root / "LaunchBox.exe"),
                path=str(launchbox_root / "LaunchBox.exe"),
            )
        elif not platforms_dir.exists():
            launchbox_check = _check_payload(
                "error",
                "LaunchBox platform XMLs are missing.",
                str(platforms_dir),
                path=str(platforms_dir),
            )
        elif not emulators_xml.exists():
            launchbox_check = _check_payload(
                "warning",
                "LaunchBox is installed, but Emulators.xml is missing.",
                f"{platform_xml_count} platform XMLs detected in {platforms_dir}",
                path=str(launchbox_root),
            )
        else:
            launchbox_check = _check_payload(
                "ok",
                "LaunchBox installation looks healthy.",
                f"{platform_xml_count} platform XMLs and Emulators.xml detected.",
                path=str(launchbox_root),
                platform_xml_count=platform_xml_count,
            )

    plugin_detail = None
    try:
        plugin_client = get_plugin_client()
        plugin_available = plugin_client.is_available()
        plugin_url = plugin_client.base_url
    except Exception as exc:
        plugin_available = False
        plugin_url = None
        plugin_detail = str(exc)

    plugin_check = _check_payload(
        "ok" if plugin_available else "warning",
        "LaunchBox plugin bridge is responding." if plugin_available else "LaunchBox plugin bridge is offline.",
        plugin_detail or (
            f"Bridge endpoint: {plugin_url}" if plugin_available else "LaunchBox features that require the plugin will fall back or stay unavailable."
        ),
        url=plugin_url,
        available=plugin_available,
    )

    if not _path_exists(drive_root):
        emulators_check = _check_payload(
            "error",
            "Emulator paths cannot be validated until the configured root is reachable.",
        )
    else:
        launchbox_root = launchbox_root or get_launchbox_root(drive_root)
        emulators_root = get_emulators_root(drive_root)
        emulator_config = EmulatorDetector.get_or_detect_config()
        emulator_defs = list((emulator_config.emulators or {}).values())

        if emulator_defs:
            valid_count = 0
            missing_titles: List[str] = []
            for emulator in emulator_defs:
                resolved = _resolve_emulator_path(emulator, drive_root, launchbox_root)
                if resolved is not None and resolved.exists():
                    valid_count += 1
                else:
                    missing_titles.append(emulator.title or emulator.id)

            total_count = len(emulator_defs)
            missing_count = total_count - valid_count
            status = "ok" if missing_count == 0 else "warning" if valid_count > 0 else "error"
            detail = (
                f"Missing: {', '.join(_trim_names(missing_titles))}"
                if missing_titles
                else "Every configured emulator executable resolved successfully."
            )
            emulators_check = _check_payload(
                status,
                f"{valid_count}/{total_count} configured emulator paths validated.",
                detail,
                configured_count=total_count,
                valid_count=valid_count,
                missing_count=missing_count,
                missing_examples=_trim_names(missing_titles),
                path=str(emulators_root),
            )
        elif emulators_root.exists():
            emulators_check = _check_payload(
                "warning",
                "Emulators root exists, but no configured emulator definitions were detected.",
                "Doc can confirm the folder exists, but it cannot validate per-emulator executables until LaunchBox Emulators.xml or saved emulator_paths.json is available.",
                path=str(emulators_root),
            )
        else:
            emulators_check = _check_payload(
                "error",
                "Emulators root is missing.",
                str(emulators_root),
                path=str(emulators_root),
            )

    if not _path_exists(drive_root):
        roms_check = _check_payload(
            "error",
            "ROM folders cannot be validated until the configured root is reachable.",
        )
    else:
        roms_root = get_roms_root(drive_root)
        console_roms_root = get_console_roms_root(drive_root)
        mame_roms_root = roms_root / "MAME"
        present_labels = [
            label
            for label, path in (
                ("Arcade ROM root", roms_root),
                ("MAME ROM set", mame_roms_root),
                ("Console ROM root", console_roms_root),
            )
            if path.exists()
        ]

        if roms_root.exists() and mame_roms_root.exists() and console_roms_root.exists():
            roms_check = _check_payload(
                "ok",
                "ROM folder structure looks healthy.",
                "Arcade, MAME, and console ROM roots are present.",
                path=str(roms_root),
            )
        elif present_labels:
            roms_check = _check_payload(
                "warning",
                "ROM folder structure is only partially present.",
                f"Present: {', '.join(present_labels)}",
                path=str(roms_root),
            )
        else:
            roms_check = _check_payload(
                "error",
                "ROM folders are missing.",
                str(roms_root),
                path=str(roms_root),
            )

    if not _path_exists(drive_root):
        bios_check = _check_payload(
            "error",
            "BIOS folders cannot be validated until the configured root is reachable.",
        )
    else:
        bios_root = get_bios_root(drive_root)
        system_bios_root = bios_root / "system"
        bios_has_entries = _path_has_entries(bios_root)
        system_bios_has_entries = _path_has_entries(system_bios_root)

        if system_bios_root.exists() and system_bios_has_entries:
            bios_check = _check_payload(
                "ok",
                "BIOS folder is present.",
                f"System BIOS files detected in {system_bios_root}",
                path=str(system_bios_root),
            )
        elif bios_root.exists() and bios_has_entries:
            bios_check = _check_payload(
                "warning",
                "BIOS files exist, but the expected system BIOS folder is incomplete.",
                f"Expected cabinet BIOS folder: {system_bios_root}",
                path=str(bios_root),
            )
        elif bios_root.exists():
            bios_check = _check_payload(
                "warning",
                "BIOS folder is present but appears empty.",
                str(bios_root),
                path=str(bios_root),
            )
        else:
            bios_check = _check_payload(
                "error",
                "BIOS folder is missing.",
                str(bios_root),
                path=str(bios_root),
            )

    checks = {
        "configured_root": configured_root,
        "manifest": manifest_check,
        "launchbox": launchbox_check,
        "plugin": plugin_check,
        "emulators": emulators_check,
        "roms": roms_check,
        "bios": bios_check,
    }

    overview_status = _merge_status(*(check["status"] for check in checks.values()))
    overview = {
        "status": overview_status,
        "ok_count": sum(1 for check in checks.values() if check["status"] == "ok"),
        "warning_count": sum(1 for check in checks.values() if check["status"] == "warning"),
        "error_count": sum(1 for check in checks.values() if check["status"] == "error"),
        "startup_errors": startup_errors,
        "write_block_reason": write_block_reason,
    }

    return {
        "checks": checks,
        "overview": overview,
    }


def _build_summary_payload(request: Request, hardware_status: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
    drive_root: Path = request.app.state.drive_root
    manifest = request.app.state.manifest or {}
    policies = request.app.state.policies or {}
    manifest_path = drive_root / ".aa" / "manifest.json"
    policies_path = drive_root / ".aa" / "policies.json"
    sanctioned_paths = manifest.get("sanctioned_paths", [])
    dependency_snapshot = _build_dependency_checks(request)
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
        "writes_allowed": bool(getattr(request.app.state, "writes_allowed", False)),
        "write_block_reason": getattr(request.app.state, "write_block_reason", None),
        "startup_errors": list(getattr(request.app.state, "startup_errors", []) or []),
        "dependencies": dependency_snapshot["checks"],
        "dependency_overview": dependency_snapshot["overview"],
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
