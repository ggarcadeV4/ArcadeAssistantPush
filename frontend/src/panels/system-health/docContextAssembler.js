/**
 * docContextAssembler.js
 * ===================================================================
 * Builds Doc's context payload so the AI can answer questions about
 * real-time system health (CPU, memory, processes, hardware, alerts).
 *
 * Called by useDiagnosisMode() on entry and every 30 s, AND on every
 * regular chat message when no diag context is already present.
 *
 * PANEL SCOPE: Doc focuses on cabinet system health telemetry.
 * The assembler provides runtime health context for Doc chat and diagnosis.
 */

import { buildStandardHeaders } from '../../utils/identity';

const HEALTH_API = '/api/local/health';

/** Silent fetch - returns null on any error */
async function safeFetch(url) {
    try {
        const res = await fetch(url, {
            headers: buildStandardHeaders({ panel: 'doc', scope: 'state' }),
        });
        if (!res.ok) return null;
        return await res.json();
    } catch {
        return null;
    }
}

/**
 * Main assembler - exported and consumed by EngineeringBaySidebar.
 * @returns {Promise<{tier1, tier2, tier3}>}
 */
export async function docContextAssembler() {
    // -- Tier 1: Always included (core telemetry) ------------------------
    const [summary, gateway, performance, processes, hardware, alertsData] = await Promise.all([
        safeFetch(`${HEALTH_API}/summary`),
        safeFetch('/api/health'),
        safeFetch(`${HEALTH_API}/performance`),
        safeFetch(`${HEALTH_API}/processes`),
        safeFetch(`${HEALTH_API}/hardware`),
        safeFetch(`${HEALTH_API}/alerts/active`),
    ]);

    const cpuPercent = performance?.cpu?.percent;
    const memPercent = performance?.memory?.percent;
    const memUsedGb = performance?.memory?.used_gb;
    const memTotalGb = performance?.memory?.total_gb;
    const uptimeSec = performance?.uptime_seconds;
    const alerts = alertsData?.alerts ?? [];
    const dependencies = summary?.dependencies ?? {};

    const tier1 = {
        diagMode: true,
        timestamp: new Date().toISOString(),
        cabinet: {
            dependency_status: summary?.dependency_overview?.status ?? 'unknown',
            dependencies: {
                configured_root: dependencies.configured_root?.summary ?? null,
                manifest: dependencies.manifest?.summary ?? null,
                launchbox: dependencies.launchbox?.summary ?? null,
                plugin: dependencies.plugin?.summary ?? null,
                emulators: dependencies.emulators?.summary ?? null,
                roms: dependencies.roms?.summary ?? null,
                bios: dependencies.bios?.summary ?? null,
            },
        },
        gateway: {
            status: gateway?.fastapi?.connected ? 'ok' : 'degraded',
            summary: gateway?.fastapi?.connected
                ? 'Gateway is connected to the backend'
                : 'Gateway cannot confirm backend connectivity',
        },
        system: {
            cpu_percent: cpuPercent ?? 'unavailable',
            memory_percent: memPercent ?? 'unavailable',
            memory_used_gb: memUsedGb ?? null,
            memory_total_gb: memTotalGb ?? null,
            uptime_seconds: uptimeSec ?? null,
            uptime_human: uptimeSec != null
                ? `${Math.floor(uptimeSec / 3600)}h ${Math.floor((uptimeSec % 3600) / 60)}m`
                : null,
            fps: performance?.fps ?? null,
            latency_ms: performance?.latency_ms ?? null,
            gpu_temp_c: performance?.gpu_temp_c ?? null,
            psutil_available: performance?.psutil_available ?? false,
        },
        alerts: {
            count: alerts.length,
            items: alerts.slice(0, 5).map(a => ({
                id: a.id,
                title: a.title,
                severity: a.severity,
                message: a.message,
            })),
        },
    };

    // -- Tier 2: Conditional (processes + hardware, only when data exists) ----
    const tier2 = {};

    if (processes?.groups) {
        const groups = processes.groups;
        tier2.processes = {};
        for (const group of groups) {
            const top5 = (group.processes || [])
                .sort((a, b) => (b.cpu_percent || 0) - (a.cpu_percent || 0))
                .slice(0, 5)
                .map(p => ({
                    name: p.name,
                    pid: p.pid,
                    cpu: p.cpu_percent,
                    mem_mb: p.memory_bytes ? Math.round(p.memory_bytes / (1024 * 1024)) : null,
                    status: p.status,
                }));
            if (top5.length > 0) {
                tier2.processes[group.id] = {
                    title: group.title,
                    count: (group.processes || []).length,
                    top5,
                };
            }
        }
    }

    if (hardware?.categories) {
        tier2.hardware = {};
        for (const cat of hardware.categories) {
            const devices = (cat.devices || []).map(d => ({
                name: d.name,
                status: d.status,
                health: d.health,
            }));
            if (devices.length > 0) {
                tier2.hardware[cat.id] = {
                    title: cat.title,
                    devices,
                };
            }
        }
        tier2.hardwareStatus = hardware.status ?? 'unknown';
        tier2.usbBackend = hardware.usb_backend ?? 'unknown';
    }

    // -- Tier 3: Static knowledge (Doc's reference material) -------------
    const tier3 = {
        panelRole: 'Doc is the system health diagnostic AI for Arcade Assistant.',
        capabilities: [
            'Read real-time CPU and memory usage',
            'List running processes by category (gaming, assistant, system)',
            'Report hardware device status and USB connections',
            'Evaluate and triage active health alerts',
            'Suggest optimization actions',
        ],
        alertThresholds: {
            cpu_warning: '85% and above',
            memory_warning: '90% and above',
        },
    };

    return { tier1, tier2, tier3 };
}
