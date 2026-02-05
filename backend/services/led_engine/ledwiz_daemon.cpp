#include <windows.h>
#include <setupapi.h>
#include <iostream>
#include <vector>
#include <string>
#include <sstream>

// HID headers (usually from Windows DDK/SDK)
extern "C" {
#include <hidsdi.h>
}

#pragma comment(lib, "setupapi.lib")
#pragma comment(lib, "hid.lib")

#define PIPE_NAME "\\\\.\\pipe\\ArcadeLED"
#define BUFFER_SIZE 1024

struct LEDWizBoard {
    HANDLE hDevice;
    int unitId;
    int pid;
    std::string path;
};

std::vector<LEDWizBoard> g_boards;

void Log(const std::string& msg) {
    std::cerr << "[LEDWizDaemon] " << msg << std::endl;
}

void CloseBoards() {
    for (auto& board : g_boards) {
        if (board.hDevice != INVALID_HANDLE_VALUE) {
            CloseHandle(board.hDevice);
        }
    }
    g_boards.clear();
}

bool DiscoverBoards() {
    CloseBoards();
    Log("Discovering LED-Wiz boards...");

    GUID hidGuid;
    HidD_GetHidGuid(&hidGuid);

    HDEVINFO deviceInfoSet = SetupDiGetClassDevs(&hidGuid, NULL, NULL, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
    if (deviceInfoSet == INVALID_HANDLE_VALUE) return false;

    SP_DEVICE_INTERFACE_DATA interfaceData;
    interfaceData.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA);

    for (DWORD i = 0; SetupDiEnumDeviceInterfaces(deviceInfoSet, NULL, &hidGuid, i, &interfaceData); i++) {
        DWORD detailSize = 0;
        SetupDiGetDeviceInterfaceDetail(deviceInfoSet, &interfaceData, NULL, 0, &detailSize, NULL);

        SP_DEVICE_INTERFACE_DETAIL_DATA* detailData = (SP_DEVICE_INTERFACE_DETAIL_DATA*)malloc(detailSize);
        detailData->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA);

        if (SetupDiGetDeviceInterfaceDetail(deviceInfoSet, &interfaceData, detailData, detailSize, NULL, NULL)) {
            HANDLE hTemp = CreateFile(detailData->DevicePath, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
            if (hTemp != INVALID_HANDLE_VALUE) {
                HIDD_ATTRIBUTES attr;
                attr.Size = sizeof(HIDD_ATTRIBUTES);
                if (HidD_GetAttributes(hTemp, &attr)) {
                    bool match = false;
                    int unitId = -1;

                    // LED-Wiz Emulation (0xFAFA:0x00F0-0x00FF)
                    if (attr.VendorID == 0xFAFA && attr.ProductID >= 0x00F0 && attr.ProductID <= 0x00FF) {
                        unitId = attr.ProductID - 0x00EF;
                        match = true;
                    }
                    // Pinscape (0xFAFA:0xEAEA)
                    else if (attr.VendorID == 0xFAFA && attr.ProductID == 0xEAEA) {
                        unitId = 1; // Default to 1 for Pinscape or parse serial
                        match = true;
                    }

                    if (match) {
                        // Re-open with write access
                        CloseHandle(hTemp);
                        HANDLE hDevice = CreateFile(detailData->DevicePath, GENERIC_WRITE | GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
                        if (hDevice != INVALID_HANDLE_VALUE) {
                            LEDWizBoard board;
                            board.hDevice = hDevice;
                            board.unitId = unitId;
                            board.pid = attr.ProductID;
                            board.path = detailData->DevicePath;
                            g_boards.push_back(board);
                            Log("Found LED-Wiz Board: Unit " + std::to_string(unitId) + " (PID: 0x" + std::to_string(attr.ProductID) + ")");
                        }
                    } else {
                        CloseHandle(hTemp);
                    }
                } else {
                    CloseHandle(hTemp);
                }
            }
        }
        free(detailData);
    }
    SetupDiDestroyDeviceInfoList(deviceInfoSet);
    return !g_boards.empty();
}

void SendSBA(int boardIdx, int b0, int b1, int b2, int b3, int speed) {
    if (boardIdx < 0 || boardIdx >= g_boards.size()) return;
    unsigned char report[9] = { 0x00, (unsigned char)b0, (unsigned char)b1, (unsigned char)b2, (unsigned char)b3, (unsigned char)speed, 0, 0, 0 };
    DWORD written;
    WriteFile(g_boards[boardIdx].hDevice, report, 9, &written, NULL);
}

void SendPBA(int boardIdx, int chunk, unsigned char* brightness) {
    if (boardIdx < 0 || boardIdx >= g_boards.size()) return;
    unsigned char report[9] = { 0x00, (unsigned char)(0x40 + chunk),
                                brightness[0], brightness[1], brightness[2], brightness[3],
                                brightness[4], brightness[5], brightness[6], brightness[7] };
    DWORD written;
    WriteFile(g_boards[boardIdx].hDevice, report, 9, &written, NULL);
}

void HandleCommand(const std::string& cmd) {
    std::stringstream ss(cmd);
    std::string action;
    ss >> action;

    if (action == "SBA") {
        int board, b0, b1, b2, b3, speed;
        ss >> board >> b0 >> b1 >> b2 >> b3 >> speed;
        SendSBA(board - 1, b0, b1, b2, b3, speed);
    } else if (action == "PBA_CHUNK") {
        int board, chunk;
        ss >> board >> chunk;
        unsigned char brightness[8];
        for (int i = 0; i < 8; i++) {
            int val;
            ss >> val;
            brightness[i] = (unsigned char)val;
        }
        SendPBA(board - 1, chunk, brightness);
    } else if (action == "DISCOVER") {
        DiscoverBoards();
    } else if (action == "ALL_OFF") {
        for (int i = 0; i < g_boards.size(); i++) {
            SendSBA(i, 0, 0, 0, 0, 2);
        }
    }
}

int main() {
    Log("Starting LED-Wiz Daemon...");
    if (!DiscoverBoards()) {
        Log("No boards found initially, will retry on command.");
    }

    while (true) {
        HANDLE hPipe = CreateNamedPipe(PIPE_NAME, PIPE_ACCESS_DUPLEX, PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
                                       PIPE_UNLIMITED_INSTANCES, BUFFER_SIZE, BUFFER_SIZE, 0, NULL);

        if (hPipe == INVALID_HANDLE_VALUE) {
            Log("Failed to create named pipe.");
            Sleep(5000);
            continue;
        }

        Log("Waiting for connection...");
        if (ConnectNamedPipe(hPipe, NULL) ? TRUE : (GetLastError() == ERROR_PIPE_CONNECTED)) {
            Log("Client connected.");
            char buffer[BUFFER_SIZE];
            DWORD read;
            std::string leftover = "";
            while (ReadFile(hPipe, buffer, sizeof(buffer) - 1, &read, NULL) && read > 0) {
                buffer[read] = '\0';
                std::string data = leftover + std::string(buffer);
                leftover = "";

                size_t pos = 0;
                while ((pos = data.find('\n')) != std::string::npos) {
                    std::string line = data.substr(0, pos);
                    if (!line.empty() && line.back() == '\r') line.pop_back();
                    if (!line.empty()) {
                        HandleCommand(line);
                    }
                    data.erase(0, pos + 1);
                }
                leftover = data;
            }
            Log("Client disconnected.");
        }
        CloseHandle(hPipe);
    }

    CloseBoards();
    return 0;
}
