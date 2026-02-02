# @agent: Echo
# @role: Mic input controller activated only by F9 keypress
# @activation: Manual only (no wake word)
# @linked_panels: DebugPanel (C3)

import threading
import time
import keyboard  # Uses `keyboard` library for F9 global hotkey
import speech_recognition as sr
from services.+logging.agent_log_writer import log_agent_event

LISTEN_DURATION = 10  # seconds

class EchoAgent:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.listening = False
        self.hotkey = "f9"
        self.mic_available = self._check_microphone()

    def _check_microphone(self):
        """Check if microphone is available and accessible"""
        try:
            with sr.Microphone() as source:
                return True
        except Exception as e:
            log_agent_event(f"Echo: Microphone check failed: {str(e)}")
            return False

    def start(self):
        """Initialize Echo agent and bind F9 hotkey"""
        if not self.mic_available:
            log_agent_event("Echo: Failed to initialize - microphone not available")
            return False

        try:
            log_agent_event("Echo initialized (F9 manual trigger)")
            keyboard.add_hotkey(self.hotkey, self._trigger_listen)
            log_agent_event("Echo listening for F9 to activate mic")
            return True
        except Exception as e:
            log_agent_event(f"Echo: Failed to bind F9 hotkey: {str(e)}")
            return False

    def _trigger_listen(self):
        """Handle F9 keypress to start voice recording"""
        if self.listening:
            log_agent_event("Echo already listening; ignored repeat F9")
            return

        self.listening = True
        log_agent_event("Echo: Mic activated via F9")

        # Run listening in separate thread to avoid blocking hotkey
        threading.Thread(target=self._listen_session, daemon=True).start()

    def _listen_session(self):
        """Execute voice recording and recognition session"""
        try:
            with sr.Microphone() as source:
                log_agent_event("Echo: Adjusting for ambient noise...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)

                log_agent_event(f"Echo: Listening for {LISTEN_DURATION}s...")
                audio = self.recognizer.listen(source, timeout=LISTEN_DURATION)

                log_agent_event("Echo: Processing audio...")
                # Use Google Web Speech API for recognition
                result = self.recognizer.recognize_google(audio)
                log_agent_event(f"Echo: Transcript: '{result}'")

                # TODO: Send transcript to appropriate handler
                self._handle_transcript(result)

        except sr.WaitTimeoutError:
            log_agent_event("Echo: No voice input detected (timeout)")
        except sr.RequestError as e:
            log_agent_event(f"Echo: Speech recognition service error: {str(e)}")
        except sr.UnknownValueError:
            log_agent_event("Echo: Could not understand audio")
        except Exception as e:
            log_agent_event(f"Echo: General mic error: {str(e)}")
        finally:
            self.listening = False
            log_agent_event("Echo: Mic session ended")

    def _handle_transcript(self, transcript: str):
        """Process recognized speech transcript"""
        # TODO: Integration point for voice commands
        # Could route to Claude, game commands, system controls, etc.
        log_agent_event(f"Echo: Ready to process command: '{transcript}'")

    def get_status(self):
        """Get current Echo agent status for DebugPanel"""
        if not self.mic_available:
            return "Mic Unavailable"
        elif self.listening:
            return "Listening"
        else:
            return "Ready (F9)"

    def stop(self):
        """Clean shutdown of Echo agent"""
        try:
            keyboard.remove_hotkey(self.hotkey)
            self.listening = False
            log_agent_event("Echo: Agent stopped, F9 hotkey removed")
        except Exception as e:
            log_agent_event(f"Echo: Error during shutdown: {str(e)}")

# Global instance for application use
echo_agent = EchoAgent()