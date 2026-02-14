import asyncio

import pytest

from backend.services.led_engine.devices import DeviceRegistry
from backend.services.led_engine.engine import LEDEngine
from backend.services.led_engine.ledwiz_discovery import DeviceInfo


@pytest.mark.asyncio
async def test_discover_devices_filters_supported_ids(monkeypatch):
    from backend.services.led_engine import ledwiz_discovery

    class StubHID:
        @staticmethod
        def enumerate():
            return [
                {
                    "vendor_id": 0xFAFA,
                    "product_id": 0x00F0,
                    "path": b"usb-test-0",
                    "serial_number": "LEDWIZ-001",
                    "manufacturer_string": "Groovy",
                    "product_string": "LED-Wiz",
                },
                {
                    "vendor_id": 0x0001,
                    "product_id": 0x0002,
                    "path": b"skip-me",
                },
            ]

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(ledwiz_discovery, "hid", StubHID)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    devices = await ledwiz_discovery.discover_devices()
    assert len(devices) == 1
    assert devices[0].vendor_id == 0xFAFA
    assert devices[0].product_id == 0x00F0
    assert devices[0].serial_number == "LEDWIZ-001"


@pytest.mark.asyncio
async def test_device_registry_tracks_discovery(monkeypatch):
    from backend.services.led_engine import ledwiz_discovery

    async def fake_discover():
        return [
            DeviceInfo(
                path=b"usb-test-1",
                vendor_id=0xFAFA,
                product_id=0x00F0,
                serial_number="LEDWIZ-XYZ",
                manufacturer="Groovy",
                product="LED-Wiz Tester",
            )
        ]

    monkeypatch.setattr(ledwiz_discovery, "discover_devices", fake_discover)

    registry = DeviceRegistry()
    await registry.refresh()
    assert registry.simulation_mode() is False
    devices = list(registry.all_devices())
    assert len(devices) == 1
    discovery = registry.discovery_snapshot()
    assert len(discovery) == 1
    assert discovery[0].serial_number == "LEDWIZ-XYZ"


@pytest.mark.asyncio
async def test_led_engine_status_includes_diagnostics(monkeypatch, tmp_path):
    from backend.services.led_engine import ledwiz_discovery

    async def no_devices():
        return []

    monkeypatch.setattr(ledwiz_discovery, "discover_devices", no_devices)

    engine = LEDEngine(drive_root=tmp_path, manifest={})
    engine.ensure_started()
    await asyncio.sleep(0.05)
    await engine.update_brightness(70)
    await asyncio.sleep(0.05)
    status = await engine.status()
    await engine.shutdown()

    assert "engine" in status
    diagnostics = status["engine"]
    assert diagnostics["mode"] == "simulation"
    assert diagnostics["simulation_mode"] is True
    assert diagnostics["connected_devices"] == []
    assert isinstance(diagnostics["tick_ms"], float)
    assert diagnostics["last_hid_write"] is None


@pytest.mark.asyncio
async def test_channel_test_simulation(monkeypatch, tmp_path):
    from backend.services.led_engine import ledwiz_discovery

    async def no_devices():
        return []

    monkeypatch.setattr(ledwiz_discovery, "discover_devices", no_devices)

    engine = LEDEngine(drive_root=tmp_path, manifest={})
    engine.ensure_started()
    result = await engine.channel_test(None, channel=0, duration_ms=150)
    await engine.shutdown()

    assert result["status"] == "ok"
    assert result["mode"] == "simulation"
    assert result["simulated"] is True


@pytest.mark.asyncio
async def test_health_snapshot_reports_queue(monkeypatch, tmp_path):
    from backend.services.led_engine import ledwiz_discovery

    async def no_devices():
        return []

    monkeypatch.setattr(ledwiz_discovery, "discover_devices", no_devices)

    engine = LEDEngine(drive_root=tmp_path, manifest={})
    engine.ensure_started()
    await engine.run_pattern("solid", {"color": "#FFFFFF"}, duration_ms=200)
    snapshot = await engine.health_snapshot()
    await engine.shutdown()

    assert snapshot["running"] is True or snapshot["running"] is False  # bool present
    assert "queue_depth" in snapshot
    assert "stuck_commands" in snapshot
    assert snapshot["simulation_mode"] is True
