# Arcade Assistant - Serial Number Registry

**Purpose:** Track all cabinet installations by serial number

**Last Updated:** December 2025

---

## Active Installations

| Serial  | Cabinet Name       | Location           | Owner/Customer | Install Date | Status | Notes |
|---------|--------------------|--------------------|----------------|--------------|--------|-------|
| AA-0001 | Basement Cabinet 1 | Basement - Left    | Personal       | 2025-12-01   | Active |       |
| AA-0002 | Basement Cabinet 2 | Basement - Right   | Personal       | 2025-12-01   | Active |       |
|         |                    |                    |                |              |        |       |

---

## Serial Number Format

**Pattern:** `AA-####`
- **AA** = Arcade Assistant
- **####** = Sequential 4-digit number (0001, 0002, 0003, etc.)

**Rules:**
- Serial numbers are **unique** and **permanent**
- Once assigned, a serial is **never reused**
- Even if a cabinet is decommissioned, its serial stays retired
- Always assign the next available number in sequence

---

## Assignment Log

**Next Available Serial:** AA-0003

### Assignment History:
```
2025-12-01 - AA-0001 assigned to "Basement Cabinet 1" (Personal)
2025-12-01 - AA-0002 assigned to "Basement Cabinet 2" (Personal)
```

---

## Decommissioned Installations

| Serial  | Cabinet Name | Decommission Date | Reason        | Notes |
|---------|--------------|-------------------|---------------|-------|
| -       | -            | -                 | -             | -     |

---

## Customer Installations (Future)

When deploying to customers, add entries here:

| Serial  | Customer Name | Location          | Install Date | Contract End | Status |
|---------|---------------|-------------------|--------------|--------------|--------|
| -       | -             | -                 | -            | -            | -      |

**Example:**
| AA-0003 | John Smith    | 123 Main St       | 2025-12-15   | 2026-12-15   | Active |
| AA-0004 | Bob Jones     | 456 Oak Ave       | 2025-12-20   | 2026-12-20   | Active |

---

## Device Info Lookup

To find which cabinet has which serial:

**Method 1: Check Desktop**
- Open cabinet PC
- Look at command window titles when AA is running
- Title shows: `AA Backend [AA-####]` or `AA Gateway [AA-####]`

**Method 2: Check .env File**
- Navigate to `C:\ArcadeAssistant\.env`
- Open in Notepad
- Look for: `DEVICE_SERIAL=AA-####`

**Method 3: Check Logs**
- Navigate to `C:\ArcadeAssistant\SERIAL_REGISTRY.log`
- Shows installation timestamp and serial

---

## Maintenance Log

### Cabinet 1 (AA-0001)
```
2025-12-01 - Initial installation
```

### Cabinet 2 (AA-0002)
```
2025-12-01 - Initial installation
```

---

## Future Network Integration

When cabinets are connected on a network, add network info:

| Serial  | IP Address    | MAC Address       | Network Name  | Last Seen  |
|---------|---------------|-------------------|---------------|------------|
| AA-0001 | 192.168.1.101 | 00:1A:2B:3C:4D:5E | CABINET-001   | 2025-12-01 |
| AA-0002 | 192.168.1.102 | 00:1A:2B:3C:4D:5F | CABINET-002   | 2025-12-01 |

---

## Notes

- Keep this file updated when installing new cabinets
- Include notes about special configurations or issues
- Use for inventory tracking and support purposes
- Serial numbers help identify cabinets in logs and analytics
