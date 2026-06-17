import streamlit as st
import pandas as pd
import sqlite3
import json
import os
import plotly.express as px
from database import DB_NAME

# Page configuration for a mobile-friendly, single-column layout
st.set_page_config(
    page_title="Flight Radar Tracker Dashboard",
    page_icon="✈️",
    layout="centered", # Centered is a single column, perfect for mobile
    initial_sidebar_state="collapsed"
)

# Custom premium styling for mobile layout
st.markdown("""
<style>
    /* Make the title look premium */
    .main-title {
        font-family: 'Outfit', 'Inter', sans-serif;
        color: #1E3A8A;
        font-weight: 700;
        text-align: center;
        margin-bottom: 20px;
    }
    
    /* Make check boxes look like toggle tags */
    .stCheckbox {
        background-color: #F3F4F6;
        padding: 5px 10px;
        border-radius: 8px;
        margin-bottom: 5px;
    }
    
    /* Style table buttons or links */
    a.booking-btn {
        background-color: #10B981;
        color: white;
        padding: 5px 10px;
        border-radius: 5px;
        text-decoration: none;
        font-weight: bold;
        font-size: 0.85em;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='main-title'>✈️ Flight Price Tracker</h1>", unsafe_allow_html=True)

# 1. Load config to map passenger counts and route info
def load_config_data() -> dict:
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

config = load_config_data()

# Build mappings from config
passenger_map = {}
route_map = {}

if config:
    travel_pods = config.get("travel_pods", {})
    for category in ["hinfluege", "rueckfluege"]:
        for pod in travel_pods.get(category, []):
            pod_id = pod.get("id")
            passengers = pod.get("passengers", [])
            passenger_map[pod_id] = len(passengers)
            route_map[pod_id] = f"{pod.get('from')} ➔ {pod.get('to')}"

# 2. Fetch data from SQLite database
def fetch_data() -> pd.DataFrame:
    if not os.path.exists(DB_NAME):
        return pd.DataFrame()
    
    conn = sqlite3.connect(DB_NAME)
    query = """
    SELECT timestamp, pod_id, price, airline, booking_link, is_live_check, flight_date 
    FROM flights 
    ORDER BY timestamp ASC;
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Parse timestamp as datetime
    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

df = fetch_data()

if df.empty:
    st.info("Keine Flugpreis-Daten in der Datenbank gefunden. Bitte starte den Tracker (`tracker.py`), um Daten zu sammeln.")
else:
    # 3. Checkboxes to show/hide lines (all selected by default)
    unique_pods = sorted(df['pod_id'].unique())
    
    st.markdown("### 🔍 Flug-Pods filtern")
    
    # Use a collapsable expander to save mobile screen space, open by default
    with st.expander("Auswahl der Flugstrecken", expanded=True):
        selected_pods = []
        for pod_id in unique_pods:
            route_info = route_map.get(pod_id, "")
            label = f"{pod_id} ({route_info})" if route_info else pod_id
            # Checked by default as requested: "müssen alle Flug-Pods standardmäßig gleichzeitig ... gezeichnet werden"
            if st.checkbox(label, value=True, key=f"chk_{pod_id}"):
                selected_pods.append(pod_id)

    # 4. Radio Button to toggle Price Mode
    st.markdown("### 💰 Preisanzeige umschalten")
    price_mode = st.radio(
        "Wähle den Preistyp für den Vergleich:",
        options=["Gesamtpreis der Gruppe", "Preis pro Person"],
        index=0,
        horizontal=True # Horizontal is very neat and mobile friendly
    )

    # 5. Data transformation based on inputs
    if not selected_pods:
        st.warning("Bitte wähle mindestens einen Flug-Pod aus, um das Diagramm anzuzeigen.")
    else:
        # Filter by selected pods
        df_filtered = df[df['pod_id'].isin(selected_pods)].copy()
        
        # Calculate display price
        if price_mode == "Preis pro Person":
            df_filtered['display_price'] = df_filtered.apply(
                lambda row: row['price'] / passenger_map.get(row['pod_id'], 1) if row['pod_id'] in passenger_map else row['price'],
                axis=1
            )
            y_label = "Preis pro Person (EUR)"
        else:
            df_filtered['display_price'] = df_filtered['price']
            y_label = "Gesamtpreis der Gruppe (EUR)"

        # 6. Plotly Interactive Multi-line chart
        fig = px.line(
            df_filtered,
            x="timestamp",
            y="display_price",
            color="pod_id",
            markers=True,
            labels={
                "timestamp": "Zeitpunkt (UTC)",
                "display_price": y_label,
                "pod_id": "Flug-Pod"
            },
            title="Preisentwicklung über die Zeit"
        )

        # Optimize plotly graph for mobile viewport
        fig.update_layout(
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.5, # Move legend below graph
                xanchor="center",
                x=0.5
            ),
            margin=dict(l=10, r=10, t=50, b=100),
            hovermode="x unified",
            xaxis_title="Abfragezeitpunkt",
            yaxis_title=y_label
        )
        
        st.plotly_chart(fig, use_container_width=True)

        # 7. Mobile-Friendly Summary Table
        st.markdown("### 📊 Aktuelle Flugpreise (Letzter Stand)")
        
        # Get the latest entry for each selected pod
        latest_entries = []
        for pod_id in selected_pods:
            pod_df = df_filtered[df_filtered['pod_id'] == pod_id]
            if not pod_df.empty:
                latest_entries.append(pod_df.iloc[-1])
                
        if latest_entries:
            latest_df = pd.DataFrame(latest_entries)
            
            # Format display strings
            table_data = []
            for _, row in latest_df.iterrows():
                p_count = passenger_map.get(row['pod_id'], 1)
                route = route_map.get(row['pod_id'], "Unbekannt")
                
                # Format prices
                total_p = f"{row['price']:.2f} €"
                per_person_p = f"{row['price']/p_count:.2f} €"
                
                # Check is_live_check
                source = "🟢 Live API" if row['is_live_check'] == 1 else "🧪 Test-Daten"
                
                table_data.append({
                    "Flug-Pod (Route)": f"<b>{row['pod_id']}</b><br><small>{route}</small>",
                    "Reisedatum": row.get('flight_date', '-') if pd.notna(row.get('flight_date')) else '-',
                    "Pax": p_count,
                    "Gesamtpreis": total_p,
                    "Preis/Person": per_person_p,
                    "Airline": row['airline'],
                    "Quelle": source,
                    "Link": f'<a class="booking-btn" href="{row["booking_link"]}" target="_blank">Buchen</a>' if row['booking_link'] else "-"
                })
                
            summary_table_df = pd.DataFrame(table_data)
            
            # Render HTML table to support formatted links/text
            st.write(summary_table_df.to_html(escape=False, index=False), unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
