
import ctypes
import os
import time

# --- Configuration ---
DLL_PATH = r"C:\LEDBlinky\ledwiz.dll"
DEVICE_ID = 1 # As per documentation, device IDs start at 1

def run_test():
    """
    Loads the ledwiz.dll, registers the device, and attempts to light an LED.
    """
    print("--- LED-Wiz Diagnostic Script ---")

    if not os.path.exists(DLL_PATH):
        print(f"ERROR: DLL not found at path: {DLL_PATH}")
        return

    # --- 1. Load DLL ---
    try:
        # Use WinDLL for stdcall convention, common in Windows APIs
        ledwiz = ctypes.WinDLL(DLL_PATH)
        print(f"SUCCESS: Loaded {DLL_PATH}")
    except OSError as e:
        print(f"ERROR: Failed to load DLL. Check architecture (32-bit Python required).")
        print(f"Details: {e}")
        return

    # --- 2. Define Function Signatures (argtypes and restype) ---
    try:
        # int LWZ_REGISTER(HWND hwnd, void* callback);
        ledwiz.LWZ_REGISTER.restype = ctypes.c_int
        ledwiz.LWZ_REGISTER.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        # void LWZ_SBA(int id, int b0, int b1, int b2, int b3, int speed, int u1, int u2);
        ledwiz.LWZ_SBA.restype = None
        ledwiz.LWZ_SBA.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        
        print("SUCCESS: Defined function signatures for LWZ_REGISTER and LWZ_SBA.")

    except AttributeError as e:
        print(f"ERROR: A function was not found in the DLL. Is it the correct DLL?")
        print(f"Details: {e}")
        return

    # --- 3. Register Device ---
    print("\nAttempting to register device...")
    # We pass 0 for both hwnd and callback, as we don't need window handles or callbacks.
    device_count = ledwiz.LWZ_REGISTER(0, 0)

    print(f"INFO: LWZ_REGISTER returned: {device_count}")

    if device_count > 0:
        print(f"SUCCESS: Detected {device_count} LED-Wiz device(s).")
    else:
        print("ERROR: No LED-Wiz devices detected. Halting.")
        return

    # --- 4. Call SBA to light an LED ---
    # We will try to light up the first button (Port 1, Bit 0)
    # The bitmask for the first 8 ports is in the 'b0' argument.
    # To turn on the first light, we set the first bit of b0 to 1.
    b0_mask = 1  # Binary 00000001
    
    print(f"\nAttempting to call LWZ_SBA for device {DEVICE_ID}...")
    print(f"Parameters: id={DEVICE_ID}, b0={b0_mask}, b1=0, b2=0, b3=0, speed=255, u1=0, u2=0")

    try:
        # Call with full power (speed=255) and no fade timers (u1, u2 = 0)
        ledwiz.LWZ_SBA(DEVICE_ID, b0_mask, 0, 0, 0, 255, 0, 0)
        print("SUCCESS: LWZ_SBA called. Check if LED 1 is lit.")

        # Keep the LED on for a few seconds before turning it off
        time.sleep(3)

        print("\nAttempting to turn off all LEDs...")
        ledwiz.LWZ_SBA(DEVICE_ID, 0, 0, 0, 0, 255, 0, 0)
        print("SUCCESS: LWZ_SBA called with all-zero mask. LEDs should be off.")

    except Exception as e:
        print(f"ERROR: An exception occurred during the LWZ_SBA call.")
        print(f"Details: {e}")

    print("\n--- Test Complete ---")


if __name__ == "__main__":
    run_test()
