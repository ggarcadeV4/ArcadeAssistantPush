
import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_ANON_KEY")
service_key = os.environ.get("SUPABASE_SERVICE_KEY")

print(f"URL: {url}")
print(f"Key: {key and '***'}")
print(f"Service Key: {service_key and '***'}")

async def probe_table(client, table_name):
    try:
        # Just try to select 1 row, don't care about data
        client.table(table_name).select("*").limit(1).execute()
        return True
    except Exception as e:
        if "PGRST205" in str(e): # Not found
            return False
        # Other error (auth?) might mean table exists but is protected
        print(f"[{table_name}] Error: {e}")
        return False

async def main():
    if not url or not key:
        print("Missing Credentials")
        return

    client = create_client(url, key)
    
    candidates = ["devices", "device", "cabinet", "cabinets", "arcade_cabinets", "profiles", "users"]
    
    print("\nProbing Tables (Anon Key)...")
    for t in candidates:
        exists = await probe_table(client, t)
        print(f"Table '{t}': {'EXISTS' if exists else 'MISSING'}")

    if service_key:
        print("\nProbing Tables (Service Key)...")
        admin = create_client(url, service_key)
        for t in candidates:
            exists = await probe_table(admin, t)
            print(f"Table '{t}': {'EXISTS' if exists else 'MISSING'}")

if __name__ == "__main__":
    asyncio.run(main())
