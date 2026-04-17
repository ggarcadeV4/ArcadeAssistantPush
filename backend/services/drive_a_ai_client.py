"""
Secure AI Client for Drive A - Arcade Assistant
This module replaces direct API calls with secure Supabase Edge Function proxies
"""

import os
import time
import requests
from typing import List, Dict, Optional, Any

from backend.constants.drive_root import get_drive_root

# Import telemetry function (try-except for standalone usage)
try:
    from backend.services.supabase_client import SupabaseClient
    _supabase = SupabaseClient()
    def _send_telemetry(cabinet_id, level, code, message, payload=None, panel='system'):
        try:
            from backend.services.supabase_client import TelemetryEntry
            entry = TelemetryEntry(
                cabinet_id=cabinet_id,
                level=level,
                code=code,
                message=message,
                payload=payload
            )
            _supabase.send_telemetry(entry)
        except Exception:
            pass  # Fire-and-forget
except ImportError:
    def _send_telemetry(*args, **kwargs):
        pass  # No telemetry available

class SecureAIClient:
    """
    Unified client for calling AI services through Supabase Edge Functions.
    All API keys are stored securely in Supabase and never exposed to the cabinet.
    """
    
    def __init__(self):
        self.supabase_url = os.environ.get("SUPABASE_URL")
        self.service_key = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_SERVICE_KEY")
        )
        self.cabinet_id = self._get_cabinet_id()
        self.tenant_id = os.environ.get("TENANT_ID", "gg_arcade")
        
        if not self.supabase_url or not self.service_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SERVICE_KEY must be set"
            )
    
    def _get_cabinet_id(self) -> str:
        """Read cabinet ID from drive_root/.aa/device_id.txt
        
        Golden Drive Contract: Uses AA_DRIVE_ROOT, no hardcoded A:\\.
        """
        drive_root = get_drive_root(allow_cwd_fallback=True, context="drive_a_ai_client cabinet id")
        device_id_path = os.path.join(str(drive_root), ".aa", "device_id.txt")
        try:
            with open(device_id_path, "r") as f:
                return f.read().strip()
        except Exception as e:
            print(f"Warning: Could not read cabinet_id from {device_id_path}: {e}")
            return "unknown-cabinet"
    
    def call_anthropic(
        self,
        messages: List[Dict[str, str]],
        model: str = "claude-3-5-sonnet-20241022",
        max_tokens: int = 4096,
        temperature: float = 1.0,
        panel: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Call Anthropic API through Supabase Edge Function.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Anthropic model name
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)
            panel: Panel name (e.g., 'dewey', 'lora', 'vicky')
        
        Returns:
            Anthropic API response dict
        """
        url = f"{self.supabase_url}/functions/v1/anthropic-proxy"
        
        payload = {
            "messages": messages,
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "cabinet_id": self.cabinet_id,
            "tenant_id": self.tenant_id,
            "panel": panel
        }
        
        start_time = time.time()
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60
        )
        latency_ms = int((time.time() - start_time) * 1000)
        
        response.raise_for_status()
        result = response.json()
        
        # Send AI telemetry (fire-and-forget)
        usage = result.get('usage', {})
        _send_telemetry(
            self.cabinet_id,
            'INFO',
            'AI_CALL',
            f'anthropic {model}: {latency_ms}ms',
            {
                'provider': 'anthropic',
                'model': model,
                'panel': panel or 'backend',
                'latency_ms': latency_ms,
                'input_tokens': usage.get('input_tokens'),
                'output_tokens': usage.get('output_tokens')
            },
            panel or 'backend'
        )
        
        return result

    def call_gemini(
        self,
        messages: List[Dict[str, str]],
        model: str = "gemini-2.5-flash",
        max_tokens: int = 4096,
        temperature: float = 0.4,
        panel: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Call Google Gemini API through Supabase Edge Function.

        Args:
            messages: List of message dicts with 'role' and 'content'.
                      'system' role messages are extracted and sent as systemInstruction.
            model: Gemini model name
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 2.0)
            panel: Panel name (e.g., 'dewey', 'lora', 'vicky')

        Returns:
            Gemini API response dict
        """
        url = f"{self.supabase_url}/functions/v1/gemini-proxy"

        # Extract system messages and convert to Gemini format
        system_parts = []
        gemini_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            else:
                # Gemini uses 'model' instead of 'assistant'
                gemini_role = "model" if role == "assistant" else "user"
                gemini_messages.append({"role": gemini_role, "content": content})

        payload: Dict[str, Any] = {
            "messages": gemini_messages,
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "cabinet_id": self.cabinet_id,
            "tenant_id": self.tenant_id,
            "panel": panel
        }

        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if tools:
            payload["tools"] = tools

        start_time = time.time()
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60
        )
        latency_ms = int((time.time() - start_time) * 1000)

        response.raise_for_status()
        result = response.json()

        # Send AI telemetry (fire-and-forget)
        usage = result.get('usage', {})
        _send_telemetry(
            self.cabinet_id,
            'INFO',
            'AI_CALL',
            f'gemini {model}: {latency_ms}ms',
            {
                'provider': 'gemini',
                'model': model,
                'panel': panel or 'backend',
                'latency_ms': latency_ms,
                'input_tokens': usage.get('input_tokens'),
                'output_tokens': usage.get('output_tokens')
            },
            panel or 'backend'
        )

        return result

    def call_openai(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4",
        max_tokens: Optional[int] = None,
        temperature: float = 1.0,
        panel: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Call OpenAI API through Supabase Edge Function.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: OpenAI model name
            max_tokens: Maximum tokens to generate (optional)
            temperature: Sampling temperature (0.0 to 2.0)
            panel: Panel name (e.g., 'dewey', 'lora', 'vicky')
        
        Returns:
            OpenAI API response dict
        """
        url = f"{self.supabase_url}/functions/v1/openai-proxy"
        
        payload = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "cabinet_id": self.cabinet_id,
            "tenant_id": self.tenant_id,
            "panel": panel
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        start_time = time.time()
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60
        )
        latency_ms = int((time.time() - start_time) * 1000)
        
        response.raise_for_status()
        result = response.json()
        
        # Send AI telemetry (fire-and-forget)
        usage = result.get('usage', {})
        _send_telemetry(
            self.cabinet_id,
            'INFO',
            'AI_CALL',
            f'openai {model}: {latency_ms}ms',
            {
                'provider': 'openai',
                'model': model,
                'panel': panel or 'backend',
                'latency_ms': latency_ms,
                'input_tokens': usage.get('prompt_tokens'),
                'output_tokens': usage.get('completion_tokens')
            },
            panel or 'backend'
        )
        
        return result
    
    def call_elevenlabs(
        self,
        text: str,
        voice_id: str = "EXAVITQu4vr4xnSDxMaL",
        model_id: str = "eleven_monolingual_v1",
        voice_settings: Optional[Dict[str, float]] = None,
        panel: Optional[str] = None
    ) -> bytes:
        """
        Call ElevenLabs API through Supabase Edge Function.
        
        Args:
            text: Text to convert to speech
            voice_id: ElevenLabs voice ID
            model_id: ElevenLabs model ID
            voice_settings: Dict with 'stability' and 'similarity_boost'
            panel: Panel name (e.g., 'dewey', 'lora', 'vicky')
        
        Returns:
            Audio data as bytes (MP3 format)
        """
        url = f"{self.supabase_url}/functions/v1/elevenlabs-proxy"
        
        payload = {
            "text": text,
            "voice_id": voice_id,
            "model_id": model_id,
            "cabinet_id": self.cabinet_id,
            "tenant_id": self.tenant_id,
            "panel": panel
        }
        
        if voice_settings:
            payload["voice_settings"] = voice_settings
        
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60
        )
        
        response.raise_for_status()
        return response.content


# Example usage for testing
if __name__ == "__main__":
    print("Testing Secure AI Client...")
    
    try:
        client = SecureAIClient()
        
        # Test Anthropic
        print("\n1. Testing Anthropic...")
        response = client.call_anthropic(
            messages=[{"role": "user", "content": "Say hello in 5 words"}],
            panel="test"
        )
        print(f"Claude says: {response['content'][0]['text']}")
        
        # Test OpenAI
        print("\n2. Testing OpenAI...")
        response = client.call_openai(
            messages=[{"role": "user", "content": "Say hello in 5 words"}],
            model="gpt-4",
            panel="test"
        )
        print(f"GPT says: {response['choices'][0]['message']['content']}")
        
        # Test ElevenLabs
        print("\n3. Testing ElevenLabs...")
        audio_data = client.call_elevenlabs(
            text="Welcome to the arcade!",
            panel="test"
        )
        output_path = os.path.join(str(get_drive_root(allow_cwd_fallback=True, context="drive_a_ai_client TTS output")), "state", "audio", "welcome.mp3")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(audio_data)
        print(f"Audio saved to: {output_path}")
        
        print("\n\u2705 All tests passed!")
        
    except Exception as e:
        print(f"\n\u274c Error: {e}")
