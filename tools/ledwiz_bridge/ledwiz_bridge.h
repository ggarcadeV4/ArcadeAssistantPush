#pragma once

#include <stdbool.h>

#ifdef _WIN32
#  ifdef LEDWIZ_BRIDGE_EXPORTS
#    define LEDWIZ_BRIDGE_API __declspec(dllexport)
#  elif defined(LEDWIZ_BRIDGE_CLI)
#    define LEDWIZ_BRIDGE_API
#  else
#    define LEDWIZ_BRIDGE_API __declspec(dllimport)
#  endif
#else
#  define LEDWIZ_BRIDGE_API
#endif

extern "C" {

// Initialize and open all detected LED-Wiz devices.
LEDWIZ_BRIDGE_API bool LED_Init();

// Set a 1-based global port to intensity (0-48).
// Port 1-32 -> board 0, 33-64 -> board 1, etc.
LEDWIZ_BRIDGE_API bool LED_SetPort(int port, int intensity);

// Turn all ports off on all boards.
LEDWIZ_BRIDGE_API bool LED_AllOff();

// Get number of detected boards after LED_Init.
LEDWIZ_BRIDGE_API int LED_GetBoardCount();

// Close device handles and release resources.
LEDWIZ_BRIDGE_API void LED_Close();

// Optional error helpers.
LEDWIZ_BRIDGE_API int LED_GetLastErrorCode();
LEDWIZ_BRIDGE_API const char* LED_GetLastError();

}
