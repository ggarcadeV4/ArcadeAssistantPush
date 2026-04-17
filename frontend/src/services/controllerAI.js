import { buildStandardHeaders, resolveDeviceId } from '../utils/identity';

export async function controllerAIChat(message, panelState = {}, options = {}) {
  if (!message || typeof message !== 'string') {
    throw new Error('message is required');
  }

  const deviceId = options.deviceId || resolveDeviceId();
  const panel = options.panel || 'controller';

  // Build system prompt based on panel type
  const systemPrompt = panel === 'controller-chuck' || panel === 'chuck'
    ? `You are Chuck, a Brooklyn-accented arcade technician who helps with encoder board setup.

Core capabilities:
- Arcade encoder boards (I-PAC, Ultimarc, etc.)
- Pin mapping and configuration
- MAME config generation
- USB controller detection
- Troubleshooting hardware issues
- Managing controller configuration files and mappings

IMPORTANT CAPABILITIES:
- You CAN modify configuration files through the Arcade Assistant architecture
- Controller mappings stored in configs/controllers/controls.json
- You can create/modify button-to-pin mappings for arcade controls
- You can generate MAME configuration files (mame.ini, ctrlr/*.cfg)
- You can set up custom profiles for different cabinets
- All changes use preview/apply workflow with automatic backups
- You can trigger cascades to sync configs to LED Blinky and emulators

WHEN USERS ASK ABOUT CHANGING SETTINGS:
- Explain what you can modify (pin mappings, MAME configs, button assignments)
- Offer to create/modify controller profiles
- Mention changes will be previewed before applying
- All modifications create automatic backups
- You have full access to the Arcade Assistant's safe file modification system

Communication style:
- Brooklyn accent (e.g., "Yo!", "Ey!", "Lookin' good!")
- Concise and practical (2-3 sentences)
- Friendly and encouraging
- Technical but approachable

Current panel state: ${JSON.stringify(panelState)}`
    : `You are a helpful controller configuration assistant.`;

  // Use gateway AI endpoint instead of backend
  const res = await fetch('/api/ai/chat', {
    method: 'POST',
    headers: {
      ...buildStandardHeaders({
        panel,
        scope: 'state',
        extraHeaders: { 'content-type': 'application/json' }
      }),
      'x-device-id': deviceId
    },
    body: JSON.stringify({
      provider: 'gemini',
      model: 'gemini-2.0-flash',
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: message }
      ],
      max_tokens: 500,
      temperature: 0.7
    })
  });

  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = body?.detail || body?.message || body?.code || 'Controller AI request failed';
    if (
      res.status === 501 ||
      res.status === 502 ||
      body?.code === 'NOT_CONFIGURED' ||
      /provider unavailable/i.test(detail)
    ) {
      return buildOfflineResponse({
        message,
        panelState,
        panel,
        detail,
      });
    }
    throw new Error(detail);
  }

  // Transform gateway response to expected format
  return {
    message: body.message,
    reply: body.message?.content,
    response: body.message?.content
  };
}

export async function controllerAIHealth(options = {}) {
  const deviceId = options.deviceId || resolveDeviceId();
  const panel = options.panel || 'controller';

  const res = await fetch('/api/controller/ai/health', {
    method: 'GET',
    headers: {
      ...buildStandardHeaders({ panel, scope: 'state' }),
      'x-device-id': deviceId
    }
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw body;
  return body;
}

function buildOfflineResponse({ message, panelState, panel, detail }) {
  const lower = (message || '').toLowerCase();
  const context = {
    offline: true,
    error: detail,
    timestamp: new Date().toISOString(),
  };

  if (panel === 'console-wizard' || panel === 'console' || panel === 'wizard') {
    const step = panelState?.currentStep;
    let reply = 'My link to the great library is faint, but I can still guide you through the basics.';

    if (/hello|hi|hey/.test(lower)) {
      reply = 'Greetings, apprentice. Though the oracle is offline, I stand ready to help using the knowledge etched in crystal.';
    } else if (/detect/.test(lower)) {
      reply = 'To detect controllers, ensure the handheld is connected and press “Detect Devices.” If nothing appears, check USB permissions or run start-gui.bat on Windows.';
    } else if (/profile/.test(lower)) {
      reply = 'Select a profile from the list, then choose the player slot. You can adjust hotkeys or deadzones before generating the RetroArch config.';
    } else if (/apply|generate/.test(lower)) {
      reply = 'When you reach the Review step, press “Generate Config.” The wizard will stage RetroArch first; afterwards, mirror to other emulators.';
    } else if (step === 0) {
      reply = 'Begin with “Detect.” Once a controller appears, choose a profile that matches its layout.';
    }

    return {
      reply,
      context,
    };
  }

  if (panel === 'controller-chuck' || panel === 'controller' || panel === 'chuck') {
    const mapping = panelState?.mapping || {};
    const mappedButtons = Object.keys(mapping).length;

    let reply = 'Chuck here. The fancy AI is offline, but I\'ve still got the muscle memory. I can help with manual steps.';

    if (/hello|hi|hey/.test(lower)) {
      reply = 'Yo! Chuck on the line. Cloud brain\'s taking five, but I\'m still wrench-ready.';
    } else if (/detect/.test(lower)) {
      reply = 'Smack the “Scan Devices” button. If nothing shows, double-check USB and make sure the backend is running with access to the encoder.';
    } else if (/pin|mapping/.test(lower)) {
      reply = 'Pick a control from the grid, set its pin, hit Preview, then Apply. Keep an eye out for the cascade prompt to sync LEDs and emulators.';
    } else if (/mame/.test(lower)) {
      reply = 'Generate the MAME config after you\'re happy with the pin layout. The cascade will validate MAME via listxml once it runs.';
    } else if (/cascade/.test(lower)) {
      reply = 'After applying mappings, run the cascade to push updates to LED Blinky, MAME, and friends. Use the new Cascade Status card if you skipped it earlier.';
    } else if (mappedButtons === 0) {
      reply = 'Looks like the mapping dictionary is empty. Load the factory defaults or start assigning pins to get rolling.';
    }

    return {
      reply,
      context,
    };
  }

  return {
    reply: 'The AI assistant is currently offline. Please refer to the panel instructions or try again later.',
    context,
  };
}
