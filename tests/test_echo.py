# @test: Echo Agent F9 Activation
# @goal: Ensure mic activates on F9 and logs transcript or failure

from services.+voice_core.echo import EchoAgent
import time
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_echo_agent():
    """Test Echo agent F9 activation and voice recognition"""
    print("🧪 Echo Test: Press F9 to activate mic input.")
    print("📝 All activity will be logged to logs/agent_calls/")
    print()

    try:
        echo = EchoAgent()

        if not echo.start():
            print("❌ Failed to initialize Echo agent")
            return False

        print(f"✅ Echo agent started successfully")
        print(f"🎤 Microphone status: {echo.get_status()}")
        print()
        print("📋 Test Instructions:")
        print("  1. Press F9 to activate voice input")
        print("  2. Speak clearly when you hear the activation")
        print("  3. Wait for transcription result")
        print("  4. Check logs/agent_calls/ for detailed logging")
        print()

        # Keep the program alive long enough to test keypress
        print("⏳ Waiting 60 seconds for input... Press Ctrl+C to exit.")

        start_time = time.time()
        while time.time() - start_time < 60:
            time.sleep(1)
            # Show status updates
            status = echo.get_status()
            if status != "Ready (F9)":
                print(f"🔄 Status: {status}")

        print("⏰ Test timeout reached")

    except KeyboardInterrupt:
        print("\n🛑 Test stopped manually.")
    except Exception as e:
        print(f"❌ Test error: {str(e)}")
        return False
    finally:
        try:
            echo.stop()
            print("🛑 Echo agent stopped")
        except:
            pass

    return True

def verify_requirements():
    """Check if required dependencies are available"""
    try:
        import keyboard
        import speech_recognition as sr
        print("✅ Required dependencies available")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("💡 Install with: pip install keyboard SpeechRecognition pyaudio")
        return False

if __name__ == "__main__":
    print("🎤 Echo Agent Test Suite")
    print("=" * 40)

    if not verify_requirements():
        sys.exit(1)

    success = test_echo_agent()

    print("\n" + "=" * 40)
    if success:
        print("✅ Test completed successfully")
        print("📁 Check logs/agent_calls/ for detailed activity logs")
    else:
        print("❌ Test failed")

    sys.exit(0 if success else 1)