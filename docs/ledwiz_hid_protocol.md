# LED-Wiz HID Protocol (Reference)

This document summarizes the LED-Wiz USB HID protocol used by the bridge.

## Device IDs

- VID: `0xFAFA`
- PID: `0x00F0` (device 1), `0x00F1` (device 2), `0x00F2` (device 3), ...
- LED-Wiz uses sequential PIDs to represent multiple boards.

## HID Report

- Output report length: typically 9 bytes
- Report ID: `0x00` (first byte of every report)

## SBA (Set Bank Address)

Turns outputs ON/OFF via bitmasks per bank of 8.

```
Byte 0: Report ID (0x00)
Byte 1: Bank 0 (outputs 1-8)   bitmask
Byte 2: Bank 1 (outputs 9-16)  bitmask
Byte 3: Bank 2 (outputs 17-24) bitmask
Byte 4: Bank 3 (outputs 25-32) bitmask
Byte 5: Pulse speed (1-7)      (use 2 for steady on)
Byte 6: 0x00
Byte 7: 0x00
Byte 8: 0x00
```

Example: turn on port 1 only

```
00 01 00 00 00 02 00 00 00
```

## PBA (Profile Brightness Address)

Sets brightness for outputs in 4 chunks of 8.

```
Byte 0: Report ID (0x00)
Byte 1: Command marker (0x40 + chunk index)
Byte 2..9: 8 brightness values (0-48)
```

Chunk indices:

- `0x40` = outputs 1-8
- `0x41` = outputs 9-16
- `0x42` = outputs 17-24
- `0x43` = outputs 25-32

Brightness:

- `0` = off
- `1..48` = PWM brightness

## Multi-Board Addressing

Boards are addressed by device index rather than packet content.
To target a specific board, open the corresponding HID device path
(PID order ascending) and send SBA/PBA to that handle.

## Timing Notes

- Send SBA first, then all 4 PBA chunks.
- Allow ~10ms between frames if doing rapid updates to avoid HID saturation.
