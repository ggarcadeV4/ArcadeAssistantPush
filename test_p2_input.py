"""Quick diagnostic to test if Player 2 inputs are being detected."""
import pygame
import time

pygame.init()
pygame.joystick.init()

print("=== Player 2 Input Diagnostic ===")
print(f"Number of joysticks detected: {pygame.joystick.get_count()}")

if pygame.joystick.get_count() < 2:
    print("⚠️  WARNING: Less than 2 joysticks detected!")
    print("   Player 2 requires a second joystick (JS1)")
else:
    print("✅ Multiple joysticks detected - Player 2 should work")

# Initialize all joysticks
joysticks = []
for i in range(pygame.joystick.get_count()):
    js = pygame.joystick.Joystick(i)
    js.init()
    joysticks.append(js)
    print(f"\nJoystick {i}: {js.get_name()}")
    print(f"  - Buttons: {js.get_numbuttons()}")
    print(f"  - Axes: {js.get_numaxes()}")
    print(f"  - Hats: {js.get_numhats()}")

if len(joysticks) >= 2:
    print("\n" + "="*50)
    print("NOW TEST PLAYER 2 CONTROLS:")
    print("  - Press any button or move joystick on Player 2 controller")
    print("  - Watch for 'JS1' in the output (that's Player 2)")
    print("  - Press Ctrl+C to exit")
    print("="*50 + "\n")

    try:
        while True:
            pygame.event.pump()

            # Check Joystick 1 (Player 2)
            js = joysticks[1]

            # Check buttons
            for btn_idx in range(js.get_numbuttons()):
                if js.get_button(btn_idx):
                    print(f"✅ P2 BUTTON DETECTED: BTN_{btn_idx}_JS1")
                    time.sleep(0.2)  # Debounce

            # Check axes
            for axis_idx in range(js.get_numaxes()):
                value = js.get_axis(axis_idx)
                if abs(value) > 0.5:
                    direction = "+" if value > 0 else "-"
                    print(f"✅ P2 AXIS DETECTED: AXIS_{axis_idx}{direction}_JS1 (value={value:.2f})")
                    time.sleep(0.2)

            # Check hats
            for hat_idx in range(js.get_numhats()):
                hat = js.get_hat(hat_idx)
                if hat != (0, 0):
                    x, y = hat
                    if y == 1:
                        print(f"✅ P2 DPAD DETECTED: DPAD_UP_JS1")
                    elif y == -1:
                        print(f"✅ P2 DPAD DETECTED: DPAD_DOWN_JS1")
                    elif x == -1:
                        print(f"✅ P2 DPAD DETECTED: DPAD_LEFT_JS1")
                    elif x == 1:
                        print(f"✅ P2 DPAD DETECTED: DPAD_RIGHT_JS1")
                    time.sleep(0.2)

            time.sleep(0.05)  # Small delay
    except KeyboardInterrupt:
        print("\n\nDiagnostic complete!")
else:
    print("\n⚠️  Cannot test Player 2 - need at least 2 joysticks")
    print("   Make sure your P2 controller is connected!")

pygame.quit()
