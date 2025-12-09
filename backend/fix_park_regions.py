import sqlite3
from pathlib import Path
import pandas as pd

# Reuse the same mapping as the loader. Update this dict if your CSV uses
# slightly different region names.
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
    if raw is None:
        return ""
    return " ".join(str(raw).split())


def main():
    base = Path(__file__).resolve().parents[1]
    db_path = base / "database" / "nps.db"
    data_dir = base / "data"

    csv_paths = sorted(data_dir.glob("*.csv"))
    if not csv_paths:
        print(f"No CSV files found in {data_dir}")
        return

    print(f"Reading {len(csv_paths)} CSV(s) to infer park -> region mapping...")
    df_list = [pd.read_csv(p, thousands=",") for p in csv_paths]
    df = pd.concat(df_list, ignore_index=True)

    if "UnitCode" not in df.columns or "Region" not in df.columns:
        print("CSV missing required columns UnitCode or Region")
        return

    df["UnitCode"] = df["UnitCode"].astype(str).str.upper()
    df["Region_clean"] = df["Region"].apply(clean_region_name)
    df["region_id"] = df["Region_clean"].map(REGION_ID_MAP)

    # Report any unknown region names so user can adjust REGION_ID_MAP
    unknown = df.loc[df["region_id"].isna(), "Region_clean"].unique()
    if len(unknown) > 0:
        print("WARNING: Unknown region names found in CSV (add to REGION_ID_MAP):")
        for u in unknown:
            print(" -", repr(u))

    park_region_df = (
        df[["UnitCode", "region_id"]]
        .dropna(subset=["region_id"]) 
        .drop_duplicates()
        .rename(columns={"UnitCode": "park_code"})
    )

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Ensure region table has the region rows
    print("Inserting missing regions into region table (if any)...")
    for name, rid in REGION_ID_MAP.items():
        cur.execute(
            "INSERT OR IGNORE INTO region (region_id, region_name, description) VALUES (?, ?, NULL);",
            (rid, name),
        )

    conn.commit()

    # Update parks
    print(f"Updating park.region_id for {len(park_region_df)} parks...")
    not_found = []
    updated = 0
    for _, row in park_region_df.iterrows():
        park_code = row["park_code"]
        region_id = row["region_id"]
        cur.execute("UPDATE park SET region_id = ? WHERE park_code = ?;", (region_id, park_code))
        if cur.rowcount == 0:
            not_found.append((park_code, region_id))
        else:
            updated += cur.rowcount

    conn.commit()

    print(f"Updated region_id for {updated} parks.")
    if not_found:
        print("The following park_codes were not found in `park` table (no update performed):")
        for pk, rid in not_found[:100]:
            print(f" - {pk} -> {rid}")
        if len(not_found) > 100:
            print(f" ... and {len(not_found)-100} more")

    conn.close()


if __name__ == "__main__":
    main()
