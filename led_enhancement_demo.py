import time
import math

# This is a placeholder for the user's LEDWiz class.
# The user should replace this with their actual, working implementation.
class LEDWiz:
    """
    A placeholder for your working LEDWiz communication class.
    Your class should handle finding the device and writing data to it.
    """
    def __init__(self):
        print("INFO: Initializing placeholder for LEDWiz connection.")
        # Your real __init__ should find the device and get a handle to it.
        self.handle = True # Simulate a successful connection

    def write(self, data):
        """
        Your write method should take a list/tuple of bytes and send them.
        The first byte must be the Report ID (usually 0).
        """
        if self.handle:
            # This demo will print the first few bytes of the data being "sent".
            # In your real code, this would be the call to ctypes.windll.kernel32.WriteFile
            # print(f"DEBUG: Writing data: {data[:5]}...") # Uncomment for debugging
            pass
        else:
            print("WARN: LEDWiz not connected. Cannot write.")

    def close(self):
        print("INFO: Closing placeholder for LEDWiz connection.")
        if self.handle:
            # Your real close method should call CloseHandle.
            self.handle = False

def create_breathing_effect(ledwiz, led_output_index, duration_seconds, max_brightness=48, breathing_speed=2.5):
    """
    Generates a smooth "breathing" light effect on a specified LED output.

    This function directly addresses the "dim grain" issue by using the full
    brightness range of the LED-Wiz and a smooth sine wave for transitions.

    :param ledwiz: An initialized LEDWiz object with a `write` method.
    :param led_output_index: The LED output to animate (1-32).
    :param duration_seconds: How long the effect should run.
    :param max_brightness: The peak brightness for the effect.
                           For LED-Wiz, 48 is full brightness. Using a lower
                           value will make the effect dimmer.
    :param breathing_speed: Controls the speed of the breathing cycle. Larger numbers are faster.
    """
    if not (1 <= led_output_index <= 32):
        raise ValueError("LED output index must be between 1 and 32.")
    
    if not (1 <= max_brightness <= 48):
        print(f"WARNING: max_brightness is {max_brightness}, but the optimal range for LED-Wiz is 1-48. Clamping to this range.")
        max_brightness = max(1, min(48, max_brightness))

    start_time = time.time()
    
    # The LED-Wiz output report is 33 bytes long:
    # - Byte 0: Report ID (must be 0)
    # - Bytes 1-32: PWM value (0-48) for each of the 32 outputs.
    output_data = [0] * 33

    print(f"INFO: Starting breathing effect on LED output #{led_output_index} for {duration_seconds} seconds.")
    print(f"INFO: Peak brightness set to {max_brightness} (out of 48).")

    try:
        while time.time() - start_time < duration_seconds:
            elapsed_time = time.time() - start_time
            
            # Use a sine wave to create a smooth, organic pulse.
            # The value cycles between 0.0 and 1.0.
            sine_value = (math.sin(elapsed_time * breathing_speed) + 1) / 2
            
            # Scale the sine value to the desired brightness range.
            brightness = int(sine_value * max_brightness)
            
            # Set the brightness for the target LED.
            output_data[led_output_index] = brightness

            # Send the complete 33-byte report to the device.
            ledwiz.write(output_data)
            
            # Simple console visualization of the brightness
            print(f"Brightness: {brightness:2d} ({'#' * int(brightness / 48 * 20):<20})", end='\r')

            time.sleep(1/60) # Update at ~60Hz for a very smooth animation.

finally:
        # Ensure the LED is turned off when the effect is done or interrupted.
        print("\nINFO: Breathing effect finished. Turning off LED.")
        output_data[led_output_index] = 0
        ledwiz.write(output_data)


if __name__ == "__main__":
    my_ledwiz_device = None
    try:
        # --- IMPORTANT ---
        # Replace this placeholder with your actual LEDWiz class instance.
        my_ledwiz_device = LEDWiz()

        # --- DEMONSTRATION ---
        # This will run a 10-second breathing effect on LED output 5.
        # It uses the maximum brightness (48) to ensure a vivid, not "dim", effect.
        create_breathing_effect(
            ledwiz=my_ledwiz_device,
            led_output_index=5,
            duration_seconds=10,
            max_brightness=48, # Key to solving the "dim" issue!
            breathing_speed=2.0 # Adjust for faster/slower breathing
        )

    except Exception as e:
        print(f"\nERROR: An unexpected error occurred: {e}")
    finally:
        if my_ledwiz_device:
            my_ledwiz_device.close()
