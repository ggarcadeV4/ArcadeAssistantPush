/**
 * LED-Wiz Helper - Command-line tool that uses official LEDWiz32.dll
 * 
 * This program bridges Python (which has HID issues) to the official DLL.
 * It reads JSON commands from stdin and outputs results to stdout.
 * 
 * Build: cl ledwiz_helper.cpp /Fe:ledwiz_helper.exe
 * Or:    g++ ledwiz_helper.cpp -o ledwiz_helper.exe
 * 
 * Usage:
 *   echo {"cmd":"sba","banks":[255,0,0,0],"speed":2} | ledwiz_helper.exe
 *   echo {"cmd":"pba","values":[48,48,48,48,0,0,0,0,...]} | ledwiz_helper.exe
 *   echo {"cmd":"all_on"} | ledwiz_helper.exe
 *   echo {"cmd":"all_off"} | ledwiz_helper.exe
 *   echo {"cmd":"channel_on","channel":0} | ledwiz_helper.exe
 */

#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

// LEDWiz DLL function typedefs
typedef void (__stdcall *LWZ_SBA_t)(int id, int bank0, int bank1, int bank2, int bank3, int speed, int unused1, int unused2);
typedef void (__stdcall *LWZ_PBA_t)(int id, unsigned char* brightness);
typedef int (__stdcall *LWZ_REGISTER_t)(void* hwnd, void* notifyFunc);
typedef void (__stdcall *LWZ_SET_t)(int id, int bankNumber, unsigned char* settings);

// Global DLL handles
HMODULE hLedwizDll = NULL;
LWZ_SBA_t pLWZ_SBA = NULL;
LWZ_PBA_t pLWZ_PBA = NULL;
LWZ_REGISTER_t pLWZ_REGISTER = NULL;

// Device ID (1 = first LED-Wiz, can be 1-16)
int deviceId = 1;

bool LoadLedwizDll() {
    // Try multiple paths for the DLL
    const char* paths[] = {
        "LEDWiz.dll",
        "ledwiz.dll",
        "LEDWiz32.dll",
        "C:\\LEDBlinky\\LEDWiz.dll",
        NULL
    };
    
    for (int i = 0; paths[i] != NULL; i++) {
        hLedwizDll = LoadLibraryA(paths[i]);
        if (hLedwizDll) {
            fprintf(stderr, "[ledwiz_helper] Loaded DLL from: %s\n", paths[i]);
            break;
        }
    }
    
    if (!hLedwizDll) {
        fprintf(stderr, "[ledwiz_helper] ERROR: Could not load LEDWiz.dll\n");
        return false;
    }
    
    // Get function pointers
    pLWZ_SBA = (LWZ_SBA_t)GetProcAddress(hLedwizDll, "LWZ_SBA");
    pLWZ_PBA = (LWZ_PBA_t)GetProcAddress(hLedwizDll, "LWZ_PBA");
    pLWZ_REGISTER = (LWZ_REGISTER_t)GetProcAddress(hLedwizDll, "LWZ_REGISTER");
    
    if (!pLWZ_SBA || !pLWZ_PBA) {
        fprintf(stderr, "[ledwiz_helper] ERROR: Could not get function pointers from DLL\n");
        return false;
    }
    
    // Register with DLL (required before use)
    if (pLWZ_REGISTER) {
        pLWZ_REGISTER(NULL, NULL);
        fprintf(stderr, "[ledwiz_helper] Registered with LWZ_REGISTER\n");
    }
    
    return true;
}

void SendSBA(int bank0, int bank1, int bank2, int bank3, int speed) {
    if (pLWZ_SBA) {
        pLWZ_SBA(deviceId, bank0, bank1, bank2, bank3, speed, 0, 0);
        fprintf(stderr, "[ledwiz_helper] SBA sent: banks=[%d,%d,%d,%d] speed=%d\n", 
                bank0, bank1, bank2, bank3, speed);
    }
}

void SendPBA(unsigned char* brightness) {
    if (pLWZ_PBA) {
        pLWZ_PBA(deviceId, brightness);
        fprintf(stderr, "[ledwiz_helper] PBA sent: first 8 values=[%d,%d,%d,%d,%d,%d,%d,%d]\n",
                brightness[0], brightness[1], brightness[2], brightness[3],
                brightness[4], brightness[5], brightness[6], brightness[7]);
    }
}

void AllOn() {
    // Turn all 32 outputs ON
    SendSBA(255, 255, 255, 255, 2);
    
    // Set all to max brightness (49 = solid on)
    unsigned char brightness[32];
    for (int i = 0; i < 32; i++) brightness[i] = 49;
    SendPBA(brightness);
    
    printf("{\"status\":\"ok\",\"action\":\"all_on\"}\n");
}

void AllOff() {
    // Turn all 32 outputs OFF
    SendSBA(0, 0, 0, 0, 2);
    printf("{\"status\":\"ok\",\"action\":\"all_off\"}\n");
}

void ChannelOn(int channel, int brightness_val) {
    if (channel < 0 || channel >= 32) {
        printf("{\"status\":\"error\",\"message\":\"channel out of range\"}\n");
        return;
    }
    
    // Calculate which bank and bit
    int bank0 = 0, bank1 = 0, bank2 = 0, bank3 = 0;
    if (channel < 8) bank0 = (1 << channel);
    else if (channel < 16) bank1 = (1 << (channel - 8));
    else if (channel < 24) bank2 = (1 << (channel - 16));
    else bank3 = (1 << (channel - 24));
    
    // Turn on the specific output
    SendSBA(bank0, bank1, bank2, bank3, 2);
    
    // Set brightness (value 1-49, 49 = max)
    unsigned char brightness[32] = {0};
    brightness[channel] = (unsigned char)(brightness_val > 0 ? brightness_val : 49);
    SendPBA(brightness);
    
    printf("{\"status\":\"ok\",\"action\":\"channel_on\",\"channel\":%d}\n", channel);
}

void ChannelOff(int channel) {
    // Turn off by sending SBA with that bit cleared
    SendSBA(0, 0, 0, 0, 2);
    printf("{\"status\":\"ok\",\"action\":\"channel_off\",\"channel\":%d}\n", channel);
}

// Simple JSON parsing (minimal, no external libs)
int ParseInt(const char* json, const char* key, int defaultVal) {
    char searchKey[64];
    snprintf(searchKey, sizeof(searchKey), "\"%s\":", key);
    const char* pos = strstr(json, searchKey);
    if (!pos) return defaultVal;
    pos += strlen(searchKey);
    while (*pos == ' ') pos++;
    return atoi(pos);
}

bool ParseCommand(const char* json, char* cmd, int cmdSize) {
    const char* pos = strstr(json, "\"cmd\":");
    if (!pos) return false;
    pos += 6;
    while (*pos == ' ' || *pos == '"') pos++;
    int i = 0;
    while (*pos && *pos != '"' && i < cmdSize - 1) {
        cmd[i++] = *pos++;
    }
    cmd[i] = '\0';
    return true;
}

int main(int argc, char* argv[]) {
    fprintf(stderr, "[ledwiz_helper] Starting...\n");
    
    if (!LoadLedwizDll()) {
        printf("{\"status\":\"error\",\"message\":\"failed to load LEDWiz.dll\"}\n");
        return 1;
    }
    
    // Read command from stdin
    char buffer[4096] = {0};
    if (fgets(buffer, sizeof(buffer), stdin) == NULL) {
        printf("{\"status\":\"error\",\"message\":\"no input\"}\n");
        return 1;
    }
    
    fprintf(stderr, "[ledwiz_helper] Received: %s\n", buffer);
    
    char cmd[64] = {0};
    if (!ParseCommand(buffer, cmd, sizeof(cmd))) {
        printf("{\"status\":\"error\",\"message\":\"missing cmd field\"}\n");
        return 1;
    }
    
    if (strcmp(cmd, "all_on") == 0) {
        AllOn();
    } else if (strcmp(cmd, "all_off") == 0) {
        AllOff();
    } else if (strcmp(cmd, "channel_on") == 0) {
        int channel = ParseInt(buffer, "channel", 0);
        int brightness = ParseInt(buffer, "brightness", 49);
        ChannelOn(channel, brightness);
    } else if (strcmp(cmd, "channel_off") == 0) {
        int channel = ParseInt(buffer, "channel", 0);
        ChannelOff(channel);
    } else {
        printf("{\"status\":\"error\",\"message\":\"unknown command: %s\"}\n", cmd);
        return 1;
    }
    
    // Cleanup
    if (hLedwizDll) FreeLibrary(hLedwizDll);
    
    return 0;
}
