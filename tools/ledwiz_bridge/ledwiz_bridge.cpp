#include "ledwiz_bridge.h"

#include <windows.h>
#include <setupapi.h>
#include <hidsdi.h>

#include <algorithm>
#include <cstdint>
#include <mutex>
#include <string>
#include <vector>

#pragma comment(lib, "setupapi.lib")
#pragma comment(lib, "hid.lib")

namespace {

constexpr USHORT kLedWizVid = 0xFAFA;
constexpr USHORT kLedWizPidMin = 0x00F0;
constexpr USHORT kLedWizPidMax = 0x00FF;
constexpr int kChannelCount = 32;
constexpr int kDefaultReportLen = 9;

struct LedWizDevice {
    std::wstring path;
    HANDLE handle = INVALID_HANDLE_VALUE;
    USHORT vid = 0;
    USHORT pid = 0;
    USHORT outputReportLen = kDefaultReportLen;
    std::vector<uint8_t> frame;
};

std::mutex g_mutex;
std::vector<LedWizDevice> g_devices;
int g_last_error_code = 0;
std::string g_last_error;

void SetError(int code, const char* message) {
    g_last_error_code = code;
    g_last_error = message ? message : "";
}

std::string WideToUtf8(const std::wstring& wide) {
    if (wide.empty()) return "";
    int size_needed = WideCharToMultiByte(CP_UTF8, 0, wide.c_str(),
                                          static_cast<int>(wide.size()), nullptr, 0, nullptr, nullptr);
    if (size_needed <= 0) return "";
    std::string result(size_needed, '\0');
    WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), static_cast<int>(wide.size()),
                        result.data(), size_needed, nullptr, nullptr);
    return result;
}

bool IsLedWiz(USHORT vid, USHORT pid) {
    return (vid == kLedWizVid) && (pid >= kLedWizPidMin) && (pid <= kLedWizPidMax);
}

bool GetOutputReportLength(HANDLE handle, USHORT* out_len) {
    if (!out_len) return false;
    *out_len = kDefaultReportLen;
    PHIDP_PREPARSED_DATA preparsed = nullptr;
    if (!HidD_GetPreparsedData(handle, &preparsed)) return false;
    HIDP_CAPS caps = {};
    if (HidP_GetCaps(preparsed, &caps) == HIDP_STATUS_SUCCESS) {
        if (caps.OutputReportByteLength > 0) {
            *out_len = caps.OutputReportByteLength;
        }
    }
    HidD_FreePreparsedData(preparsed);
    return true;
}

std::vector<LedWizDevice> EnumerateLedWiz() {
    std::vector<LedWizDevice> devices;

    GUID hid_guid;
    HidD_GetHidGuid(&hid_guid);

    HDEVINFO info = SetupDiGetClassDevs(
        &hid_guid, nullptr, nullptr, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
    if (info == INVALID_HANDLE_VALUE) return devices;

    DWORD index = 0;
    SP_DEVICE_INTERFACE_DATA interface_data = {};
    interface_data.cbSize = sizeof(interface_data);

    while (SetupDiEnumDeviceInterfaces(info, nullptr, &hid_guid, index, &interface_data)) {
        DWORD required_size = 0;
        SetupDiGetDeviceInterfaceDetailW(info, &interface_data, nullptr, 0, &required_size, nullptr);
        if (required_size == 0) {
            index++;
            continue;
        }

        std::vector<uint8_t> detail_buffer(required_size);
        auto* detail_data = reinterpret_cast<SP_DEVICE_INTERFACE_DETAIL_DATA_W*>(detail_buffer.data());
        detail_data->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W);

        if (!SetupDiGetDeviceInterfaceDetailW(
                info, &interface_data, detail_data, required_size, nullptr, nullptr)) {
            index++;
            continue;
        }

        std::wstring device_path = detail_data->DevicePath;
        HANDLE handle = CreateFileW(
            device_path.c_str(),
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            nullptr,
            OPEN_EXISTING,
            0,
            nullptr);

        if (handle == INVALID_HANDLE_VALUE) {
            index++;
            continue;
        }

        HIDD_ATTRIBUTES attributes = {};
        attributes.Size = sizeof(attributes);
        if (!HidD_GetAttributes(handle, &attributes)) {
            CloseHandle(handle);
            index++;
            continue;
        }

        if (!IsLedWiz(attributes.VendorID, attributes.ProductID)) {
            CloseHandle(handle);
            index++;
            continue;
        }

        USHORT out_len = kDefaultReportLen;
        GetOutputReportLength(handle, &out_len);

        LedWizDevice dev;
        dev.path = device_path;
        dev.handle = INVALID_HANDLE_VALUE;
        dev.vid = attributes.VendorID;
        dev.pid = attributes.ProductID;
        dev.outputReportLen = out_len;
        dev.frame.assign(kChannelCount, 0);
        devices.push_back(dev);

        CloseHandle(handle);
        index++;
    }

    SetupDiDestroyDeviceInfoList(info);

    std::sort(devices.begin(), devices.end(),
              [](const LedWizDevice& a, const LedWizDevice& b) {
                  if (a.pid == b.pid) return a.path < b.path;
                  return a.pid < b.pid;
              });

    return devices;
}

bool OpenDevice(LedWizDevice& dev) {
    if (dev.handle != INVALID_HANDLE_VALUE) return true;
    HANDLE handle = CreateFileW(
        dev.path.c_str(),
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        nullptr,
        OPEN_EXISTING,
        0,
        nullptr);
    if (handle == INVALID_HANDLE_VALUE) {
        return false;
    }
    dev.handle = handle;
    return true;
}

void CloseDevice(LedWizDevice& dev) {
    if (dev.handle != INVALID_HANDLE_VALUE) {
        CloseHandle(dev.handle);
        dev.handle = INVALID_HANDLE_VALUE;
    }
}

bool WriteReport(LedWizDevice& dev, const std::vector<uint8_t>& report) {
    if (dev.handle == INVALID_HANDLE_VALUE) return false;
    DWORD written = 0;
    BOOL ok = WriteFile(dev.handle, report.data(),
                        static_cast<DWORD>(report.size()), &written, nullptr);
    return ok && written == report.size();
}

std::vector<uint8_t> BuildSbaReport(USHORT report_len, int bank0, int bank1, int bank2, int bank3, int speed) {
    std::vector<uint8_t> report(report_len, 0);
    report[0] = 0x00;
    if (report_len > 1) report[1] = static_cast<uint8_t>(bank0);
    if (report_len > 2) report[2] = static_cast<uint8_t>(bank1);
    if (report_len > 3) report[3] = static_cast<uint8_t>(bank2);
    if (report_len > 4) report[4] = static_cast<uint8_t>(bank3);
    if (report_len > 5) report[5] = static_cast<uint8_t>(speed);
    return report;
}

std::vector<uint8_t> BuildPbaReport(USHORT report_len, int chunk_idx, const std::vector<uint8_t>& values) {
    std::vector<uint8_t> report(report_len, 0);
    report[0] = 0x00;
    if (report_len > 1) report[1] = static_cast<uint8_t>(0x40 + chunk_idx);
    for (size_t i = 0; i < values.size() && (i + 2) < report.size(); ++i) {
        report[i + 2] = values[i];
    }
    return report;
}

bool WriteFrame(LedWizDevice& dev) {
    int bank0 = 0, bank1 = 0, bank2 = 0, bank3 = 0;
    for (int i = 0; i < kChannelCount; ++i) {
        if (dev.frame[i] > 0) {
            if (i < 8) bank0 |= (1 << i);
            else if (i < 16) bank1 |= (1 << (i - 8));
            else if (i < 24) bank2 |= (1 << (i - 16));
            else bank3 |= (1 << (i - 24));
        }
    }

    std::vector<uint8_t> sba = BuildSbaReport(dev.outputReportLen, bank0, bank1, bank2, bank3, 2);
    if (!WriteReport(dev, sba)) return false;

    for (int chunk = 0; chunk < 4; ++chunk) {
        std::vector<uint8_t> values;
        values.reserve(8);
        int start = chunk * 8;
        for (int i = 0; i < 8; ++i) {
            int idx = start + i;
            uint8_t v = dev.frame[idx];
            values.push_back(v);
        }
        std::vector<uint8_t> pba = BuildPbaReport(dev.outputReportLen, chunk, values);
        if (!WriteReport(dev, pba)) return false;
    }
    return true;
}

}  // namespace

extern "C" {

LEDWIZ_BRIDGE_API bool LED_Init() {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_devices.clear();
    SetError(0, "");

    auto devices = EnumerateLedWiz();
    if (devices.empty()) {
        SetError(1001, "No LED-Wiz devices detected");
        return false;
    }

    for (auto& dev : devices) {
        if (!OpenDevice(dev)) {
            SetError(1002, "LED-Wiz detected but failed to open HID handle");
            g_devices.clear();
            return false;
        }
    }

    g_devices = std::move(devices);
    return true;
}

LEDWIZ_BRIDGE_API bool LED_SetPort(int port, int intensity) {
    std::lock_guard<std::mutex> lock(g_mutex);
    SetError(0, "");
    if (g_devices.empty()) {
        SetError(1003, "LED_Init not called or no devices opened");
        return false;
    }
    if (port < 1) {
        SetError(1004, "Port must be >= 1");
        return false;
    }
    int clamped = std::max(0, std::min(48, intensity));
    int board_index = (port - 1) / kChannelCount;
    int local = (port - 1) % kChannelCount;
    if (board_index < 0 || board_index >= static_cast<int>(g_devices.size())) {
        SetError(1005, "Port out of range for detected boards");
        return false;
    }
    auto& dev = g_devices[board_index];
    dev.frame[local] = static_cast<uint8_t>(clamped);
    if (!WriteFrame(dev)) {
        SetError(1006, "HID write failed");
        return false;
    }
    return true;
}

LEDWIZ_BRIDGE_API bool LED_AllOff() {
    std::lock_guard<std::mutex> lock(g_mutex);
    SetError(0, "");
    if (g_devices.empty()) {
        SetError(1003, "LED_Init not called or no devices opened");
        return false;
    }
    for (auto& dev : g_devices) {
        std::fill(dev.frame.begin(), dev.frame.end(), 0);
        if (!WriteFrame(dev)) {
            SetError(1006, "HID write failed");
            return false;
        }
    }
    return true;
}

LEDWIZ_BRIDGE_API int LED_GetBoardCount() {
    std::lock_guard<std::mutex> lock(g_mutex);
    return static_cast<int>(g_devices.size());
}

LEDWIZ_BRIDGE_API void LED_Close() {
    std::lock_guard<std::mutex> lock(g_mutex);
    for (auto& dev : g_devices) {
        CloseDevice(dev);
    }
    g_devices.clear();
    SetError(0, "");
}

LEDWIZ_BRIDGE_API int LED_GetLastErrorCode() {
    return g_last_error_code;
}

LEDWIZ_BRIDGE_API const char* LED_GetLastError() {
    return g_last_error.c_str();
}

}  // extern "C"

#ifdef LEDWIZ_BRIDGE_CLI

#include <cstdio>
#include <iostream>

void PrintUsage() {
    std::cout
        << "Usage:\n"
        << "  ledwiz_bridge.exe list\n"
        << "  ledwiz_bridge.exe set <port> <intensity>\n"
        << "  ledwiz_bridge.exe alloff\n"
        << "\n"
        << "Notes:\n"
        << "  Port is 1-based. Intensity range 0-48.\n";
}

int main(int argc, char** argv) {
    if (argc < 2) {
        PrintUsage();
        return 1;
    }

    std::string cmd = argv[1];
    if (cmd == "list") {
        auto devices = EnumerateLedWiz();
        std::cout << "{";
        std::cout << "\"count\":" << devices.size() << ",\"devices\":[";
        for (size_t i = 0; i < devices.size(); ++i) {
            if (i > 0) std::cout << ",";
            std::cout << "{";
            std::cout << "\"vid\":\"0x" << std::hex << devices[i].vid << std::dec << "\"";
            std::cout << ",\"pid\":\"0x" << std::hex << devices[i].pid << std::dec << "\"";
            std::cout << ",\"path\":\"" << WideToUtf8(devices[i].path) << "\"";
            std::cout << "}";
        }
        std::cout << "]}\n";
        return 0;
    }

    if (!LED_Init()) {
        std::cout << "{\"status\":\"error\",\"code\":" << LED_GetLastErrorCode()
                  << ",\"message\":\"" << LED_GetLastError() << "\"}\n";
        return 1;
    }

    if (cmd == "set" && argc >= 4) {
        int port = std::atoi(argv[2]);
        int intensity = std::atoi(argv[3]);
        bool ok = LED_SetPort(port, intensity);
        if (!ok) {
            std::cout << "{\"status\":\"error\",\"code\":" << LED_GetLastErrorCode()
                      << ",\"message\":\"" << LED_GetLastError() << "\"}\n";
            LED_Close();
            return 1;
        }
        std::cout << "{\"status\":\"ok\",\"port\":" << port
                  << ",\"intensity\":" << intensity << "}\n";
        LED_Close();
        return 0;
    }

    if (cmd == "alloff") {
        bool ok = LED_AllOff();
        if (!ok) {
            std::cout << "{\"status\":\"error\",\"code\":" << LED_GetLastErrorCode()
                      << ",\"message\":\"" << LED_GetLastError() << "\"}\n";
            LED_Close();
            return 1;
        }
        std::cout << "{\"status\":\"ok\",\"action\":\"alloff\"}\n";
        LED_Close();
        return 0;
    }

    PrintUsage();
    LED_Close();
    return 1;
}

#endif
