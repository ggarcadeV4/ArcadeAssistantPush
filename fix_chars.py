from PIL import Image
import numpy as np
import os

src = os.path.join(os.path.expanduser("~"), ".gemini", "antigravity", "brain", 
                   "bbdfccc0-4772-4992-bf91-0fca5395aaf2")
d = r"A:\Arcade Assistant Local\frontend\public\characters"

mapping = {
    "media__1771311174194.jpg": "doc-char.png",
    "media__1771311205749.jpg": "gunner-char.png",
    "media__1771311225642.jpg": "blinky-char.png",
    "media__1771311242250.jpg": "wizard-char.png",
    "media__1771311261087.jpg": "dewey-char.png",
    "media__1771311292814.jpg": "chuck-char.png",
    "media__1771311314103.jpg": "vicki-char.png",
    "media__1771311329891.jpg": "sam-char.png",
    "media__1771311367217.jpg": "lora-char.png",
}

bg = np.array([15, 23, 42])

for src_name, dst_name in mapping.items():
    img = np.array(Image.open(os.path.join(src, src_name)).convert("RGB")).astype(float)
    # Grayscale check: R,G,B all within 30 of each other AND brightness > 100
    spread = np.max(img, axis=2) - np.min(img, axis=2)
    brightness = np.mean(img, axis=2)
    mask = (spread < 30) & (brightness > 100)
    img[mask] = bg
    Image.fromarray(img.astype(np.uint8)).save(os.path.join(d, dst_name))
    print(f"Fixed: {dst_name}")

print("All done!")
