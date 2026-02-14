# LED-Wiz HID Bridge (CLI + DLL)

This is a minimal C++ HID bridge for LED-Wiz devices. It provides:

- A CLI for enumeration and quick testing (`ledwiz_bridge.exe`)
- A DLL with a stable C ABI for Python `ctypes` (`ledwiz_bridge.dll`)

## Build (MSVC)

Open a Developer PowerShell for VS and run:

```powershell
cd A:\Arcade Assistant Local\tools\ledwiz_bridge

# CLI
cl /nologo /EHsc /std:c++17 /DLEDWIZ_BRIDGE_CLI /Fe:ledwiz_bridge.exe ledwiz_bridge.cpp /link setupapi.lib hid.lib

# DLL
cl /nologo /EHsc /std:c++17 /DLEDWIZ_BRIDGE_EXPORTS /LD /Fe:ledwiz_bridge.dll ledwiz_bridge.cpp /link setupapi.lib hid.lib
```

Copy the DLL to `A:\Tools\LEDBlinky\`:

```powershell
Copy-Item .\ledwiz_bridge.dll A:\Tools\LEDBlinky\
```

## Build (MSYS2 / MinGW-w64)

If MSVC isn't available, MSYS2 works and produces a standalone CLI/DLL
that depend on MinGW runtime DLLs.

```powershell
# Install MSYS2
winget install --id MSYS2.MSYS2 -e

# Install MinGW-w64 toolchain
C:\msys64\msys2_shell.cmd -mingw64 -lc "pacman -S --noconfirm mingw-w64-x86_64-gcc"

# Build (CLI + DLL)
C:\msys64\msys2_shell.cmd -mingw64 -lc "cd '/a/Arcade Assistant Local/tools/ledwiz_bridge' && g++ -std=c++17 -DLEDWIZ_BRIDGE_CLI -o ledwiz_bridge.exe ledwiz_bridge.cpp -lsetupapi -lhid"
C:\msys64\msys2_shell.cmd -mingw64 -lc "cd '/a/Arcade Assistant Local/tools/ledwiz_bridge' && g++ -std=c++17 -DLEDWIZ_BRIDGE_EXPORTS -shared -o ledwiz_bridge.dll ledwiz_bridge.cpp -lsetupapi -lhid"
```

MinGW runtime DLLs required (place alongside `ledwiz_bridge.exe` / `ledwiz_bridge.dll`):

- `libstdc++-6.dll`
- `libgcc_s_seh-1.dll`
- `libwinpthread-1.dll`

## CLI Usage

```powershell
ledwiz_bridge.exe list
ledwiz_bridge.exe set 1 48
ledwiz_bridge.exe alloff
```

CLI outputs JSON on success/error.

## DLL Usage (Python ctypes)

```python
from ctypes import cdll, c_int, c_bool

ledwiz = cdll.LoadLibrary("A:/Tools/LEDBlinky/ledwiz_bridge.dll")
ledwiz.LED_Init.restype = c_bool
ledwiz.LED_SetPort.restype = c_bool
ledwiz.LED_AllOff.restype = c_bool
ledwiz.LED_GetBoardCount.restype = c_int

ledwiz.LED_Init()
ledwiz.LED_SetPort(1, 48)
ledwiz.LED_AllOff()
ledwiz.LED_Close()
```

## Notes

- Ports are 1-based. Port 1-32 = board 0, 33-64 = board 1, etc.
- Intensity range is 0-48 (0 = off).
- Devices are ordered by product ID (PID) ascending, then path.
