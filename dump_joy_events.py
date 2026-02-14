# Dump raw pygame joystick events for 30 seconds
# Run this and press D-pad Up - it will show exactly what event type fires
import pygame
import time
import sys

sys.stdout = sys.stderr  # Force unbuffered output

pygame.init()
pygame.joystick.init()

count = pygame.joystick.get_count()
print(f"Found {count} joysticks")

if count == 0:
    print("No joysticks found!")
    sys.exit(1)

# Initialize all joysticks
joysticks = []
for i in range(count):
    js = pygame.joystick.Joystick(i)
    js.init()
    joysticks.append(js)
    print(f"  [{i}] {js.get_name()}: buttons={js.get_numbuttons()}, axes={js.get_numaxes()}, hats={js.get_numhats()}")

print()
print("=" * 60)
print("RAW EVENT DUMP - Press D-pad Up (or any input) now!")
print("Watching for 30 seconds...")
print("=" * 60)
print()

start = time.time()
while time.time() - start < 30:
    pygame.event.pump()
    
    for ev in pygame.event.get():
        if ev.type == pygame.JOYAXISMOTION:
            print(f"JOYAXISMOTION: joy={ev.joy} axis={ev.axis} value={ev.value:.4f}")
        elif ev.type == pygame.JOYBUTTONDOWN:
            print(f"JOYBUTTONDOWN: joy={ev.joy} button={ev.button}")
        elif ev.type == pygame.JOYBUTTONUP:
            print(f"JOYBUTTONUP: joy={ev.joy} button={ev.button}")
        elif ev.type == pygame.JOYHATMOTION:
            print(f"JOYHATMOTION: joy={ev.joy} hat={ev.hat} value={ev.value}")
        elif ev.type == pygame.JOYDEVICEADDED:
            print(f"JOYDEVICEADDED: device_index={ev.device_index}")
        elif ev.type == pygame.JOYDEVICEREMOVED:
            print(f"JOYDEVICEREMOVED: instance_id={ev.instance_id}")
        else:
            # Any other joy event
            if hasattr(ev, 'joy'):
                print(f"OTHER JOY EVENT: type={ev.type} ev={ev}")
    
    time.sleep(0.01)

print()
print("Done! Copy the event lines above and paste them.")
pygame.quit()
