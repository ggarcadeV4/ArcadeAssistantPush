# Golden A-Drive Clone Checklist

1. **Run `clean_for_clone.bat` on the development cabinet.**  
   This removes `.aa` identity files, `state/profile`, `state/scorekeeper`, and all `logs`, leaving the drive sanitized for imaging.
2. **Shut down and clone the entire `A:` drive onto the target SSD.**  
   Use your normal disk imaging workflow (offline clone station, dd, etc.) so the filesystem layout is copied sector-for-sector.
3. **On the new cabinet, run the provisioning flow (coming soon).**  
   That process will generate a fresh `device_id`, write a new `.aa/manifest.json`, and capture new consent/profile data for the cabinet.

> **Warning**  
> - Do **not** run the cleanup script on a cabinet that is already in production unless you intend to wipe its local scores and logs.  
> - The script does **not** remove Supabase keys; keep `.env` internal and rotate keys if a cloned drive leaves your control.
