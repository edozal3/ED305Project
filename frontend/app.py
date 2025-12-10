import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import folium  # type: ignore
from streamlit_folium import st_folium  # type: ignore
from datetime import datetime

# Configure Streamlit page
st.set_page_config(
    page_title="NPS Park Operations Dashboard",
    page_icon="🏞️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Add keyboard shortcuts via custom JavaScript
st.markdown("""
<script>
document.addEventListener('keydown', function(e) {
    // Ctrl/Cmd + K to focus search
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const searchInput = document.querySelector('input[aria-label="Search parks (global)"]');
        if (searchInput) searchInput.focus();
    }
    // Ctrl/Cmd + Enter to trigger search/load buttons
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        const searchBtn = Array.from(document.querySelectorAll('button')).find(btn => btn.textContent.includes('Search Parks'));
        if (searchBtn) searchBtn.click();
    }
});
</script>
<style>
/* Force content to resize properly when sidebar changes */
.main .block-container {
    max-width: 100%;
}
iframe {
    width: 100% !important;
}
</style>
""", unsafe_allow_html=True)

# API base URL
API_BASE = "http://127.0.0.1:8000"

# -----------------------
# Session State & Cache
# -----------------------

# Initialize session slots for caching query results between tab switches
for _key in [
    "q1_data", "q1_meta",
    "q2_data", "q2_meta",
    "q3_data", "q3_meta",
    "q4_data", "q4_meta",
    "q5_data", "q5_meta",
    "q6_data", "q6_meta",
    "q7_data", "q7_meta",
    "q8_data", "q8_meta",
    "metrics_data", "metrics_meta",
    "q10_data", "q10_meta",
]:
    if _key not in st.session_state:
        st.session_state[_key] = None

@st.cache_data
def fetch_regions():
    """Fetch all regions from API."""
    try:
        resp = requests.get(f"{API_BASE}/regions/")
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to fetch regions: {e}")
        return []


@st.cache_data
def fetch_parks_by_region(region_id, year):
    """Fetch parks in a specific region for a given year."""
    try:
        resp = requests.get(
            f"{API_BASE}/annual-visits/parks",
            params={"year": year, "region_id": region_id, "limit": 500}
        )
        resp.raise_for_status()
        data = resp.json()
        # Extract unique parks (park_code -> park_name)
        parks = list({p["park_code"]: p["park_name"] for p in data}.items())
        return parks
    except Exception as e:
        st.error(f"Failed to fetch parks: {e}")
        return []


@st.cache_data
def fetch_parks_by_query(query, year, limit=50):
    """Fetch parks by partial name or code using the backend search (annual-visits/parks).

    Returns a list of tuples `(park_code, park_name)` suitable for a selectbox.
    """
    if not query:
        return []
    try:
        resp = requests.get(
            f"{API_BASE}/annual-visits/parks",
            params={"year": year, "query": query, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        parks = [(p["park_code"], p["park_name"]) for p in data]
        return parks
    except Exception as e:
        st.error(f"Failed to search parks: {e}")
        return []


# -----------------------
# UI Layout
# -----------------------

st.title("🏞️ NPS Park Operations Dashboard")
st.markdown("Analyze visitor patterns, trends, and park performance across the National Park System.")

# Sidebar controls
st.sidebar.header("⚙️ Global Filters & Options")

# Clear all filters button
if st.sidebar.button("🔄 Clear All Filters", key="clear_filters_btn", help="Reset all filters to defaults"):
    # Clear region selection
    st.session_state.global_regions = []
    # Clear park search and selection
    if "global_matches" in st.session_state:
        st.session_state.global_matches = []
    if "global_selected" in st.session_state:
        st.session_state.global_selected = []
    if "global_search" in st.session_state:
        st.session_state.global_search = ""
    # Clear clicked park on map
    if "clicked_park_code" in st.session_state:
        del st.session_state.clicked_park_code
    st.success("✅ All filters cleared!")
    st.rerun()

@st.cache_data
def fetch_years():
    """Fetch the min/max year available from the backend metadata endpoint."""
    try:
        resp = requests.get(f"{API_BASE}/metadata/years")
        resp.raise_for_status()
        return resp.json()
    except Exception:
        # Fall back to sensible defaults if backend not available yet
        # (project data spans 2015-2024)
        return {"min_year": 2015, "max_year": 2024}


# Region/park/search controls are provided inside each query tab
# to keep the sidebar minimal; regions/options will be fetched below.
regions = fetch_regions()
region_options = {r["region_id"]: r["region_name"] for r in regions}

# Add "All Regions" option
all_region_keys = list(region_options.keys())
region_display_options = ["All Regions"] + all_region_keys

def format_region_func(x):
    if x == "All Regions":
        return "All Regions"
    return region_options.get(x, x)

# Collapsible section for Regions
with st.sidebar.expander("🌎 Regions", expanded=True):
    global_regions_display = st.multiselect(
        "Select regions to filter",
        options=region_display_options,
        format_func=format_region_func,
        key="global_regions",
    )

# Convert display selection to actual region keys
if "All Regions" in global_regions_display:
    global_regions = all_region_keys
else:
    global_regions = global_regions_display

# Collapsible section for Year and Limits
with st.sidebar.expander("📅 Year & Limits", expanded=True):
    years = fetch_years()
    min_year = years.get("min_year", 2015)
    max_year = years.get("max_year", 2024)
    year = st.slider(
        "Select Year",
        min_value=min_year,
        max_value=max_year,
        value=max_year,
        step=1,
    )
    
    limit = st.slider("Results Limit", min_value=1, max_value=100, value=10, step=1)

# Collapsible section for Park Search
with st.sidebar.expander("🔍 Park Search & Selection", expanded=False):
    global_search = st.text_input("Search parks (global)", value="", key="global_search", help="Press Ctrl/Cmd+K to focus")
    col_a, col_b = st.columns([3, 2])
    with col_a:
        if st.button("Search Parks", key="global_search_btn", help="Or press Ctrl/Cmd+Enter"):
            matches = fetch_parks_by_query(global_search, year)
            st.session_state["global_matches"] = matches
    with col_b:
        if st.button("Load Region Parks", key="global_load_region"):
            if global_regions:
                all_matches = []
                for rid in global_regions:
                    try:
                        part = fetch_parks_by_region(rid, year)
                        all_matches.extend(part)
                    except Exception as e:
                        st.warning(f"Failed to load parks for region {rid}: {e}")
                # dedupe by park_code
                seen = set()
                uniq = []
                for code, name in all_matches:
                    if code not in seen:
                        seen.add(code)
                        uniq.append((code, name))
                st.session_state["global_matches"] = uniq
                if uniq:
                    st.success(f"Loaded {len(uniq)} parks from {len(global_regions)} region(s)")
            else:
                st.warning("Select one or more regions first (Global Filters).")
    
    global_matches = st.session_state.get("global_matches", [])
    global_selected = st.multiselect(
        "Selected Parks",
        options=global_matches,
        format_func=lambda x: f"{x[1]} ({x[0]})",
        key="global_selected",
    )

selected_park_codes = [p[0] for p in global_selected] if global_selected else []

# Ensure limit and year are integers
limit = int(limit)
year = int(year)

st.sidebar.markdown("---")
st.sidebar.markdown("**Data Source:** National Park Service API")

# -----------------------
# Main Content
# -----------------------

query_options = [
    ("Q1: Monthly Visits", "q1"),
    ("Q2: Annual by Park", "q2"),
    ("Q3: Avg Monthly", "q3"),
    ("Q4: Peak Season", "q4"),
    ("Q5: Above Average", "q5"),
    ("Q6: Top Parks", "q6"),
    ("Q7: By Region", "q7"),
    ("Q8: Month-to-Month", "q8"),
    ("Q9: Growth", "q9"),
    ("Q10: Variability", "q10"),
    ("Metrics", "metrics"),
]

# Main content: Query selector and Interactive Map tab
tab_main, tab_map = st.tabs(["Queries", "Interactive Map"])

with tab_main:
    query_label_to_key = {label: key for label, key in query_options}
    query_labels = [label for label, _ in query_options]
    selected_query_label = st.selectbox("Select Query", options=query_labels, key="query_select")
    selected_query = query_label_to_key[selected_query_label]

    # Only show the selected query's controls/results
    if selected_query == "q1":
        # ...existing code for Q1 (was: with tabs[0]: ...)
        st.subheader("Q1: Monthly Total Visits for a Park (search & compare)")
        st.markdown("📊 Compare monthly visitor trends for a specific park across multiple years. Shows how visitor numbers fluctuate throughout the year and across different time periods.")
        park_search = st.text_input("Search for a park", value="", key="q1_search")
        park_matches = []
        if park_search:
            park_matches = fetch_parks_by_query(park_search, year, limit=20)
        
        if park_matches:
            selected_park = st.selectbox(
                "Select a park from search results:",
                options=park_matches,
                format_func=lambda x: f"{x[1]} ({x[0]})",
                key="q1_selected",
            )
            park_code = selected_park[0]
        else:
            park_code = None
            if park_search:
                st.info("No parks found matching that search.")
        
        years_list = list(range(min_year, max_year + 1))
        selected_years = st.multiselect(
            "Select Years to Compare",
            options=years_list,
            default=[year],
            format_func=lambda x: str(x),
            key="q1_years",
        )
        clicked_q1 = st.button("Fetch Q1 Data", key="btn_q1_fetch")
        if clicked_q1:
            if not park_code:
                st.warning("Please search for and select a park first.")
            elif not selected_years:
                st.warning("Please select one or more years to compare.")
            else:
                combined = []
                for y in selected_years:
                    try:
                        resp = requests.get(
                            f"{API_BASE}/parks/{park_code}/monthly-visits",
                            params={"year": int(y)},
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        if not data:
                            st.warning(f"No data for {park_code} in {y}")
                            continue
                        dfy = pd.DataFrame(data)
                        dfy["year"] = int(y)
                        combined.append(dfy)
                    except Exception as e:
                        st.error(f"Error fetching {park_code} {y}: {e}")
                if not combined:
                    st.warning("No data fetched for selected years.")
                else:
                    df_all = pd.concat(combined, ignore_index=True)
                    pivot = df_all.pivot_table(values="total_visits", index="month", columns="year", aggfunc="sum").fillna(0).astype(int)
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**Monthly Visits by Year**")
                        st.dataframe(pivot, use_container_width=True)
                    with col2:
                        fig = px.line(
                            df_all,
                            x="month",
                            y="total_visits",
                            color="year",
                            markers=True,
                            title=f"Monthly Visits - {park_code} ({', '.join(map(str, selected_years))})",
                            labels={"month": "Month", "total_visits": "Total Visits", "year": "Year"},
                        )
                        st.plotly_chart(fig, width='stretch')
                    st.session_state["q1_data"] = df_all.to_dict(orient="records")
                    st.session_state["q1_meta"] = {"park_code": park_code, "park_name": selected_park[1] if park_matches else "", "years": list(selected_years)}
        elif st.session_state.get("q1_data"):
            meta = st.session_state.get("q1_meta", {})
            park_label = meta.get("park_name") or meta.get("park_code", "")
            years_list = meta.get("years", [])
            st.info(f"Showing last Q1 results ({park_label} | Years: {', '.join(map(str, years_list))})")
            df_all = pd.DataFrame(st.session_state["q1_data"])
            pivot = df_all.pivot_table(values="total_visits", index="month", columns="year", aggfunc="sum").fillna(0).astype(int)
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Monthly Visits by Year**")
                st.dataframe(pivot, use_container_width=True)
            with col2:
                fig = px.line(
                    df_all,
                    x="month",
                    y="total_visits",
                    color="year",
                    markers=True,
                    title=f"Monthly Visits - {park_label} ({', '.join(map(str, years_list))})",
                    labels={"month": "Month", "total_visits": "Total Visits", "year": "Year"},
                )
                st.plotly_chart(fig, width='stretch')
    elif selected_query == "q2":
        st.subheader("Q2: Annual Total Visits by Park")
        st.markdown("📈 See the total number of visitors each park received in a single year. Perfect for identifying which parks attract the most visitors.")
        clicked_q2 = st.button("Fetch Q2 Data", key="btn_q2")
        if clicked_q2:
            try:
                params = {"year": year, "limit": limit}
                if not global_regions:
                    resp = requests.get(f"{API_BASE}/annual-visits/parks", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                elif len(global_regions) == 1:
                    params["region_id"] = global_regions[0]
                    resp = requests.get(f"{API_BASE}/annual-visits/parks", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                else:
                    combined = []
                    for rid in global_regions:
                        p = params.copy()
                        p["region_id"] = rid
                        resp = requests.get(f"{API_BASE}/annual-visits/parks", params=p)
                        resp.raise_for_status()
                        combined.extend(resp.json())
                    data = combined
                
                if data:
                    df = pd.DataFrame(data)
                    if selected_park_codes:
                        df = df[df["park_code"].isin(selected_park_codes)]
                    # Sort by the metric (descending) to mix regions
                    df = df.sort_values("annual_total_visits", ascending=False)
                    # Apply limit to final results for multi-region queries
                    if len(global_regions) > 1:
                        df = df.head(limit)
                    display_cols = [col for col in ["park_name", "region_name", "annual_total_visits"] if col in df.columns]
                    st.dataframe(df[display_cols], use_container_width=True)
                    fig = px.bar(
                        df.head(20),
                        x="park_name",
                        y="annual_total_visits",
                        title="Top Parks by Annual Visits",
                        labels={"park_name": "Park", "annual_total_visits": "Annual Visits"},
                    )
                    st.plotly_chart(fig, width='stretch')
                    st.session_state["q2_data"] = df.to_dict(orient="records")
                    st.session_state["q2_meta"] = {"year": year, "regions": list(global_regions), "limit": limit}
                else:
                    st.warning("No data found.")
            except Exception as e:
                st.error(f"Error: {e}")
        elif st.session_state.get("q2_data"):
            meta = st.session_state.get("q2_meta", {})
            st.info(f"Showing last Q2 results (Year {meta.get('year', year)}, Regions: {', '.join(meta.get('regions', [])) or 'All'}, Limit: {meta.get('limit', limit)})")
            df = pd.DataFrame(st.session_state["q2_data"])
            if selected_park_codes:
                df = df[df["park_code"].isin(selected_park_codes)]
            display_cols = [col for col in ["park_name", "region_name", "annual_total_visits"] if col in df.columns]
            st.dataframe(df[display_cols], use_container_width=True)
            fig = px.bar(
                df.head(20),
                x="park_name",
                y="annual_total_visits",
                title="Top Parks by Annual Visits",
                labels={"park_name": "Park", "annual_total_visits": "Annual Visits"},
            )
            st.plotly_chart(fig, width='stretch')
    elif selected_query == "q3":
        st.subheader("Q3: Average Monthly Visits Over Year Range")
        st.markdown("📅 Calculate the average monthly visitor count for parks across a range of years. Useful for understanding typical monthly traffic patterns.")
        col1, col2 = st.columns(2)
        with col1:
            start_year = st.number_input(
                "Start Year",
                value=min_year,
                min_value=min_year,
                max_value=max_year,
            )
        with col2:
            end_year = st.number_input(
                "End Year",
                value=max_year,
                min_value=min_year,
                max_value=max_year,
            )
        clicked_q3 = st.button("Fetch Q3 Data", key="btn_q3")
        if clicked_q3:
            try:
                params = {
                    "start_year": int(start_year),
                    "end_year": int(end_year),
                    "limit": limit,
                }
                if not global_regions:
                    resp = requests.get(f"{API_BASE}/visits/parks/average-monthly", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                elif len(global_regions) == 1:
                    params["region_id"] = global_regions[0]
                    resp = requests.get(f"{API_BASE}/visits/parks/average-monthly", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                else:
                    combined = []
                    for rid in global_regions:
                        p = params.copy()
                        p["region_id"] = rid
                        resp = requests.get(f"{API_BASE}/visits/parks/average-monthly", params=p)
                        resp.raise_for_status()
                        combined.extend(resp.json())
                    data = combined
                
                if data:
                    df = pd.DataFrame(data)
                    if selected_park_codes:
                        df = df[df["park_code"].isin(selected_park_codes)]
                    # Sort by the metric (descending) to mix regions
                    df = df.sort_values("avg_monthly_visits", ascending=False)
                    # Apply limit to final results for multi-region queries
                    if len(global_regions) > 1:
                        df = df.head(limit)
                    display_cols = [col for col in ["park_name", "region_name", "avg_monthly_visits"] if col in df.columns]
                    st.dataframe(df[display_cols], use_container_width=True)
                    fig = px.bar(
                        df.head(15),
                        x="park_name",
                        y="avg_monthly_visits",
                        title="Avg Monthly Visits",
                        labels={"park_name": "Park", "avg_monthly_visits": "Avg Monthly Visits"},
                    )
                    st.plotly_chart(fig, width='stretch')
                    st.session_state["q3_data"] = df.to_dict(orient="records")
                    st.session_state["q3_meta"] = {"start_year": int(start_year), "end_year": int(end_year), "regions": list(global_regions), "limit": limit}
                else:
                    st.warning("No data found.")
            except Exception as e:
                st.error(f"Error: {e}")
        elif st.session_state.get("q3_data"):
            meta = st.session_state.get("q3_meta", {})
            st.info(
                f"Showing last Q3 results (Years {meta.get('start_year', start_year)}-{meta.get('end_year', end_year)}, Regions: {', '.join(meta.get('regions', [])) or 'All'}, Limit: {meta.get('limit', limit)})"
            )
            df = pd.DataFrame(st.session_state["q3_data"])
            if selected_park_codes:
                df = df[df["park_code"].isin(selected_park_codes)]
            display_cols = [col for col in ["park_name", "region_name", "avg_monthly_visits"] if col in df.columns]
            st.dataframe(df[display_cols], use_container_width=True)
            fig = px.bar(
                df.head(15),
                x="park_name",
                y="avg_monthly_visits",
                title="Avg Monthly Visits",
                labels={"park_name": "Park", "avg_monthly_visits": "Avg Monthly Visits"},
            )
            st.plotly_chart(fig, width='stretch')
    elif selected_query == "q4":
        st.subheader("Q4: Peak Season (Jun-Aug) Above Threshold")
        st.markdown("⛰️ Find parks that exceed a visitor threshold during peak summer season (June-August). Identifies high-traffic parks when tourism peaks.")
        threshold = st.number_input(
            "Avg Monthly Visits Threshold",
            value=100000,
            step=10000,
        )
        clicked_q4 = st.button("Fetch Q4 Data", key="btn_q4")
        if clicked_q4:
            try:
                params = {
                    "year": year,
                    "threshold": int(threshold),
                    "limit": limit,
                }
                if not global_regions:
                    resp = requests.get(f"{API_BASE}/visits/peak-season/above-threshold", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                elif len(global_regions) == 1:
                    params["region_id"] = global_regions[0]
                    resp = requests.get(f"{API_BASE}/visits/peak-season/above-threshold", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                else:
                    combined = []
                    for rid in global_regions:
                        p = params.copy()
                        p["region_id"] = rid
                        resp = requests.get(f"{API_BASE}/visits/peak-season/above-threshold", params=p)
                        resp.raise_for_status()
                        combined.extend(resp.json())
                    data = combined
                
                if data:
                    df = pd.DataFrame(data)
                    if selected_park_codes:
                        df = df[df["park_code"].isin(selected_park_codes)]
                    # Sort by the metric (descending) to mix regions
                    df = df.sort_values("avg_monthly_visits", ascending=False)
                    # Apply limit to final results for multi-region queries
                    if len(global_regions) > 1:
                        df = df.head(limit)
                    display_cols = [col for col in ["park_name", "region_name", "avg_monthly_visits"] if col in df.columns]
                    st.dataframe(df[display_cols], use_container_width=True)
                    st.session_state["q4_data"] = df.to_dict(orient="records")
                    st.session_state["q4_meta"] = {"year": year, "threshold": int(threshold), "regions": list(global_regions), "limit": limit}
                else:
                    st.info("No parks exceed the threshold in peak season.")
            except Exception as e:
                st.error(f"Error: {e}")
        elif st.session_state.get("q4_data"):
            meta = st.session_state.get("q4_meta", {})
            st.info(
                f"Showing last Q4 results (Year {meta.get('year', year)}, Threshold {meta.get('threshold', threshold)}, Regions: {', '.join(meta.get('regions', [])) or 'All'}, Limit: {meta.get('limit', limit)})"
            )
            df = pd.DataFrame(st.session_state["q4_data"])
            if selected_park_codes:
                df = df[df["park_code"].isin(selected_park_codes)]
            display_cols = [col for col in ["park_name", "region_name", "avg_monthly_visits"] if col in df.columns]
            st.dataframe(df[display_cols], use_container_width=True)
    elif selected_query == "q5":
        st.subheader("Q5: Parks Above System/Region Average")
        st.markdown("⭐ Identify parks that attract more visitors than the average park in their region or the entire system. Great for recognizing popular parks.")
        clicked_q5 = st.button("Fetch Q5 Data", key="btn_q5")
        if clicked_q5:
            try:
                params = {"year": year, "limit": limit}
                if not global_regions:
                    resp = requests.get(f"{API_BASE}/visits/parks/above-system-average", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                elif len(global_regions) == 1:
                    params["region_id"] = global_regions[0]
                    resp = requests.get(f"{API_BASE}/visits/parks/above-system-average", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                else:
                    combined = []
                    for rid in global_regions:
                        p = params.copy()
                        p["region_id"] = rid
                        resp = requests.get(f"{API_BASE}/visits/parks/above-system-average", params=p)
                        resp.raise_for_status()
                        combined.extend(resp.json())
                    data = combined
                
                if data:
                    df = pd.DataFrame(data)
                    if selected_park_codes:
                        df = df[df["park_code"].isin(selected_park_codes)]
                    # Sort by the metric (descending) to mix regions
                    df = df.sort_values("annual_total_visits", ascending=False)
                    # Apply limit to final results
                    df = df.head(limit)
                    display_cols = [col for col in ["park_name", "region_name", "annual_total_visits", "percent_above_average"] if col in df.columns]
                    st.dataframe(df[display_cols], use_container_width=True)
                    fig = px.scatter(
                        df,
                        x="annual_total_visits",
                        y="percent_above_average",
                        hover_data=["park_name"],
                        title="Parks Above Average (% Above vs Total Visits)",
                        labels={"percent_above_average": "% Above Average"},
                    )
                    st.plotly_chart(fig, width='stretch')
                    st.session_state["q5_data"] = df.to_dict(orient="records")
                    st.session_state["q5_meta"] = {"year": year, "regions": list(global_regions), "limit": limit}
            except Exception as e:
                st.error(f"Error: {e}")
        elif st.session_state.get("q5_data"):
            meta = st.session_state.get("q5_meta", {})
            st.info(
                f"Showing last Q5 results (Year {meta.get('year', year)}, Regions: {', '.join(meta.get('regions', [])) or 'All'}, Limit: {meta.get('limit', limit)})"
            )
            df = pd.DataFrame(st.session_state["q5_data"])
            if selected_park_codes:
                df = df[df["park_code"].isin(selected_park_codes)]
            display_cols = [col for col in ["park_name", "region_name", "annual_total_visits", "percent_above_average"] if col in df.columns]
            st.dataframe(df[display_cols], use_container_width=True)
            fig = px.scatter(
                df,
                x="annual_total_visits",
                y="percent_above_average",
                hover_data=["park_name"],
                title="Parks Above Average (% Above vs Total Visits)",
                labels={"percent_above_average": "% Above Average"},
            )
            st.plotly_chart(fig, width='stretch')

    elif selected_query == "q6":
        st.subheader("Q6: Top Parks by Annual Visits")
        st.markdown("🏆 Rank parks by total annual visitors to see which parks are the most visited.")
        clicked_q6 = st.button("Fetch Q6 Data", key="btn_q6")
        if clicked_q6:
            try:
                params = {"year": year, "limit": limit}
                if not global_regions:
                    resp = requests.get(f"{API_BASE}/annual-visits/parks", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                elif len(global_regions) == 1:
                    params["region_id"] = global_regions[0]
                    resp = requests.get(f"{API_BASE}/annual-visits/parks", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                else:
                    combined = []
                    for rid in global_regions:
                        p = params.copy()
                        p["region_id"] = rid
                        resp = requests.get(f"{API_BASE}/annual-visits/parks", params=p)
                        resp.raise_for_status()
                        combined.extend(resp.json())
                    data = combined
                
                if data:
                    df = pd.DataFrame(data)
                    if selected_park_codes:
                        df = df[df["park_code"].isin(selected_park_codes)]
                    # Sort by the metric (descending) to mix regions
                    df = df.sort_values("annual_total_visits", ascending=False)
                    # Apply limit to final results for multi-region queries
                    if len(global_regions) > 1:
                        df = df.head(limit)
                    display_cols = [col for col in ["park_name", "region_name", "annual_total_visits"] if col in df.columns]
                    st.dataframe(df[display_cols], use_container_width=True)
                    fig = px.bar(
                        df.head(20),
                        x="park_name",
                        y="annual_total_visits",
                        title="Top Parks by Annual Visits",
                        labels={"park_name": "Park", "annual_total_visits": "Annual Visits"},
                    )
                    st.plotly_chart(fig, width='stretch')
                    st.session_state["q6_data"] = df.to_dict(orient="records")
                    st.session_state["q6_meta"] = {"year": year, "regions": list(global_regions), "limit": limit}
                else:
                    st.warning("No data found.")
            except Exception as e:
                st.error(f"Error: {e}")
        elif st.session_state.get("q6_data"):
            meta = st.session_state.get("q6_meta", {})
            st.info(
                f"Showing last Q6 results (Year {meta.get('year', year)}, Regions: {', '.join(meta.get('regions', [])) or 'All'}, Limit: {meta.get('limit', limit)})"
            )
            df = pd.DataFrame(st.session_state["q6_data"])
            if selected_park_codes:
                df = df[df["park_code"].isin(selected_park_codes)]
            display_cols = [col for col in ["park_name", "region_name", "annual_total_visits"] if col in df.columns]
            st.dataframe(df[display_cols], use_container_width=True)
            fig = px.bar(
                df.head(20),
                x="park_name",
                y="annual_total_visits",
                title="Top Parks by Annual Visits",
                labels={"park_name": "Park", "annual_total_visits": "Annual Visits"},
            )
            st.plotly_chart(fig, width='stretch')
    
    elif selected_query == "q7":
        st.subheader("Q7: Annual Visits by Region (Ranked)")
        st.markdown("🗺️ Compare total visitor numbers across all NPS regions. See which regions attract the most visitation and understand geographic distribution of visitors.")
        clicked_q7 = st.button("Fetch Q7 Data", key="btn_q7")
        if clicked_q7:
            try:
                if not global_regions:
                    params = {"year": year}
                    resp = requests.get(f"{API_BASE}/annual-visits/regions", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                elif len(global_regions) == 1:
                    params = {"year": year, "region_id": global_regions[0]}
                    resp = requests.get(f"{API_BASE}/annual-visits/regions", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                else:
                    combined = []
                    for rid in global_regions:
                        params = {"year": year, "region_id": rid}
                        resp = requests.get(f"{API_BASE}/annual-visits/regions", params=params)
                        resp.raise_for_status()
                        combined.extend(resp.json())
                    data = combined
                
                if data:
                    df = pd.DataFrame(data)
                    # Sort by the metric (descending) to mix regions
                    df = df.sort_values("annual_total_visits", ascending=False)
                    st.dataframe(df, use_container_width=True)
                    fig = px.pie(
                        df,
                        names="region_name",
                        values="annual_total_visits",
                        title="Regional Visit Distribution",
                    )
                    st.plotly_chart(fig, width='stretch')
                    st.session_state["q7_data"] = df.to_dict(orient="records")
                    st.session_state["q7_meta"] = {"year": year, "regions": list(global_regions)}
                else:
                    st.warning("No data found.")
            except Exception as e:
                st.error(f"Error: {e}")
        elif st.session_state.get("q7_data"):
            meta = st.session_state.get("q7_meta", {})
            st.info(
                f"Showing last Q7 results (Year {meta.get('year', year)}, Regions: {', '.join(meta.get('regions', [])) or 'All'})"
            )
            df = pd.DataFrame(st.session_state["q7_data"])
            st.dataframe(df, use_container_width=True)
            fig = px.pie(
                df,
                names="region_name",
                values="annual_total_visits",
                title="Regional Visit Distribution",
            )
            st.plotly_chart(fig, width='stretch')

    elif selected_query == "q8":
        st.subheader("Q8: Month-to-Month Change Within Year")
        st.markdown("📈 Track how visitor numbers change from month to month for a specific park. Shows seasonal trends and visitor flow patterns throughout the year.")
        park_search_q8 = st.text_input("Search for a park", value="", key="q8_search")
        park_matches_q8 = []
        if park_search_q8:
            park_matches_q8 = fetch_parks_by_query(park_search_q8, year, limit=20)
        
        if park_matches_q8:
            selected_park_q8 = st.selectbox(
                "Select a park from search results:",
                options=park_matches_q8,
                format_func=lambda x: f"{x[1]} ({x[0]})",
                key="q8_selected",
            )
            park_code = selected_park_q8[0]
        else:
            park_code = None
            if park_search_q8:
                st.info("No parks found matching that search.")
        
        clicked_q8 = st.button("Fetch Q8 Data", key="btn_q8")
        if clicked_q8:
            if not park_code:
                st.warning("Please search for and select a park first.")
            else:
                try:
                    resp = requests.get(
                        f"{API_BASE}/parks/{park_code}/monthly-visits",
                        params={"year": year}
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if data:
                        df = pd.DataFrame(data)
                        # Convert month number to month name
                        month_names = {1: "January", 2: "February", 3: "March", 4: "April", 
                                     5: "May", 6: "June", 7: "July", 8: "August", 
                                     9: "September", 10: "October", 11: "November", 12: "December"}
                        df["month_name"] = df["month"].map(month_names)
                        
                        # Calculate month-to-month change
                        df["change"] = df["total_visits"].diff()
                        df["change_percent"] = df["total_visits"].pct_change() * 100
                        
                        # Display the changes (skip first month since it has no previous month)
                        display_df = df[df["change"].notna()].copy()
                        display_cols = [col for col in ["month_name", "total_visits", "change", "change_percent"] if col in display_df.columns]
                        st.dataframe(display_df[display_cols], use_container_width=True)
                        
                        # Create bar chart showing absolute change
                        fig = px.bar(
                            display_df,
                            x="month_name",
                            y="change",
                            title=f"Month-to-Month Change in Visitors - {park_code}",
                            labels={"month_name": "Month", "change": "Change in Visitors"},
                            color="change",
                            color_continuous_scale="RdYlGn",
                        )
                        st.plotly_chart(fig, use_container_width=True)
                        st.session_state["q8_data"] = display_df.to_dict(orient="records")
                        st.session_state["q8_meta"] = {"park_code": park_code, "park_name": selected_park_q8[1] if park_matches_q8 else "", "year": year}
                    else:
                        st.warning("No data found.")
                except Exception as e:
                    st.error(f"Error: {e}")
        elif st.session_state.get("q8_data"):
            meta = st.session_state.get("q8_meta", {})
            park_label = meta.get("park_name") or meta.get("park_code", "")
            st.info(f"Showing last Q8 results ({park_label} | Year: {meta.get('year', year)})")
            display_df = pd.DataFrame(st.session_state["q8_data"])
            display_cols = [col for col in ["month_name", "total_visits", "change", "change_percent"] if col in display_df.columns]
            st.dataframe(display_df[display_cols], use_container_width=True)
            fig = px.bar(
                display_df,
                x="month_name",
                y="change",
                title=f"Month-to-Month Change in Visitors - {park_label}",
                labels={"month_name": "Month", "change": "Change in Visitors"},
                color="change",
                color_continuous_scale="RdYlGn",
            )
            st.plotly_chart(fig, use_container_width=True)

    elif selected_query == "q9":
        st.subheader("Q9: Parks with Highest Growth")
        st.markdown("📊 Compare visitor growth percentages for parks between two years. Identify which parks are experiencing the fastest growth in visitation.")
        col1, col2 = st.columns(2)
        with col1:
            start_year_q9 = st.number_input(
                "Start Year",
                value=min_year,
                min_value=min_year,
                max_value=max_year,
                key="q9_start",
            )
        with col2:
            end_year_q9 = st.number_input(
                "End Year",
                value=max_year,
                min_value=min_year,
                max_value=max_year,
                key="q9_end",
            )
        if st.button("Fetch Q9 Data", key="btn_q9"):
            try:
                params = {
                    "start_year": int(start_year_q9),
                    "end_year": int(end_year_q9),
                    "limit": limit,
                }
                if not global_regions:
                    # Fetch all regions when none selected (like other queries)
                    combined = []
                    for rid in all_region_keys:
                        try:
                            r = requests.get(f"{API_BASE}/regions/{rid}/growth", params=params)
                            r.raise_for_status()
                            combined.extend(r.json())
                        except Exception:
                            continue
                    data = combined
                elif len(global_regions) == 1:
                    region_for_q9 = global_regions[0]
                    resp = requests.get(f"{API_BASE}/regions/{region_for_q9}/growth", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                else:
                    combined = []
                    for rid in global_regions:
                        try:
                            r = requests.get(f"{API_BASE}/regions/{rid}/growth", params=params)
                            r.raise_for_status()
                            combined.extend(r.json())
                        except Exception:
                            continue
                    data = combined
                if data:
                    df = pd.DataFrame(data)
                    if selected_park_codes:
                        df = df[df["park_code"].isin(selected_park_codes)]
                    # Sort by growth_percent descending to mix regions
                    df = df.sort_values("growth_percent", ascending=False)
                    # Apply limit to final results
                    df = df.head(limit)
                    st.dataframe(df, use_container_width=True)
                    fig = px.bar(
                        df,
                        x="park_name",
                        y="growth_percent",
                        title=f"Park Growth: {start_year_q9} to {end_year_q9}",
                        labels={"park_name": "Park", "growth_percent": "Growth %"},
                    )
                    st.plotly_chart(fig, width='stretch')
                else:
                    st.warning("No data found.")
            except Exception as e:
                st.error(f"Error: {e}")

    elif selected_query == "q10":
        st.subheader("Q10: Parks Ranked by Visitor Variability")
        st.markdown("📊 Identify parks with the most fluctuation in visitor numbers month-to-month. High variability indicates seasonal tourism; low variability shows consistent visitation.")
        clicked_q10 = st.button("Fetch Q10 Data", key="btn_q10")
        if clicked_q10:
            try:
                params = {"year": year, "limit": limit}
                if global_regions:
                    if len(global_regions) == 1:
                        params["region_id"] = global_regions[0]
                resp = requests.get(f"{API_BASE}/visits/parks/variability", params=params)
                resp.raise_for_status()
                data = resp.json()
                if data:
                    df = pd.DataFrame(data)
                    if selected_park_codes:
                        df = df[df["park_code"].isin(selected_park_codes)]
                    if df.empty:
                        st.warning("No data found after applying selected park filter.")
                    else:
                        # Sort by the metric (descending) to mix regions
                        df = df.sort_values("std_dev_monthly_visits", ascending=False)
                        display_cols = [col for col in ["park_name", "region_name", "std_dev_monthly_visits"] if col in df.columns]
                        st.dataframe(df[display_cols], use_container_width=True)
                        fig = px.bar(
                            df,
                            x="park_name",
                            y="std_dev_monthly_visits",
                            title="Park Visitor Variability (Std Dev)",
                            labels={"park_name": "Park", "std_dev_monthly_visits": "Std Dev"},
                        )
                        st.plotly_chart(fig, width='stretch')
                        st.session_state["q10_data"] = df.to_dict(orient="records")
                        st.session_state["q10_meta"] = {"year": year, "regions": list(global_regions), "limit": limit}
                else:
                    st.warning("No data found.")
            except Exception as e:
                st.error(f"Error: {e}")
        elif st.session_state.get("q10_data"):
            meta = st.session_state.get("q10_meta", {})
            st.info(
                f"Showing last Q10 results (Year {meta.get('year', year)}, Regions: {', '.join(meta.get('regions', [])) or 'All'}, Limit: {meta.get('limit', limit)})"
            )
            df = pd.DataFrame(st.session_state["q10_data"])
            if selected_park_codes:
                df = df[df["park_code"].isin(selected_park_codes)]
            if df.empty:
                st.warning("No data found after applying selected park filter.")
            else:
                df = df.sort_values("std_dev_monthly_visits", ascending=False)
                display_cols = [col for col in ["park_name", "region_name", "std_dev_monthly_visits"] if col in df.columns]
                st.dataframe(df[display_cols], use_container_width=True)
                fig = px.bar(
                    df,
                    x="park_name",
                    y="std_dev_monthly_visits",
                    title="Park Visitor Variability (Std Dev)",
                    labels={"park_name": "Park", "std_dev_monthly_visits": "Std Dev"},
                )
                st.plotly_chart(fig, width='stretch')

    elif selected_query == "metrics":
        st.subheader("Metrics: Lodging, Camping, Backcountry, etc.")
        st.markdown("🏕️ Explore various visitor activity metrics including lodging, camping, and backcountry visits. See which parks have the most infrastructure usage and activity.")
        metric_options = {
            "concessioner_lodging": "Concessioner Lodging",
            "concessioner_camping": "Concessioner Camping",
            "tent_campers": "Tent Campers",
            "rv_campers": "RV Campers",
            "backcountry": "Backcountry Visits",
            "nonrecreation_overnight_stays": "Non-recreation Overnight Stays",
            "miscellaneous_overnight_stays": "Miscellaneous Overnight Stays",
        }
        col1, col2 = st.columns(2)
        with col1:
            sel_metric = st.selectbox("Select Metric", options=list(metric_options.keys()), format_func=lambda k: metric_options[k], key="metrics_select")
        with col2:
            st.markdown("\n")
        clicked_metrics = st.button("Fetch Metrics", key="btn_metrics")
        if clicked_metrics:
            try:
                params = {"year": year, "metric": sel_metric, "limit": limit}
                if global_regions and len(global_regions) == 1:
                    params["region_id"] = global_regions[0]
                if global_regions and len(global_regions) > 1:
                    combined = []
                    for rid in global_regions:
                        p = params.copy()
                        p["region_id"] = rid
                        try:
                            r = requests.get(f"{API_BASE}/annual-visits/parks/metrics", params=p)
                            r.raise_for_status()
                            combined.extend(r.json())
                        except Exception:
                            continue
                    data = combined
                else:
                    resp = requests.get(f"{API_BASE}/annual-visits/parks/metrics", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                if data:
                    df = pd.DataFrame(data)
                    if selected_park_codes:
                        df = df[df["park_code"].isin(selected_park_codes)]
                    # Sort by metric_total descending to mix regions
                    df = df.sort_values("metric_total", ascending=False)
                    # Apply limit to final results for multi-region queries
                    if len(global_regions) > 1:
                        df = df.head(limit)
                    st.dataframe(df, use_container_width=True)
                    fig = px.bar(
                        df,
                        x="park_name",
                        y="metric_total",
                        title=f"Top Parks by {metric_options.get(sel_metric, sel_metric)} ({year})",
                        labels={"park_name": "Park", "metric_total": metric_options.get(sel_metric, sel_metric)},
                    )
                    st.plotly_chart(fig, width='stretch')
                    st.session_state["metrics_data"] = df.to_dict(orient="records")
                    st.session_state["metrics_meta"] = {"year": year, "metric": sel_metric, "metric_label": metric_options.get(sel_metric, sel_metric), "regions": list(global_regions), "limit": limit}
                else:
                    st.warning("No data found for that metric/year.")
            except Exception as e:
                st.error(f"Error fetching metric data: {e}")
        elif st.session_state.get("metrics_data"):
            meta = st.session_state.get("metrics_meta", {})
            st.info(
                f"Showing last Metrics results ({meta.get('metric_label', sel_metric)} | Year {meta.get('year', year)}, Regions: {', '.join(meta.get('regions', [])) or 'All'}, Limit: {meta.get('limit', limit)})"
            )
            df = pd.DataFrame(st.session_state["metrics_data"])
            if selected_park_codes:
                df = df[df["park_code"].isin(selected_park_codes)]
            if not df.empty:
                df = df.sort_values("metric_total", ascending=False)
            st.dataframe(df, use_container_width=True)
            if not df.empty:
                fig = px.bar(
                    df,
                    x="park_name",
                    y="metric_total",
                    title=f"Top Parks by {meta.get('metric_label', sel_metric)} ({meta.get('year', year)})",
                    labels={"park_name": "Park", "metric_total": meta.get('metric_label', sel_metric)},
                )
                st.plotly_chart(fig, width='stretch')

    elif selected_query == "map_placeholder":
        pass  # Map is in separate tab below

with tab_map:
    st.subheader("Interactive Park Map")
    st.markdown("Click on park markers to view details. Markers are colored by region and sized by visitor count.")
    
    # Initialize session state for map
    if "map_data" not in st.session_state:
        st.session_state.map_data = None
        st.session_state.map_df = None
    
    if st.button("Load Map", key="btn_load_map"):
        try:
            # Fetch park data with annual visits for the selected year
            params = {"year": year, "limit": 500}
            
            # If single region selected, filter by that region
            if global_regions and len(global_regions) == 1:
                params["region_id"] = global_regions[0]
                resp = requests.get(f"{API_BASE}/annual-visits/parks", params=params)
                resp.raise_for_status()
                data = resp.json()
            elif global_regions and len(global_regions) > 1:
                # Multiple regions: fetch each and combine
                combined = []
                for rid in global_regions:
                    p = params.copy()
                    p["region_id"] = rid
                    try:
                        r = requests.get(f"{API_BASE}/annual-visits/parks", params=p)
                        r.raise_for_status()
                        combined.extend(r.json())
                    except Exception:
                        continue
                data = combined
            else:
                # No region filter, get all parks
                resp = requests.get(f"{API_BASE}/annual-visits/parks", params=params)
                resp.raise_for_status()
                data = resp.json()
            
            if not data:
                st.warning("No parks found for the selected filters.")
                st.session_state.map_data = None
            else:
                # Convert to DataFrame for easier manipulation
                df = pd.DataFrame(data)
                
                # Filter by selected parks if any
                if selected_park_codes:
                    df = df[df["park_code"].isin(selected_park_codes)]
                
                if df.empty:
                    st.warning("No parks match your selected parks filter.")
                    st.session_state.map_data = None
                else:
                    st.session_state.map_df = df
                    st.session_state.map_year = year
                    st.session_state.map_data = "loaded"
                    st.success(f"Map loaded with {len(df)} parks!")
        except Exception as e:
            st.error(f"Error loading map: {e}")
            st.session_state.map_data = None
    
    # Display map if data is loaded
    if st.session_state.map_data == "loaded" and st.session_state.map_df is not None:
        df = st.session_state.map_df
        year_disp = st.session_state.map_year
        
        # Define region colors
        region_colors = {
            "AKR": "orange",
            "IMR": "red",
            "MWR": "blue",
            "NCR": "purple",
            "NER": "green",
            "PWR": "darkblue",
            "SER": "darkred",
        }
        
        # Create Folium map centered on US
        m = folium.Map(
            location=[39.8283, -98.5795],
            zoom_start=4,
            tiles="OpenStreetMap"
        )
        
        # Normalize visitor counts for marker size scaling (1-20)
        min_visits = df["annual_total_visits"].min()
        max_visits = df["annual_total_visits"].max()
        
        # Add markers for each park
        for idx, row in df.iterrows():
            if pd.notna(row.get("latitude")) and pd.notna(row.get("longitude")):
                # Scale marker radius based on visitor count
                if max_visits > min_visits:
                    radius = 5 + ((row["annual_total_visits"] - min_visits) / (max_visits - min_visits)) * 15
                else:
                    radius = 10
                
                # Get region color
                color = region_colors.get(row.get("region_id", ""), "gray")
                
                # Build popup HTML with click instruction
                popup_html = f"""
                <div style="width: 280px; font-family: Arial; font-size: 12px;">
                    <b style="font-size: 14px;">{row['park_name']}</b><br>
                    <b>Code:</b> {row['park_code']}<br>
                    <b>Region:</b> {row.get('region_name', 'N/A')}<br>
                    <b>State:</b> {row.get('state', 'N/A')}<br>
                    <b>Annual Visitors ({year_disp}):</b> {int(row['annual_total_visits']):,}<br>
                    <hr style="margin: 8px 0;">
                    <i style="color: #666; font-size: 11px;">💡 Select this park code below to view details & boundary</i>
                </div>
                """
                
                marker = folium.CircleMarker(
                    location=[row["latitude"], row["longitude"]],
                    radius=radius,
                    popup=folium.Popup(popup_html, max_width=320),
                    color=color,
                    fill=True,
                    fillColor=color,
                    fillOpacity=0.7,
                    weight=2,
                    tooltip=f"{row['park_name']} ({row['park_code']})"
                )
                marker.add_to(m)
        
        # Display map with key parameter and capture click events
        map_data = st_folium(m, width=None, height=600, key="main_map", returned_objects=["last_object_clicked"])
        
        # Check if a marker was clicked and update selected park
        if map_data and map_data.get("last_object_clicked"):
            clicked_lat = map_data["last_object_clicked"].get("lat")
            clicked_lng = map_data["last_object_clicked"].get("lng")
            
            if clicked_lat and clicked_lng:
                # Find the park that matches these coordinates
                for _, row in df.iterrows():
                    if abs(row["latitude"] - clicked_lat) < 0.001 and abs(row["longitude"] - clicked_lng) < 0.001:
                        # Store the clicked park in session state
                        st.session_state.clicked_park_code = row["park_code"]
                        break
        
        # Show park count summary
        st.info(f"📍 Showing {len(df)} parks | 💡 Click a marker to auto-select the park below")
        
        # Park selector for details
        st.markdown("---")
        st.subheader("Park Details & Boundary")
        
        # Determine initial selection based on clicked park or first park
        park_options = [(row['park_code'], row['park_name']) for _, row in df.iterrows()]
        default_index = 0
        
        # If a park was clicked, find its index
        if hasattr(st.session_state, 'clicked_park_code') and st.session_state.clicked_park_code:
            for i, (code, name) in enumerate(park_options):
                if code == st.session_state.clicked_park_code:
                    default_index = i
                    break
        
        selected_park = st.selectbox(
            "Select a park to view details and boundary:",
            options=park_options,
            format_func=lambda x: f"{x[1]} ({x[0]})",
            index=default_index,
            key="park_detail_select"
        )
        
        if selected_park:
            park_code = selected_park[0]
            
            # Fetch full park details including description, website, boundary
            try:
                detail_resp = requests.get(f"{API_BASE}/parks/{park_code}/details")
                detail_resp.raise_for_status()
                park_detail = detail_resp.json()
                
                # Also get visitor stats
                stats_resp = requests.get(f"{API_BASE}/annual-visits/parks", params={"year": year_disp, "park_code": park_code})
                stats_resp.raise_for_status()
                stats_data = stats_resp.json()
                visitor_count = stats_data[0]['annual_total_visits'] if stats_data else 0
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.markdown(f"### {park_detail['park_name']}")
                    st.markdown(f"**Code:** {park_detail['park_code']}")
                    st.markdown(f"**Designation:** {park_detail['designation']}")
                    st.markdown(f"**Region:** {park_detail.get('region_name', 'N/A')}")
                    st.markdown(f"**State:** {park_detail['state']}")
                    st.markdown(f"**Annual Visitors ({year_disp}):** {int(visitor_count):,}")
                    
                    # Description
                    if park_detail.get('description'):
                        st.markdown("#### Description")
                        st.write(park_detail['description'])
                    
                    # Website
                    if park_detail.get('website'):
                        st.markdown(f"🌐 **Website:** [{park_detail['website']}]({park_detail['website']})")
                
                with col2:
                    if park_detail.get('latitude') and park_detail.get('longitude'):
                        # Create a detailed map with boundary if available
                        detail_map = folium.Map(
                            location=[park_detail['latitude'], park_detail['longitude']],
                            zoom_start=9,
                            tiles="OpenStreetMap"
                        )
                        
                        # Add park marker
                        folium.CircleMarker(
                            location=[park_detail['latitude'], park_detail['longitude']],
                            radius=10,
                            color=region_colors.get(park_detail.get("region_id", ""), "gray"),
                            fill=True,
                            fillOpacity=0.8,
                            popup=f"<b>{park_detail['park_name']}</b>",
                            tooltip=park_detail['park_name']
                        ).add_to(detail_map)
                        
                        # Add boundary if available
                        if park_detail.get('boundary'):
                            try:
                                import json
                                boundary_data = json.loads(park_detail['boundary'])
                                
                                # If it's a FeatureCollection, extract features
                                if boundary_data.get('type') == 'FeatureCollection' and boundary_data.get('features'):
                                    for feature in boundary_data['features']:
                                        if feature.get('geometry'):
                                            folium.GeoJson(
                                                feature,
                                                name=f"{park_detail['park_name']} Boundary",
                                                style_function=lambda x: {
                                                    'fillColor': region_colors.get(park_detail.get("region_id", ""), "gray"),
                                                    'color': region_colors.get(park_detail.get("region_id", ""), "gray"),
                                                    'weight': 2,
                                                    'fillOpacity': 0.2
                                                }
                                            ).add_to(detail_map)
                                elif boundary_data.get('geometry'):
                                    # Single feature
                                    folium.GeoJson(
                                        boundary_data,
                                        name=f"{park_detail['park_name']} Boundary",
                                        style_function=lambda x: {
                                            'fillColor': region_colors.get(park_detail.get("region_id", ""), "gray"),
                                            'color': region_colors.get(park_detail.get("region_id", ""), "gray"),
                                            'weight': 2,
                                            'fillOpacity': 0.2
                                        }
                                    ).add_to(detail_map)
                                
                                st.success("✅ Park boundary displayed on map")
                            except Exception as e:
                                st.warning(f"Boundary data available but couldn't render: {str(e)[:100]}")
                        
                        st_folium(detail_map, width=400, height=400, key=f"detail_map_{park_code}", returned_objects=[])
            except Exception as e:
                st.error(f"Error loading park details: {e}")


# -----------------------
# Footer
# -----------------------
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center;">
        <p><strong>NPS Park Operations Dashboard</strong> | IEEE 305 Term Project</p>
        <p style="font-size: 12px; color: #666;">
            Backend: FastAPI @ http://127.0.0.1:8000 | Database: SQLite
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


