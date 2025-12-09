from typing import List, Optional
from math import sqrt

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Session, select, func
from sqlalchemy.orm import aliased

from database import get_session
from models import Region, Park, MonthlyVisit


app = FastAPI(title="NPS Visitor Analytics API")

# Allow frontend (Streamlit / HTML/JS) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # OK for class project
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------
# Response models
# -----------------------

class MonthlyThresholdOut(SQLModel):
    month: int
    total_visits: int
    above_threshold: bool


class TopParkOut(SQLModel):
    rank: int
    park_code: str
    park_name: str
    year: int
    annual_total_visits: int


class AnnualParkVisitsOut(SQLModel):
    park_code: str
    park_name: str
    region_id: Optional[str] = None
    region_name: Optional[str] = None
    year: int
    annual_total_visits: int
    state: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class ParkAboveAverageOut(SQLModel):
    """Q5: Parks above system/region average, with context."""
    park_code: str
    park_name: str
    region_id: Optional[str] = None
    region_name: Optional[str] = None
    year: int
    annual_total_visits: int
    system_average_visits: int
    difference_from_average: int
    percent_above_average: int


class RegionAnnualVisitsOut(SQLModel):
    region_id: str
    region_name: str
    year: int
    annual_total_visits: int
    rank: int


class AvgMonthlyVisitsOut(SQLModel):
    park_code: str
    park_name: str
    region_id: Optional[str] = None
    region_name: Optional[str] = None
    start_year: int
    end_year: int
    avg_monthly_visits: int


class MonthToMonthChangeOut(SQLModel):
    month: int
    total_visits: int
    change_from_previous: Optional[int]


class GrowthOut(SQLModel):
    park_code: str
    park_name: str
    region_id: str
    region_name: str
    start_year: int
    end_year: int
    start_total: int
    end_total: int
    growth_percent: int


class VariabilityOut(SQLModel):
    park_code: str
    park_name: str
    region_id: Optional[str] = None
    region_name: Optional[str] = None
    year: int
    avg_monthly_visits: int
    std_dev_monthly_visits: int
    months_with_data: int


class MetricParkOut(SQLModel):
    park_code: str
    park_name: str
    region_id: Optional[str] = None
    region_name: Optional[str] = None
    year: int
    metric_total: int


class ParkDetailOut(SQLModel):
    """Full park details including description, website, and boundary."""
    park_code: str
    park_name: str
    state: str
    designation: str
    region_id: Optional[str] = None
    region_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    website: Optional[str] = None
    boundary: Optional[str] = None  # GeoJSON as string


# -----------------------
# Helper / utility
# -----------------------


@app.get("/metadata/years", summary="Get min and max year available in monthly_visit table")
def get_available_years(session: Session = Depends(get_session)):
    """Return the minimum and maximum year present in `monthly_visit`.

    This allows the frontend to build dynamic year selectors that match the
    data loaded into the database.
    """
    row = session.exec(select(func.min(MonthlyVisit.year), func.max(MonthlyVisit.year))).first()
    if not row or row[0] is None:
        raise HTTPException(status_code=404, detail="No year data available")
    min_year, max_year = row[0], row[1]
    return {"min_year": int(min_year), "max_year": int(max_year)}


@app.get("/regions/", response_model=List[Region], summary="List all NPS regions")
def list_regions(session: Session = Depends(get_session)):
    """
    Helper: list all regions (not one of the 10 queries, but useful for dropdowns).
    """
    stmt = select(Region).order_by(Region.region_id)
    return session.exec(stmt).all()


@app.get("/parks/{park_code}/details", response_model=ParkDetailOut, summary="Get full park details")
def get_park_details(park_code: str, session: Session = Depends(get_session)):
    """
    Get complete park information including description, website, and boundary GeoJSON.
    Used for displaying park details and boundaries on the map.
    """
    park_code = park_code.upper()
    
    stmt = (
        select(Park, Region)
        .join(Region, Region.region_id == Park.region_id, isouter=True)
        .where(Park.park_code == park_code)
    )
    
    result = session.exec(stmt).first()
    if not result:
        raise HTTPException(status_code=404, detail=f"Park {park_code} not found")
    
    park, region = result
    
    return ParkDetailOut(
        park_code=park.park_code,
        park_name=park.park_name,
        state=park.state,
        designation=park.designation,
        region_id=region.region_id if region else None,
        region_name=region.region_name if region else None,
        latitude=park.latitude,
        longitude=park.longitude,
        description=park.description,
        website=park.website,
        boundary=park.boundary,
    )


# -----------------------
# Q1: Monthly visits + threshold for a park/year
# -----------------------

@app.get(
    "/parks/{park_code}/monthly-visits",
    response_model=List[MonthlyThresholdOut],
    summary="Q1: Monthly total visits for a park & year, with threshold flag",
)
def park_monthly_visits_with_threshold(
    park_code: str,
    year: int,
    threshold: int = 0,
    session: Session = Depends(get_session),
):
    """
    Q1 – Business question:
    For a given park and year, what are the monthly total visits,
    and which months exceed a chosen demand threshold?

    SQL concepts: WHERE filter, ORDER BY.
    """
    park_code = park_code.upper()  # case-insensitive input

    stmt = (
        select(MonthlyVisit.month, MonthlyVisit.total_visits)
        .where(
            MonthlyVisit.park_code == park_code,
            MonthlyVisit.year == year,
        )
        .order_by(MonthlyVisit.month)
    )

    rows = session.exec(stmt).all()

    if not rows:
        raise HTTPException(status_code=404, detail="No visits for that park/year")

    out: List[MonthlyThresholdOut] = []
    for month, total in rows:
        total_int = int(total or 0)
        out.append(
            MonthlyThresholdOut(
                month=month,
                total_visits=total_int,
                above_threshold=total_int >= threshold,
            )
        )
    return out


# -----------------------
# Q2: Annual visits by park (with optional filters)
# -----------------------

@app.get(
    "/annual-visits/parks",
    response_model=List[AnnualParkVisitsOut],
    summary="Q2: Annual total visits per park for a given year (with optional filters)",
)
def annual_visits_by_park(
    year: int,
    region_id: Optional[str] = None,
    park_code: Optional[str] = None,
    query: Optional[str] = None,
    min_total: Optional[int] = None,
    limit: int = 100,
    session: Session = Depends(get_session),
):
    """
    Q2 – Business question:
      For a selected year, list all parks with their region names
      and total annual visits.

    Optional filters:
      - region_id: limit to a region
      - park_code: exact park code
      - query: partial park name search
      - min_total: minimum annual visits threshold (HAVING)
      - limit: max results (default 100)

    SQL concepts: 3-table JOIN (region–park–monthly_visit),
    aggregation with SUM, GROUP BY, HAVING, parameterized filters.
    """
    if region_id is not None:
        region_id = region_id.upper()
    if park_code is not None:
        park_code = park_code.upper()

    stmt = (
        select(
            Park.park_code,
            Park.park_name,
            Park.state,
            Park.latitude,
            Park.longitude,
            Region.region_id,
            Region.region_name,
            MonthlyVisit.year,
            func.sum(MonthlyVisit.total_visits).label("annual_total"),
        )
        .join(MonthlyVisit, MonthlyVisit.park_code == Park.park_code)
        .join(Region, Region.region_id == Park.region_id, isouter=True)
        .where(MonthlyVisit.year == year)
        .group_by(
            Park.park_code,
            Park.park_name,
            Park.state,
            Park.latitude,
            Park.longitude,
            Region.region_id,
            Region.region_name,
            MonthlyVisit.year,
        )
    )

    if region_id is not None:
        stmt = stmt.where(Region.region_id == region_id)

    # Filter by exact park code if provided
    if park_code is not None:
        stmt = stmt.where(Park.park_code == park_code)
    # Filter by partial park name if provided
    elif query is not None:
        stmt = stmt.where(Park.park_name.ilike(f"%{query}%"))

    if min_total is not None:
        stmt = stmt.having(func.sum(MonthlyVisit.total_visits) >= min_total)

    stmt = stmt.order_by(func.sum(MonthlyVisit.total_visits).desc()).limit(limit)

    rows = session.exec(stmt).all()

    out: List[AnnualParkVisitsOut] = []
    for park_code, park_name, state, latitude, longitude, reg_id, reg_name, y, annual_total in rows:
        out.append(
            AnnualParkVisitsOut(
                park_code=park_code,
                park_name=park_name,
                state=state,
                latitude=latitude,
                longitude=longitude,
                region_id=reg_id,
                region_name=reg_name,
                year=y,
                annual_total_visits=int(annual_total or 0),
            )
        )
    return out


# -----------------------
# Q3: Average monthly visits per park over a year range
# -----------------------

@app.get(
    "/visits/parks/average-monthly",
    response_model=List[AvgMonthlyVisitsOut],
    summary="Q3: Average monthly total visits per park over a year range",
)
def average_monthly_visits_by_park(
    start_year: int,
    end_year: int,
    region_id: Optional[str] = None,
    park_code: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 100,
    session: Session = Depends(get_session),
):
    """
    Q3 – Business question:
    What is the average monthly total visitation for each park over a selected
    multi-year period (e.g., 2022–2024)?

    Optional filters:
      - park_code: exact park code (e.g., GRCA)
      - query: partial park name search (e.g., "grand")
      - limit: max results to return (default 100)

    SQL concepts: AVG aggregation, GROUP BY, WHERE year BETWEEN.
    """
    if start_year > end_year:
        raise HTTPException(status_code=400, detail="start_year must be <= end_year")

    if region_id is not None:
        region_id = region_id.upper()
    if park_code is not None:
        park_code = park_code.upper()

    stmt = (
        select(
            Park.park_code,
            Park.park_name,
            Region.region_id,
            Region.region_name,
            func.avg(MonthlyVisit.total_visits).label("avg_monthly"),
        )
        .join(MonthlyVisit, MonthlyVisit.park_code == Park.park_code)
        .join(Region, Region.region_id == Park.region_id, isouter=True)
        .where(MonthlyVisit.year.between(start_year, end_year))
        .group_by(
            Park.park_code,
            Park.park_name,
            Region.region_id,
            Region.region_name,
        )
        .order_by(func.avg(MonthlyVisit.total_visits).desc())
    )

    if region_id is not None:
        stmt = stmt.where(Region.region_id == region_id)

    # Filter by exact park code if provided
    if park_code is not None:
        stmt = stmt.where(Park.park_code == park_code)
    # Filter by partial park name if provided
    elif query is not None:
        stmt = stmt.where(Park.park_name.ilike(f"%{query}%"))

    # Apply limit for pagination
    stmt = stmt.limit(limit)

    rows = session.exec(stmt).all()

    out: List[AvgMonthlyVisitsOut] = []
    for park_code, park_name, reg_id, reg_name, avg_monthly in rows:
        avg_int = int(round(avg_monthly or 0))
        out.append(
            AvgMonthlyVisitsOut(
                park_code=park_code,
                park_name=park_name,
                region_id=reg_id,
                region_name=reg_name,
                start_year=start_year,
                end_year=end_year,
                avg_monthly_visits=avg_int,
            )
        )
    return out


# -----------------------
# Q4: Peak-season (Jun–Aug) average above threshold
# -----------------------

@app.get(
    "/visits/peak-season/above-threshold",
    response_model=List[AvgMonthlyVisitsOut],
    summary="Q4: Parks with peak-season (Jun–Aug) average monthly visits above threshold",
)
def peak_season_above_threshold(
    year: int,
    threshold: int,
    region_id: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """
    Q4 – Business question:
    Which parks have an average peak-season (June–August) monthly visitation
    above a specified threshold?

    SQL concepts: WHERE for months, AVG aggregation, GROUP BY, HAVING.
    """
    if region_id is not None:
        region_id = region_id.upper()

    stmt = (
        select(
            Park.park_code,
            Park.park_name,
            Region.region_id,
            Region.region_name,
            func.avg(MonthlyVisit.total_visits).label("avg_monthly"),
        )
        .join(MonthlyVisit, MonthlyVisit.park_code == Park.park_code)
        .join(Region, Region.region_id == Park.region_id, isouter=True)
        .where(
            MonthlyVisit.year == year,
            MonthlyVisit.month.in_([6, 7, 8]),
        )
        .group_by(
            Park.park_code,
            Park.park_name,
            Region.region_id,
            Region.region_name,
        )
        .having(func.avg(MonthlyVisit.total_visits) >= threshold)
        .order_by(func.avg(MonthlyVisit.total_visits).desc())
    )

    if region_id is not None:
        stmt = stmt.where(Region.region_id == region_id)

    rows = session.exec(stmt).all()

    out: List[AvgMonthlyVisitsOut] = []
    for park_code, park_name, reg_id, reg_name, avg_monthly in rows:
        avg_int = int(round(avg_monthly or 0))
        out.append(
            AvgMonthlyVisitsOut(
                park_code=park_code,
                park_name=park_name,
                region_id=reg_id,
                region_name=reg_name,
                start_year=year,
                end_year=year,
                avg_monthly_visits=avg_int,
            )
        )
    return out


# -----------------------
# Q5: Parks above system-wide (or region-wide) average annual visits
# -----------------------

@app.get(
    "/visits/parks/above-system-average",
    response_model=List[ParkAboveAverageOut],
    summary="Q5: Parks with annual visits above system-wide (or region) average in a given year",
)
def parks_above_system_average(
    year: int,
    region_id: Optional[str] = None,
    park_code: Optional[str] = None,
    query: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """
    Q5 – Business question:
    Which parks have total annual visits greater than the system-wide
    average annual visits in the same year?

    If region_id is provided, compute the average within that region only.
    
    Optional: Filter by park_code (exact) or query (partial park name search).

    Returns each park with the system average, difference, and percent above average.

    SQL concepts: subquery-style aggregation, aggregation, GROUP BY, HAVING.
    """
    if region_id is not None:
        region_id = region_id.upper()

    # 1) Get annual totals per park
    annual_totals_stmt = (
        select(func.sum(MonthlyVisit.total_visits).label("annual_total"))
        .join(Park, Park.park_code == MonthlyVisit.park_code)
        .where(MonthlyVisit.year == year)
    )

    if region_id is not None:
        annual_totals_stmt = annual_totals_stmt.where(Park.region_id == region_id)

    annual_totals_stmt = annual_totals_stmt.group_by(MonthlyVisit.park_code)

    # When selecting only an aggregate, results are scalars, not rows
    annual_totals = session.exec(annual_totals_stmt).all()

    if not annual_totals:
        raise HTTPException(status_code=404, detail="No data for that year/filters")

    overall_avg = int(round(sum(annual_totals) / len(annual_totals)))

    # 2) Get parks whose annual total > overall_avg
    stmt = (
        select(
            Park.park_code,
            Park.park_name,
            Region.region_id,
            Region.region_name,
            MonthlyVisit.year,
            func.sum(MonthlyVisit.total_visits).label("annual_total"),
        )
        .join(MonthlyVisit, MonthlyVisit.park_code == Park.park_code)
        .join(Region, Region.region_id == Park.region_id, isouter=True)
        .where(MonthlyVisit.year == year)
        .group_by(
            Park.park_code,
            Park.park_name,
            Region.region_id,
            Region.region_name,
            MonthlyVisit.year,
        )
        .having(func.sum(MonthlyVisit.total_visits) > overall_avg)
        .order_by(func.sum(MonthlyVisit.total_visits).desc())
    )

    if region_id is not None:
        stmt = stmt.where(Region.region_id == region_id)

    # Apply optional park filtering
    if park_code is not None:
        stmt = stmt.where(Park.park_code == park_code.upper())
    elif query is not None:
        stmt = stmt.where(Park.park_name.ilike(f"%{query}%"))

    rows = session.exec(stmt).all()

    out: List[ParkAboveAverageOut] = []
    for park_code, park_name, reg_id, reg_name, y, annual_total in rows:
        annual_total_int = int(round(annual_total or 0))
        diff = int(round(annual_total_int - overall_avg))
        pct_above = int(round(((annual_total_int - overall_avg) / overall_avg * 100))) if overall_avg > 0 else 0
        out.append(
            ParkAboveAverageOut(
                park_code=park_code,
                park_name=park_name,
                region_id=reg_id,
                region_name=reg_name,
                year=y,
                annual_total_visits=annual_total_int,
                system_average_visits=int(round(overall_avg)),
                difference_from_average=diff,
                percent_above_average=pct_above,
            )
        )
    return out


# -----------------------
# Q6: Top N parks by annual total visits (with optional region filter)
# -----------------------

@app.get(
    "/annual-visits/top",
    response_model=List[TopParkOut],
    summary="Q6: Top N parks by annual total visits for a given year",
)
def top_parks_by_year(
    year: int,
    limit: int = 10,
    region_id: Optional[str] = None,
    query: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """
    Q6 – Business question:
    What are the top N most visited parks in a given year?

    Optional filters:
      - region_id: rank only within that region
      - query: filter to parks matching name
      - limit: number of top parks to return (default 10)

    Returns rank relative to the selected scope (global or region).

    SQL concepts: SUM aggregation, GROUP BY, ORDER BY with LIMIT.
    """
    if region_id is not None:
        region_id = region_id.upper()

    # Build base statement for ranking (without query filter yet)
    rank_stmt = (
        select(
            Park.park_code,
            Park.park_name,
            MonthlyVisit.year,
            func.sum(MonthlyVisit.total_visits).label("annual_total"),
        )
        .join(MonthlyVisit, MonthlyVisit.park_code == Park.park_code)
        .where(MonthlyVisit.year == year)
        .group_by(Park.park_code, Park.park_name, MonthlyVisit.year)
        .order_by(func.sum(MonthlyVisit.total_visits).desc())
    )

    if region_id is not None:
        rank_stmt = rank_stmt.where(Park.region_id == region_id)

    # Get all parks in the scope (for ranking)
    all_ranked = session.exec(rank_stmt).all()

    # Now apply query filter if provided
    filtered_rows = all_ranked
    if query is not None:
        filtered_rows = [
            row for row in all_ranked
            if query.lower() in row[1].lower()  # row[1] is park_name
        ]

    # Limit to requested count
    filtered_rows = filtered_rows[:limit]

    # Build output with rank from all_ranked
    out: List[TopParkOut] = []
    for park_code, park_name, y, annual_total in filtered_rows:
        # Find rank in all_ranked
        rank = next(
            (idx + 1 for idx, row in enumerate(all_ranked) 
             if row[0] == park_code),
            0
        )
        out.append(
            TopParkOut(
                rank=rank,
                park_code=park_code,
                park_name=park_name,
                year=y,
                annual_total_visits=int(annual_total or 0),
            )
        )
    return out


# -----------------------
# Q11: Arbitrary metric totals by park (concessioner_lodging, tent_campers, etc.)
# -----------------------


@app.get(
    "/annual-visits/parks/metrics",
    response_model=List[MetricParkOut],
    summary="Q11: Sum a selected monthly metric per park for a given year",
)
def parks_by_metric(
    year: int,
    metric: str,
    region_id: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_session),
):
    """
    Sum any of the integer monthly fields (e.g., concessioner_lodging,
    concessioner_camping, tent_campers, rv_campers, backcountry,
    nonrecreation_overnight_stays, miscellaneous_overnight_stays) by park
    for a given year. Returns top parks by that metric.
    """
    allowed = {
        "concessioner_lodging": MonthlyVisit.concessioner_lodging,
        "concessioner_camping": MonthlyVisit.concessioner_camping,
        "tent_campers": MonthlyVisit.tent_campers,
        "rv_campers": MonthlyVisit.rv_campers,
        "backcountry": MonthlyVisit.backcountry,
        "nonrecreation_overnight_stays": MonthlyVisit.nonrecreation_overnight_stays,
        "miscellaneous_overnight_stays": MonthlyVisit.miscellaneous_overnight_stays,
    }

    metric_col = allowed.get(metric)
    if metric_col is None:
        raise HTTPException(status_code=400, detail=f"Unsupported metric: {metric}")

    if region_id is not None:
        region_id = region_id.upper()

    stmt = (
        select(
            Park.park_code,
            Park.park_name,
            Region.region_id,
            Region.region_name,
            MonthlyVisit.year,
            func.sum(metric_col).label("metric_total"),
        )
        .join(MonthlyVisit, MonthlyVisit.park_code == Park.park_code)
        .join(Region, Region.region_id == Park.region_id, isouter=True)
        .where(MonthlyVisit.year == year)
        .group_by(Park.park_code, Park.park_name, Region.region_id, Region.region_name, MonthlyVisit.year)
        .order_by(func.sum(metric_col).desc())
        .limit(limit)
    )

    if region_id is not None:
        stmt = stmt.where(Region.region_id == region_id)

    rows = session.exec(stmt).all()

    out: List[MetricParkOut] = []
    for park_code, park_name, reg_id, reg_name, y, metric_total in rows:
        out.append(
            MetricParkOut(
                park_code=park_code,
                park_name=park_name,
                region_id=reg_id,
                region_name=reg_name,
                year=y,
                metric_total=int(metric_total or 0),
            )
        )
    return out


# -----------------------
# Q7: Total annual visits by region (ranked)
# -----------------------

@app.get(
    "/annual-visits/regions",
    response_model=List[RegionAnnualVisitsOut],
    summary="Q7: Total annual visits by region for a given year (ranked)",
)
def annual_visits_by_region(
    year: int,
    region_id: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """
    Q7 – Business question:
    For each region, what is the total annual visitation in a selected year,
    and how do regions rank from highest to lowest?

    Extra: if region_id is provided, show just that region's total.

    SQL concepts: 3-table JOIN (region–park–monthly_visit),
    SUM aggregation, GROUP BY, ORDER BY.
    """
    if region_id is not None:
        region_id = region_id.upper()

    stmt = (
        select(
            Region.region_id,
            Region.region_name,
            MonthlyVisit.year,
            func.sum(MonthlyVisit.total_visits).label("annual_total"),
        )
        .join(Park, Park.region_id == Region.region_id)
        .join(MonthlyVisit, MonthlyVisit.park_code == Park.park_code)
        .where(MonthlyVisit.year == year)
        .group_by(Region.region_id, Region.region_name, MonthlyVisit.year)
        .order_by(func.sum(MonthlyVisit.total_visits).desc())
    )

    if region_id is not None:
        stmt = stmt.where(Region.region_id == region_id)

    rows = session.exec(stmt).all()

    out: List[RegionAnnualVisitsOut] = []
    for idx, (reg_id, reg_name, y, annual_total) in enumerate(rows, start=1):
        out.append(
            RegionAnnualVisitsOut(
                region_id=reg_id,
                region_name=reg_name,
                year=y,
                annual_total_visits=int(annual_total or 0),
                rank=idx,
            )
        )
    return out


# -----------------------
# Q8: Month-to-month change within a year for a park
# -----------------------

@app.get(
    "/parks/{park_code}/month-to-month-change",
    response_model=List[MonthToMonthChangeOut],
    summary="Q8: Month-to-month change in total visits for a park & year",
)
def month_to_month_change(
    park_code: str,
    year: int,
    session: Session = Depends(get_session),
):
    """
    Q8 – Business question:
    For a selected park and year, what is the month-to-month change in
    total visits (to spot sudden spikes/drops)?

    SQL concepts: self-JOIN on monthly_visit, filtering, ORDER BY.
    """
    park_code = park_code.upper()

    m1 = aliased(MonthlyVisit)
    m2 = aliased(MonthlyVisit)

    stmt = (
        select(
            m1.month,
            m1.total_visits,
            (m1.total_visits - func.coalesce(m2.total_visits, 0)).label(
                "change_from_previous"
            ),
        )
        .join(
            m2,
            (m1.park_code == m2.park_code)
            & (m1.year == m2.year)
            & (m1.month == m2.month + 1),
            isouter=True,
        )
        .where(
            m1.park_code == park_code,
            m1.year == year,
        )
        .order_by(m1.month)
    )

    rows = session.exec(stmt).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No visits for that park/year")

    out: List[MonthToMonthChangeOut] = []
    for month, total, change in rows:
        out.append(
            MonthToMonthChangeOut(
                month=month,
                total_visits=int(total or 0),
                change_from_previous=int(change) if change is not None else None,
            )
        )
    return out


# -----------------------
# Q9: Growth in annual visits by park within a region over time window
# -----------------------

@app.get(
    "/regions/{region_id}/growth",
    response_model=List[GrowthOut],
    summary="Q9: Parks with highest % growth in annual visits within a region over a time window",
)
def growth_by_region_over_time(
    region_id: str,
    start_year: int,
    end_year: int,
    session: Session = Depends(get_session),
):
    """
    Q9 – Business question:
    For a given region and time window (e.g., 2022–2024),
    which parks show the highest percentage growth in total annual visitation?

    We interpret growth as:
        (total visits in end_year - total visits in start_year) / total in start_year.

    SQL concepts: JOINs, aggregation, subquery/CTE-like pattern, GROUP BY, ORDER BY.
    """
    if start_year >= end_year:
        raise HTTPException(status_code=400, detail="start_year must be < end_year")

    region_id = region_id.upper()

    # Aggregate annual totals by park & year for the two boundary years
    annual_stmt = (
        select(
            MonthlyVisit.park_code,
            MonthlyVisit.year,
            func.sum(MonthlyVisit.total_visits).label("annual_total"),
        )
        .join(Park, Park.park_code == MonthlyVisit.park_code)
        .where(
            Park.region_id == region_id,
            MonthlyVisit.year.in_([start_year, end_year]),
        )
        .group_by(MonthlyVisit.park_code, MonthlyVisit.year)
    ).subquery()

    start_alias = aliased(annual_stmt)
    end_alias = aliased(annual_stmt)

    # Join start-year and end-year totals per park
    stmt = (
        select(
            Park.park_code,
            Park.park_name,
            Region.region_id,
            Region.region_name,
            start_alias.c.annual_total.label("start_total"),
            end_alias.c.annual_total.label("end_total"),
        )
        .join(Region, Region.region_id == Park.region_id)
        .join(
            start_alias,
            (start_alias.c.park_code == Park.park_code)
            & (start_alias.c.year == start_year),
        )
        .join(
            end_alias,
            (end_alias.c.park_code == Park.park_code)
            & (end_alias.c.year == end_year),
        )
        .where(Region.region_id == region_id)
    )

    rows = session.exec(stmt).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No data for that region/years")

    out: List[GrowthOut] = []
    for park_code, park_name, reg_id, reg_name, start_total, end_total in rows:
        st = int(start_total or 0)
        et = int(end_total or 0)
        if st == 0:
            # avoid division by zero; treat as 0% growth (or you could skip)
            growth_pct = 0
        else:
            growth_pct = int(round((et - st) * 100.0 / st))

        out.append(
            GrowthOut(
                park_code=park_code,
                park_name=park_name,
                region_id=reg_id,
                region_name=reg_name,
                start_year=start_year,
                end_year=end_year,
                start_total=st,
                end_total=et,
                growth_percent=growth_pct,
            )
        )

    # Sort by growth descending
    out.sort(key=lambda x: x.growth_percent, reverse=True)
    return out


# -----------------------
# Q10: Variability of monthly visits (std dev) by park in a year
# -----------------------

@app.get(
    "/visits/parks/variability",
    response_model=List[VariabilityOut],
    summary="Q10: Parks ranked by variability (std dev) of monthly visits in a given year",
)
def park_visit_variability(
    year: int,
    region_id: Optional[str] = None,
    park_code: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 10,
    session: Session = Depends(get_session),
):
    """
    Q10 – Business question:
    For a given year, which parks have the most volatile (variable) monthly
    visitation patterns? This helps identify parks with unstable demand.

    We compute:
        n          = number of months with data
        sum_v      = SUM(total_visits)
        sum_v2     = SUM(total_visits^2)
        mean       = sum_v / n
        variance   = (sum_v2 / n) - (mean^2)
        std_dev    = sqrt(max(variance, 0))

    SQL concepts: SUM, COUNT, GROUP BY; then std dev computed in Python.

    Filters:
      - region_id (optional): limit to parks in a region
      - min_months (default 3): require at least this many months of data
      - limit (default 10): return top N by std dev
    """
    if region_id is not None:
        region_id = region_id.upper()
    if park_code is not None:
        park_code = park_code.upper()


    stmt = (
        select(
            Park.park_code,
            Park.park_name,
            Region.region_id,
            Region.region_name,
            MonthlyVisit.year,
            func.count(MonthlyVisit.month).label("n_months"),
            func.sum(MonthlyVisit.total_visits).label("sum_v"),
            func.sum(
                MonthlyVisit.total_visits * MonthlyVisit.total_visits
            ).label("sum_v2"),
        )
        .join(MonthlyVisit, MonthlyVisit.park_code == Park.park_code)
        .join(Region, Region.region_id == Park.region_id, isouter=True)
        .where(MonthlyVisit.year == year)
        .group_by(
            Park.park_code,
            Park.park_name,
            Region.region_id,
            Region.region_name,
            MonthlyVisit.year,
        )
    )

    if region_id is not None:
        stmt = stmt.where(Region.region_id == region_id)

    # Filter by exact park code or partial park name
    if park_code is not None:
        stmt = stmt.where(Park.park_code == park_code)
    elif query is not None:
        stmt = stmt.where(Park.park_name.ilike(f"%{query}%"))


    rows = session.exec(stmt).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No data for that year/filters")

    results: List[VariabilityOut] = []

    for (
        park_code,
        park_name,
        reg_id,
        reg_name,
        y,
        n_months,
        sum_v,
        sum_v2,
    ) in rows:
        n = int(n_months or 0)

        sum_v = float(sum_v or 0.0)
        sum_v2 = float(sum_v2 or 0.0)

        mean = sum_v / n
        variance = max((sum_v2 / n) - (mean * mean), 0.0)
        std_dev = sqrt(variance)

        results.append(
            VariabilityOut(
                park_code=park_code,
                park_name=park_name,
                region_id=reg_id,
                region_name=reg_name,
                year=y,
                avg_monthly_visits=int(round(mean)),
                std_dev_monthly_visits=int(round(std_dev)),
                months_with_data=n,
            )
        )

    # Sort by variability descending
    results.sort(key=lambda x: x.std_dev_monthly_visits, reverse=True)

    if limit is not None and limit > 0:
        results = results[:limit]

    return results
