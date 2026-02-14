"""Test script for gamepad detection using pygame (MULTI-JOYSTICK)."""
import pygame
import time
import sys

# Force unbuffered output
sys.stdout = sys.stderr

print("Initializing Pygame...")
pygame.init()
pygame.joystick.init()

count = pygame.joystick.get_count()
print(f"Found {count} joysticks")

if count == 0:
    print("No joysticks found!")
    sys.exit(1)

joysticks = []
for i in range(count):
    js = pygame.joystick.Joystick(i)
    js.init()
    joysticks.append(js)
    print(f"Joystick {i}: {js.get_name()}")
    print(f"  Buttons: {js.get_numbuttons()}")
    print(f"  Axes: {js.get_numaxes()}")
    print(f"  Hats: {js.get_numhats()}")

print()
print("=" * 60)
print("PRESS P1 and P2 BUTTONS NOW! (Monitoring all joysticks)")
print("Monitoring for 15 seconds...")
print("=" * 60)

start = time.time()
while time.time() - start < 15:
    pygame.event.pump()
    
    for i, js in enumerate(joysticks):
        # Check all buttons
        for b in range(js.get_numbuttons()):
            if js.get_button(b):
                print(f"JS{i} >>> BUTTON {b} PRESSED!")
        
        # Check all axes
        for a in range(js.get_numaxes()):
            val = js.get_axis(a)
            if abs(val) > 0.5:
                direction = "+" if val > 0 else "-"
                print(f"JS{i} >>> AXIS {a} {direction} (value: {val:.2f})")
        
        # Check all hats (d-pad)
        for h in range(js.get_numhats()):
            hat = js.get_hat(h)
            if hat != (0, 0):
                print(f"JS{i} >>> HAT {h}: {hat}")
    
    time.sleep(0.05)

print("\nDone! No more monitoring.")
pygame.quit()
