import os
import sqlite3
import json
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# Load NPS_API_KEY from .env at project root
load_dotenv()
API_KEY = os.getenv("NPS_API_KEY")

BASE_URL = "https://developer.nps.gov/api/v1/parks"
BOUNDARY_URL = "https://developer.nps.gov/api/v1/mapdata/parkboundaries"

# Path to your DB: .../ED305Project/database/nps.db
DB_PATH = Path(__file__).resolve().parents[1] / "database" / "nps.db"


def fetch_all_parks():
    """Fetch all parks from the NPS API and return a list of simplified dicts."""
    if not API_KEY:
        raise RuntimeError("NPS_API_KEY is not set. Put it in a .env file at project root.")

    parks = []
    # you already saw total=474 so we can just use 474 in one page
    params = {
        "api_key": API_KEY,
        "limit": 474,
        "start": 0,
    }

    print("Requesting parks from NPS API...")
    resp = requests.get(BASE_URL, params=params)
    resp.raise_for_status()
    data = resp.json()

    batch = data.get("data", [])
    print(f"Fetched {len(batch)} raw parks from API")

    for p in batch:
        parks.append(
            {
                "park_code": p.get("parkCode").upper() if p.get("parkCode") else None,
                "park_name": p.get("fullName"),
                "state": p.get("states"),
                "designation": p.get("designation"),
                "latitude": float(p["latitude"]) if p.get("latitude") else None,
                "longitude": float(p["longitude"]) if p.get("longitude") else None,
                "description": p.get("description"),
                "website": p.get("url"),
                "boundary": p.get("directionsInfo"),
            }
        )

    print(f"Simplified to {len(parks)} parks")
    return parks


def fetch_park_boundary(park_code: str) -> Optional[str]:
    """
    Fetch the GeoJSON boundary for a park from the NPS mapdata API.
    Returns the boundary GeoJSON as a JSON string, or None if not available.
    """
    try:
        params = {"api_key": API_KEY}
        url = f"{BOUNDARY_URL}/{park_code}"
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        
        # Return the entire response as JSON string (contains features/geometry)
        return json.dumps(data)
    except Exception as e:
        # Silently fail; boundary is optional
        return None


def insert_parks_into_db(parks):
    """Insert park records into the park table in nps.db."""
    print(f"Using DB at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Optional: clear existing rows so you can rerun safely
    print("Clearing existing rows from park table...")
    cur.execute("DELETE FROM park;")

    print(f"Inserting {len(parks)} parks into park table...")
    for idx, p in enumerate(parks, start=1):
        # Fetch boundary for this park (GeoJSON)
        if idx % 50 == 0:
            print(f"  [{idx}/{len(parks)}] Processing {p['park_code']}...")
        
        boundary_geojson = fetch_park_boundary(p["park_code"])
        
        # region_id is set to NULL for now; CSV ETL will fill it later
        cur.execute(
            """
            INSERT OR REPLACE INTO park
            (park_code, park_name, state, designation, region_id, latitude, longitude, description, website, boundary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                p["park_code"],
                p["park_name"],
                p["state"],
                p["designation"],
                None,  # region_id placeholder; will be updated from CSV
                p["latitude"],
                p["longitude"],
                p.get("description"),
                p.get("website"),
                boundary_geojson,  # GeoJSON string or None
            ),
        )

    conn.commit()
    conn.close()
    print("Done inserting parks into database.")


if __name__ == "__main__":
    parks = fetch_all_parks()

    # sanity check: print first 3
    for p in parks[:3]:
        print(p)

    insert_parks_into_db(parks)
