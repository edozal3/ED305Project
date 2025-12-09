import sqlite3
from pathlib import Path

import pandas as pd

# Paths
BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "database" / "nps.db"
CSV_PATH = BASE_DIR / "data" / "nps_visits.csv"  # <-- change name if your CSV is different


# Mapping from cleaned region name -> region_id (based on your CSV values)
REGION_ID_MAP = {
    "Alaska": "AKR",
    "Intermountain": "IMR",
    "Midwest": "MWR",
    "National Capital": "NCR",
    "Northeast": "NER",
    "Pacific West": "PWR",
    "Southeast": "SER",
}


def clean_region_name(raw: str) -> str:
    """Normalize region strings from the CSV (strip extra spaces, collapse multiple spaces)."""
    if raw is None:
        return ""
    cleaned = " ".join(str(raw).split())
    return cleaned


def load_csv():
    print(f"Using DB at:   {DB_PATH}")
    print(f"Looking for CSV files in: {BASE_DIR / 'data'}")

    # 1. Load CSV(s) into pandas. If there are multiple yearly CSV files (e.g., 2015-2024),
    # concatenate them so we import the full history.
    data_dir = BASE_DIR / "data"
    csv_paths = sorted(data_dir.glob("*.csv"))
    if not csv_paths:
        raise RuntimeError(f"No CSV files found in {data_dir}")

    if len(csv_paths) == 1:
        print(f"Loading single CSV: {csv_paths[0].name}")
        df = pd.read_csv(csv_paths[0], thousands=",")
    else:
        print(f"Loading and concatenating {len(csv_paths)} CSV files")
        df_list = [pd.read_csv(p, thousands=",") for p in csv_paths]
        df = pd.concat(df_list, ignore_index=True)

    df["UnitCode"] = df["UnitCode"].astype(str).str.upper()

    # Make sure expected columns exist
    required_cols = [
        "Region",
        "UnitCode",
        "Year",
        "Month",
        "RecreationVisits",
        "NonRecreationVisits",
        "ConcessionerLodging",
        "ConcessionerCamping",
        "TentCampers",
        "RVCampers",
        "Backcountry",
        "NonRecreationOvernightStays",
        "MiscellaneousOvernightStays",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise RuntimeError(f"CSV is missing expected columns: {missing}")

    # Clean Region strings and map to region_id
    df["Region_clean"] = df["Region"].apply(clean_region_name)
    df["region_id"] = df["Region_clean"].map(REGION_ID_MAP)

    if df["region_id"].isna().any():
        unknown_regions = df.loc[df["region_id"].isna(), "Region_clean"].unique()
        print("WARNING: Some regions did not map to REGION_ID_MAP:", unknown_regions)

    # Compute total_visits
    df["RecreationVisits"] = df["RecreationVisits"].fillna(0).astype(int)
    df["NonRecreationVisits"] = df["NonRecreationVisits"].fillna(0).astype(int)
    df["total_visits"] = df["RecreationVisits"] + df["NonRecreationVisits"]

    # Prepare smaller dataframe for monthly_visit insert
    mv_cols = [
        "UnitCode",
        "Year",
        "Month",
        "RecreationVisits",
        "NonRecreationVisits",
        "total_visits",
        "ConcessionerLodging",
        "ConcessionerCamping",
        "TentCampers",
        "RVCampers",
        "Backcountry",
        "NonRecreationOvernightStays",
        "MiscellaneousOvernightStays",
    ]
    mv_df = df[mv_cols].copy()

    # Fill NaNs with 0 and cast to int where appropriate
    int_cols = [
        "Year",
        "Month",
        "RecreationVisits",
        "NonRecreationVisits",
        "total_visits",
        "ConcessionerLodging",
        "ConcessionerCamping",
        "TentCampers",
        "RVCampers",
        "Backcountry",
        "NonRecreationOvernightStays",
        "MiscellaneousOvernightStays",
    ]
    for c in int_cols:
        mv_df[c] = mv_df[c].fillna(0).astype(int)

    # 2. Connect to SQLite
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 3. Populate REGION table (7 rows)
    print("Inserting regions into region table...")
    cur.execute("DELETE FROM region;")

    region_rows = []
    for region_name, region_id in REGION_ID_MAP.items():
        region_rows.append(
            (region_id, region_name, None)  # description = None for now
        )

    cur.executemany(
        "INSERT INTO region (region_id, region_name, description) VALUES (?, ?, ?);",
        region_rows,
    )
    print(f"Inserted {len(region_rows)} regions.")

    # 4. Update park.region_id from CSV (UnitCode -> region_id)
    print("Updating park.region_id from CSV mapping...")
    park_region_df = (
        df[["UnitCode", "region_id"]]
        .dropna(subset=["region_id"])
        .drop_duplicates()
        .rename(columns={"UnitCode": "park_code"})
    )

    updated = 0
    for _, row in park_region_df.iterrows():
        cur.execute(
            """
            UPDATE park
            SET region_id = ?
            WHERE park_code = ?;
            """,
            (row["region_id"], row["park_code"]),
        )
        if cur.rowcount > 0:
            updated += cur.rowcount

    print(f"Updated region_id for {updated} parks.")

    # 5. Populate MONTHLY_VISIT table
    print("Inserting monthly_visit rows...")
    cur.execute("DELETE FROM monthly_visit;")

    monthly_rows = []
    for _, r in mv_df.iterrows():
        monthly_rows.append(
            (
                r["UnitCode"],
                int(r["Year"]),
                int(r["Month"]),
                int(r["RecreationVisits"]),
                int(r["NonRecreationVisits"]),
                int(r["total_visits"]),
                int(r["ConcessionerLodging"]),
                int(r["ConcessionerCamping"]),
                int(r["TentCampers"]),
                int(r["RVCampers"]),
                int(r["Backcountry"]),
                int(r["NonRecreationOvernightStays"]),
                int(r["MiscellaneousOvernightStays"]),
            )
        )

    cur.executemany(
        """
        INSERT OR REPLACE INTO monthly_visit
        (park_code, year, month,
         recreation_visits, non_recreation_visits, total_visits,
         concessioner_lodging, concessioner_camping,
         tent_campers, rv_campers, backcountry,
         nonrecreation_overnight_stays, miscellaneous_overnight_stays)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        monthly_rows,
    )

    print(f"Inserted {len(monthly_rows)} monthly_visit rows.")

    conn.commit()
    conn.close()
    print("CSV load complete.")


if __name__ == "__main__":
    load_csv()
