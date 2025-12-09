# NPS Park Operations Management System

A full-stack analytics dashboard for exploring National Park Service (NPS) visitor data, built with FastAPI (backend) and Streamlit (frontend).

## Project Overview

This application provides 10 analytical queries plus metrics exploration to analyze visitor patterns, trends, and park performance across the NPS system. Features include interactive park search, multi-region filtering, monthly trend analysis, growth calculations, and an interactive map with park boundaries.

## Tech Stack

- **Backend**: FastAPI, SQLModel, SQLite
- **Frontend**: Streamlit, Plotly Express, Folium
- **Database**: SQLite (nps.db)
- **Data Source**: NPS API + CSV monthly visitor data

## Project Structure

```
ED305Project/
├── backend/
│   ├── main.py              # FastAPI app with 10+ query endpoints
│   ├── models.py            # SQLModel definitions (Region, Park, MonthlyVisit)
│   ├── database.py          # SQLite connection
│   ├── fetch_data.py        # Script to fetch parks from NPS API + boundaries
│   ├── load_csv.py          # Script to load monthly visit data from CSV
│   └── requirements.txt      # Python dependencies
├── frontend/
│   ├── app.py               # Streamlit dashboard with 11 queries + map
│   └── requirements.txt      # Python dependencies
├── database/
│   ├── schema.sql           # SQL table definitions
│   └── create_db.py         # Database initialization script
├── data/
│   └── nps_visits.csv       # Monthly visitor data (2015-2024)
├── .env                     # NPS API key (gitignored)
└── README.md                # This file
```

## Setup Instructions

### 1. Prerequisites

- Python 3.9+
- pip / conda
- NPS API key (get one at https://www.nps.gov/subjects/developer/get-started.htm)

### 2. Clone Repository

```bash
git clone <repo-url>
cd ED305Project
```

### 3. Create Virtual Environment

**Windows (PowerShell)**:
```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1
```

**macOS/Linux (Bash/Zsh)**:
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate
```

### 4. Install Dependencies

With the virtual environment active, install all project dependencies from the single requirements file (covers backend + frontend):

```bash
pip install -r backend/requirements.txt
```

### 5. Configure Environment

Create a `.env` file in the project root:

```
NPS_API_KEY=your_api_key_here
```

### 6. Initialize Database

```bash
cd database
python create_db.py          # Creates empty nps.db with schema
# Make sure to run fetch_data.py first then load_csv.py second
cd ../backend
python fetch_data.py         # Fetches ~474 parks + boundaries from NPS API, this step may take a few minutes 
python load_csv.py           # Loads monthly visit data from CSV
```

### 7. Start Backend

```bash
cd backend
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Backend will be available at `http://127.0.0.1:8000/docs`

### 8. Start Frontend

From the project root, run:

```bash
python -m streamlit run frontend/app.py
```

**Alternative commands** (if `streamlit` is on PATH):
- Windows: `streamlit run .\frontend\app.py`
- macOS/Linux: `streamlit run ./frontend/app.py`
- Or: `cd frontend` then `streamlit run app.py`

Frontend will open at `http://localhost:8501`

### 9. Deactivate Virtual Environment (when done)

**Windows/macOS/Linux**:
```bash
deactivate
```

## Queries & Features

### Q1: Monthly Visits (Park Search)
Compare monthly visitor trends for a specific park across multiple years. Shows total visits by month with line chart visualization.

### Q2: Annual by Park
Rank parks by total annual visitors in a selected year. Supports multi-region filtering with sorted results (highest to lowest).

### Q3: Avg Monthly Visits
Calculate average monthly visitor count per park over a year range. Useful for understanding typical monthly traffic patterns.

### Q4: Peak Season (Jun-Aug)
Find parks that exceed a visitor threshold during peak summer season. Identifies high-traffic parks when tourism peaks.

### Q5: Above Average Parks
Show parks with annual visits above system-wide or region-wide average. Includes scatter plot visualization (% above average vs. total visits).

### Q6: Top Parks by Annual Visits
Rank parks by total annual visitors. Sorted by visitation, mixed across regions when multiple regions selected.

### Q7: Annual Visits by Region
Compare total visitor numbers across all NPS regions. Includes pie chart showing geographic distribution of visitors.

### Q8: Month-to-Month Change
Track month-to-month visitor changes for a specific park. Shows change in absolute numbers and percentage with color-coded bar chart (green=increase, red=decrease). January is hidden (no prior month for comparison).

### Q9: Parks with Highest Growth
Compare visitor growth percentages for parks between two years. Identifies parks with fastest growth in visitation. Multi-region results sorted by growth %.

### Q10: Visitor Variability
Rank parks by month-to-month fluctuation (standard deviation). High variability indicates seasonal tourism; low indicates consistent visitation.

### Metrics
Explore visitor activity metrics: concessioner lodging, camping, tent campers, RV campers, backcountry visits, etc. Multi-region results sorted by metric value.

## Global Filters

- **Regions**: Select one or more regions (or "All Regions" for all parks)
- **Year**: Choose analysis year via slider
- **Results Limit**: Cap max results returned (1-100)
- **Park Search**: Search parks by name/code and load from specific regions
- **Selected Parks**: Filter all queries to only show selected parks

## Key Features

### Sticky Results
- Query results are cached in session state
- Switch between queries and return to see last results without re-fetching
- Info banner shows context (year, regions, limits)

### Smart Sorting
- Multi-region results automatically sort by metric value (not grouped by region)
- All parks mixed together ranked by what matters (visits, growth, variability, etc.)

### Interactive Map Tab
- Click "Load Map" to view all parks as markers (sized by visitor count, colored by region)
- Click park markers for details
- Select a park to view full details + boundary overlay on separate map

### Park Search & Selection
- Search by park name or code
- Load all parks from selected regions
- Use global park filter to apply selection across all queries

## Data Notes

- **Years**: 2015-2024 (expandable)
- **Granularity**: Monthly per park
- **Metrics**: Recreation visits, camping, lodging, backcountry, etc.
- **Park Boundaries**: GeoJSON from NPS API (optional display on map)

## Known Limitations

- January data excluded from Q8 month-to-month change (no prior month for comparison)
- Park boundaries may not load for all parks (data availability varies by NPS API)
- Multi-region API requests are sequential (not parallelized for rate limiting)
- Streamlit reruns entire page on state changes (inherent to framework)

## Troubleshooting

### Backend won't start
- Ensure NPS_API_KEY is set in `.env`
- Check port 8000 is not in use: `netstat -an | grep 8000`
- Verify FastAPI is installed: `pip install fastapi uvicorn`

### Frontend won't load data
- Check backend is running: `curl http://127.0.0.1:8000/metadata/years`
- Verify database exists: `ls database/nps.db`
- Check Streamlit logs for connection errors

### Missing regions in CSV
- Verify CSV has region names matching `REGION_ID_MAP` in `load_csv.py`
- Run `python load_csv.py` again after fixing CSV

### Slow queries
- Increase results limit to 5-10 for faster response
- Reduce year range in Q3
- Consider filtering to fewer regions

## API Endpoints

All endpoints documented at `http://127.0.0.1:8000/docs` (Swagger UI)

Key endpoints:
- `GET /regions/` – List all regions
- `GET /annual-visits/parks` – Q2: Annual by park
- `GET /visits/parks/average-monthly` – Q3: Avg monthly
- `GET /visits/peak-season/above-threshold` – Q4: Peak season
- `GET /visits/parks/above-system-average` – Q5: Above average
- `GET /annual-visits/regions` – Q7: By region
- `GET /parks/{park_code}/monthly-visits` – Q1/Q8: Monthly data
- `GET /regions/{region_id}/growth` – Q9: Growth by region
- `GET /visits/parks/variability` – Q10: Variability

## Development Notes

### Adding a New Query

1. **Backend** (`main.py`):
   - Create response model class
   - Add `@app.get()` endpoint
   - Implement SQL query logic

2. **Frontend** (`app.py`):
   - Add query option to `query_options` list
   - Add `elif selected_query == "q#":` block
   - Add session state cache slots for q#_data and q#_meta
   - Implement fetch logic + UI

3. **Session State** (optional caching):
   - Add `"q#_data"` and `"q#_meta"` to initialization loop
   - Save results on fetch: `st.session_state["q#_data"] = df.to_dict(orient="records")`
   - Restore on page reload for sticky results

### Running Tests

No automated tests in current version. Manual testing recommended:
- Test each query with 0, 1, and multiple regions selected
- Verify sorting is by metric value (not region)
- Check park filtering works globally
- Confirm map loads and renders boundaries

## License

Project for IEEE 305 class. Use as needed for educational purposes.

## Contact

For issues or questions, contact the project owner or refer to the git repository.

---

**Last Updated**: December 2025  
**Backend Version**: FastAPI 0.100+  
**Frontend Version**: Streamlit 1.30+
