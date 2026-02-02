"""
Quick diagnostic script to verify pygame joystick detection.
Based on computer scientist review - checking for Twinstick mode or hardware issues.
"""
import pygame
import time

pygame.init()
pygame.joystick.init()

print("=" * 80)
print("JOYSTICK DETECTION DIAGNOSTIC")
print("=" * 80)

joystick_count = pygame.joystick.get_count()
print(f"\n✓ Pygame detected {joystick_count} joystick(s)")

if joystick_count == 0:
    print("\n❌ NO JOYSTICKS DETECTED - Check hardware connections!")
    exit(1)

# Initialize all joysticks
sticks = []
for i in range(joystick_count):
    js = pygame.joystick.Joystick(i)
    js.init()

    # Get instance ID (pygame 2.x)
    inst = js.get_instance_id() if hasattr(js, "get_instance_id") else "N/A"
    guid = js.get_guid() if hasattr(js, "get_guid") else "N/A"

    print(f"\n--- Joystick {i} ---")
    print(f"  Name: {js.get_name()}")
    print(f"  Instance ID: {inst}")
    print(f"  GUID: {guid}")
    print(f"  Buttons: {js.get_numbuttons()}")
    print(f"  Axes: {js.get_numaxes()}")
    print(f"  Hats: {js.get_numhats()}")

    sticks.append(js)

print("\n" + "=" * 80)
print("HARDWARE EXPECTATIONS:")
print("=" * 80)
print("✓ 2× PactoTech-2000T boards → Should see 4 controllers (each board = 2 players)")
print(f"✓ Currently detected: {joystick_count} controllers")

if joystick_count == 2:
    print("\n⚠️  WARNING: Only 2 controllers detected!")
    print("   Possible causes:")
    print("   1. Only 1 PactoTech board connected (not 2)")
    print("   2. Second board in TWINSTICK MODE (P2 merged into P1)")
    print("   3. Second board not powered/connected")
elif joystick_count == 4:
    print("\n✓ All 4 controllers detected - hardware looks good!")

print("\n" + "=" * 80)
print("EVENT LISTENING TEST")
print("=" * 80)
print("Press any button on Player 2 control panel...")
print("(Ctrl+C to quit)")
print("=" * 80)

start_time = time.time()
p2_detected = False

while time.time() - start_time < 30:  # 30 second timeout
    # CRITICAL: Must pump events for joystick state to update
    for event in pygame.event.get():
        if event.type == pygame.JOYBUTTONDOWN:
            print(f"\n✓ BUTTON PRESS: {event.__dict__}")

            # Check if this is joystick index 1 (Player 2)
            joy_id = getattr(event, 'joy', None) or getattr(event, 'instance_id', None)
            if joy_id == 1:
                p2_detected = True
                print("   ^^^ THIS IS PLAYER 2 (JS1) ^^^")
            elif joy_id == 0:
                print("   ^^^ This is Player 1 (JS0) - try P2 instead ^^^")

        elif event.type == pygame.JOYAXISMOTION:
            if abs(getattr(event, "value", 0)) > 0.4:
                joy_id = getattr(event, 'joy', None) or getattr(event, 'instance_id', None)
                print(f"\n✓ AXIS MOTION: joy={joy_id}, axis={event.axis}, value={event.value:.2f}")

        elif event.type == pygame.JOYHATMOTION:
            joy_id = getattr(event, 'joy', None) or getattr(event, 'instance_id', None)
            print(f"\n✓ HAT MOTION: joy={joy_id}, hat={event.hat}, value={event.value}")

    time.sleep(0.01)

print("\n" + "=" * 80)
print("TEST RESULTS:")
print("=" * 80)

if p2_detected:
    print("✓ Player 2 (JS1) events DETECTED - pygame is working!")
    print("  → Issue is in mapping/normalization layer")
else:
    print("❌ Player 2 (JS1) events NOT detected")
    print("  → Hardware issue or Twinstick mode enabled")
    print("\nTo disable Twinstick mode on PactoTech:")
    print("  1. Unplug USB")
    print("  2. Hold P1 START + P1 BUTTON 2 (not BUTTON 1!)")
    print("  3. Plug USB back in while holding")
    print("  4. Release after 3 seconds")

pygame.quit()
