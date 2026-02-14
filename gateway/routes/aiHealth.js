import express from 'express';
import { env } from '../config/env.js';

const router = express.Router();

router.get('/', (_req, res) => {
  const claude = !!env.ANTHROPIC_API_KEY;
  const gpt = !!env.OPENAI_API_KEY;
  res.json({
    provider_default: env.AI_DEFAULT_PROVIDER,
    providers: {
      claude: { configured: claude },
      gpt: { configured: gpt }
    }
  });
});

export default router;

