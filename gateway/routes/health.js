import express from 'express';
import { getDriveStatus } from '../utils/driveDetection.js';

const router = express.Router();

router.get('/', async (req, res) => {
  try {
    const driveStatus = getDriveStatus();

    const healthInfo = {
      status: 'ok',
      gateway: {
        uptime: process.uptime(),
        memory: process.memoryUsage(),
        version: process.version,
        env: process.env.NODE_ENV || 'development'
      },
      drive: driveStatus,
      services: {
        tts: {
          available: !!process.env.ELEVENLABS_API_KEY,
          provider: process.env.ELEVENLABS_API_KEY ? 'elevenlabs' : 'unconfigured',
          voices: {
            lora: process.env.LORA_VOICE_ID || 'pFZP5JQG7iQjIQuC4Bku'
          }
        }
      },
      fastapi: {
        url: req.app.locals.fastapiUrl,
        connected: false
      }
    };

    // Test FastAPI connection
    try {
      const fastapiResponse = await fetch(`${req.app.locals.fastapiUrl}/health`);
      if (fastapiResponse.ok) {
        const fastapiHealth = await fastapiResponse.json();
        healthInfo.fastapi.connected = true;
        healthInfo.fastapi.details = fastapiHealth;
      }
    } catch (err) {
      healthInfo.fastapi.error = err.message;
    }

    res.json(healthInfo);
  } catch (err) {
    res.status(500).json({
      status: 'error',
      error: err.message
    });
  }
});

export default router;
