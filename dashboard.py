import streamlit as st
import pandas as pd
import sqlite3
import json
import os
import plotly.express as px
from typing import Tuple
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
    
    /* Style table buttons or links */
    a.booking-btn {
        background-color: #10B981;
        color: white !important;
        padding: 6px 12px;
        border-radius: 6px;
        text-decoration: none;
        font-weight: 600;
        font-size: 0.85em;
        display: inline-block;
        text-align: center;
        margin-right: 5px;
        margin-top: 5px;
        transition: background-color 0.2s;
    }
    a.booking-btn:hover {
        background-color: #059669;
    }
    
    /* Card design */
    .flight-card {
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 16px;
        background-color: #FFFFFF;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03);
        margin-bottom: 16px;
    }
    .flight-card-title {
        font-size: 1.05em;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 4px;
        line-height: 1.3;
    }
    .flight-card-dates {
        font-size: 0.85em;
        color: #6B7280;
        margin-bottom: 12px;
        font-weight: 500;
    }
    .flight-card-prices {
        font-size: 0.9em;
        line-height: 1.6;
        margin-bottom: 12px;
        color: #374151;
    }
    .flight-card-winner {
        padding: 8px 12px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.85em;
        margin-bottom: 12px;
    }
    .flight-card-winner.oneway {
        background-color: #D1FAE5;
        color: #065F46;
    }
    .flight-card-winner.roundtrip {
        background-color: #DBEAFE;
        color: #1E40AF;
    }
    .flight-card-winner.equal {
        background-color: #F3F4F6;
        color: #374151;
    }
    
    table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 15px;
        margin-bottom: 15px;
        font-size: 0.9em;
    }
    th {
        background-color: #1E3A8A;
        color: white;
        text-align: left;
        padding: 8px;
        font-weight: 600;
    }
    td {
        border-bottom: 1px solid #E5E7EB;
        padding: 8px;
        vertical-align: top;
    }
    tr:nth-child(even) {
        background-color: #F9FAFB;
    }
    /* Mobile optimization */
    @media screen and (max-width: 600px) {
        table {
            font-size: 0.75em;
        }
        th, td {
            padding: 4px;
        }
        a.booking-btn {
            padding: 4px 8px;
            font-size: 0.75em;
        }
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

# Date formatter helper
def format_date_short(date_str: str) -> str:
    if not date_str or date_str == "-":
        return "-"
    if "/" in date_str:
        parts = date_str.split("/")
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}."
    elif "-" in date_str:
        parts = date_str.split("-")
        if len(parts) >= 3:
            if len(parts[0]) == 4:
                return f"{parts[2]}.{parts[1]}."
            else:
                return f"{parts[0]}.{parts[1]}."
    return date_str

# Helper function to parse pod_pair_id
def get_pod_pair_info(pod_pair_id: str, config: dict) -> Tuple[int, str, str]:
    """
    Gibt die Anzahl der Passagiere, eine Route-Beschreibung und eine Passagier-Liste (z.B. P+A+K) für ein Pod-Paar zurück.
    """
    parts = pod_pair_id.split("__")
    if len(parts) != 2:
        return 1, pod_pair_id, "Pax"
        
    hin_id, rueck_id = parts[0], parts[1]
    
    travel_pods = config.get("travel_pods", {})
    hin_pod = next((p for p in travel_pods.get("hinfluege", []) if p.get("id") == hin_id), None)
    rueck_pod = next((p for p in travel_pods.get("rueckfluege", []) if p.get("id") == rueck_id), None)
    
    pax_count = 1
    route_str = pod_pair_id
    pax_str = "P"
    
    if hin_pod and rueck_pod:
        # Passagiere basieren auf der Rückflug-Gruppe (Ziel-Vergleichs-Gruppe)
        pax_list = rueck_pod.get("passengers", ["P"])
        pax_count = len(pax_list)
        pax_str = "+".join(pax_list)
        
        h_from = hin_pod.get('from', '')
        h_to = hin_pod.get('to', '')
        r_from = rueck_pod.get('from', '')
        r_to = rueck_pod.get('to', '')
        
        if h_to == r_from and h_from == r_to:
            route_str = f"{h_from} ↔ {h_to}"
        else:
            route_str = f"{h_from} ➔ {h_to} | {r_from} ➔ {r_to}"
    elif hin_pod:
        route_str = f"{hin_pod.get('from')} ➔ {hin_pod.get('to')}"
        pax_str = "+".join(hin_pod.get("passengers", ["P"]))
    elif rueck_pod:
        route_str = f"{rueck_pod.get('from')} ➔ {rueck_pod.get('to')}"
        pax_str = "+".join(rueck_pod.get("passengers", ["P"]))
        
    return pax_count, route_str, pax_str

# 2. Fetch data from SQLite database
def fetch_data() -> pd.DataFrame:
    if not os.path.exists(DB_NAME):
        return pd.DataFrame()
    
    conn = sqlite3.connect(DB_NAME)
    query = """
    SELECT 
        timestamp, pod_id, 
        price_oneway_hin, price_oneway_zurueck, price_oneway_total, price_roundtrip,
        airline_hin, airline_zurueck, airline_roundtrip,
        booking_link_hin, booking_link_zurueck, booking_link_roundtrip,
        flight_date_hin, flight_date_zurueck, is_live_check
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
    # Build passenger and route mappings dynamically
    pax_counts = {}
    routes = {}
    pax_strings = {}
    unique_pods = sorted(df['pod_id'].unique())
    for pid in unique_pods:
        pax_counts[pid], routes[pid], pax_strings[pid] = get_pod_pair_info(pid, config)

    # 3. Checkboxes to show/hide lines (all selected by default)
    st.markdown("### 🔍 Flug-Pods filtern")
    
    # Use a collapsable expander to save mobile screen space, open by default
    with st.expander("Auswahl der Flugstrecken", expanded=True):
        selected_pods = []
        for pod_id in unique_pods:
            route_info = routes.get(pod_id, "")
            label = f"{pod_id} ({route_info})" if route_info else pod_id
            # Checked by default as requested
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
        st.warning("Bitte wähle mindestens einen Flug-Pod aus, um das Dashboard anzuzeigen.")
    else:
        # Filter by selected pods
        df_filtered = df[df['pod_id'].isin(selected_pods)].copy()
        
        # Add pax_count and route columns
        df_filtered['pax_count'] = df_filtered['pod_id'].map(pax_counts).fillna(1).astype(int)
        df_filtered['route'] = df_filtered['pod_id'].map(routes).fillna(df_filtered['pod_id'])
        
        # Calculate display prices
        if price_mode == "Preis pro Person":
            df_filtered['display_oneway_hin'] = df_filtered['price_oneway_hin'] / df_filtered['pax_count']
            df_filtered['display_oneway_zurueck'] = df_filtered['price_oneway_zurueck'] / df_filtered['pax_count']
            df_filtered['display_oneway_total'] = df_filtered['price_oneway_total'] / df_filtered['pax_count']
            df_filtered['display_roundtrip'] = df_filtered['price_roundtrip'] / df_filtered['pax_count']
            y_label = "Preis pro Person (EUR)"
        else:
            df_filtered['display_oneway_hin'] = df_filtered['price_oneway_hin']
            df_filtered['display_oneway_zurueck'] = df_filtered['price_oneway_zurueck']
            df_filtered['display_oneway_total'] = df_filtered['price_oneway_total']
            df_filtered['display_roundtrip'] = df_filtered['price_roundtrip']
            y_label = "Gesamtpreis der Gruppe (EUR)"

        # Three tabs
        tab1, tab2, tab3 = st.tabs(["🏆 Bester Deal", "📈 Preisverlauf", "📋 Details"])

        # Tab 1: Bester Deal
        with tab1:
            st.markdown("### 🏆 Bester Deal im Vergleich")
            
            # st.metric cards comparing latest prices for each selected pod
            for pod_id in selected_pods:
                pod_df = df_filtered[df_filtered['pod_id'] == pod_id]
                if pod_df.empty:
                    continue
                
                latest_row = pod_df.iloc[-1]
                route_info = routes.get(pod_id, pod_id)
                st.markdown(f"#### ✈️ {route_info} (`{pod_id}`)")
                
                price_a = latest_row['display_oneway_total']
                price_b = latest_row['display_roundtrip']
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(
                        label="Option A (Summe Oneways)",
                        value=f"{price_a:.2f} €",
                        delta=None
                    )
                with col2:
                    st.metric(
                        label="Option B (Roundtrip Kombi)",
                        value=f"{price_b:.2f} €",
                        delta=None
                    )
                
                # Highlight winner
                if price_a < price_b:
                    savings = price_b - price_a
                    st.success(f"🎉 **Option A (Getrennt gebucht)** ist der Gewinner! Ersparnis: **{savings:.2f} €**")
                elif price_b < price_a:
                    savings = price_a - price_b
                    st.success(f"🎉 **Option B (Zusammen gebucht)** ist der Gewinner! Ersparnis: **{savings:.2f} €**")
                else:
                    st.info("🤝 Beide Buchungswege sind preislich identisch.")
                st.markdown("---")
            
            # Styled Card Grid replacing comparison table
            st.markdown("### 📊 Aktuelle Flugpreise im direkten Vergleich")
            
            # Loop through selected pods in pairs for grid layout
            for idx in range(0, len(selected_pods), 2):
                cols = st.columns(2)
                for col_idx in range(2):
                    pod_idx = idx + col_idx
                    if pod_idx >= len(selected_pods):
                        break
                    
                    pod_id = selected_pods[pod_idx]
                    pod_df = df_filtered[df_filtered['pod_id'] == pod_id]
                    if pod_df.empty:
                        continue
                    
                    latest_row = pod_df.iloc[-1]
                    p_count = pax_counts.get(pod_id, 1)
                    route_display = routes.get(pod_id, pod_id)
                    pax_str = pax_strings.get(pod_id, "Pax")
                    
                    date_hin = latest_row.get('flight_date_hin', '-')
                    date_zur = latest_row.get('flight_date_zurueck', '-')
                    date_hin_fmt = format_date_short(date_hin)
                    date_zur_fmt = format_date_short(date_zur)
                    
                    # Retrieve display values
                    p_hin = latest_row['display_oneway_hin']
                    p_zur = latest_row['display_oneway_zurueck']
                    p_tot = latest_row['display_oneway_total']
                    p_rt = latest_row['display_roundtrip']
                    
                    # Winner determination
                    if p_tot < p_rt:
                        winner_class = "oneway"
                        savings = p_rt - p_tot
                        winner_text = f"🎉 Getrennte Buchung spart dir {savings:.2f} €!"
                    elif p_rt < p_tot:
                        winner_class = "roundtrip"
                        savings = p_tot - p_rt
                        winner_text = f"🎉 Kombi-Ticket spart dir {savings:.2f} €!"
                    else:
                        winner_class = "equal"
                        winner_text = "🤝 Beide Buchungswege sind gleich teuer!"
                    
                    # Build booking links HTML
                    link_hin = latest_row.get('booking_link_hin')
                    link_zur = latest_row.get('booking_link_zurueck')
                    link_rt = latest_row.get('booking_link_roundtrip')
                    
                    links_html = ""
                    if p_tot <= p_rt:
                        # Option A links
                        links_list = []
                        if link_hin:
                            links_list.append(f'<a class="booking-btn" href="{link_hin}" target="_blank">✈️ Hin buchen</a>')
                        if link_zur:
                            links_list.append(f'<a class="booking-btn" href="{link_zur}" target="_blank">✈️ Zurück buchen</a>')
                        links_html = " ".join(links_list) if links_list else "-"
                    else:
                        # Option B link
                        links_html = f'<a class="booking-btn" href="{link_rt}" target="_blank">🔄 Kombi buchen</a>' if link_rt else "-"
                    
                    source = "Live API" if latest_row['is_live_check'] == 1 else "Test-Daten"
                    source_badge = f'<span style="font-size: 0.75em; float: right; padding: 2px 6px; border-radius: 4px; background-color: #E5E7EB; color: #4B5563;">{source}</span>'
                    
                    card_html = f"""
                    <div class="flight-card">
                        {source_badge}
                        <div class="flight-card-title">{pax_str} ✈️ {route_display}</div>
                        <div class="flight-card-dates">📅 Hin: {date_hin_fmt} | 📅 Zurück: {date_zur_fmt}</div>
                        <div class="flight-card-prices">
                            🎫 <b>Getrennt (Oneways):</b> {p_tot:.2f} € <br>
                            <span style="font-size: 0.85em; color: #6B7280; margin-left: 15px;">• Hin: {p_hin:.2f} € | Zurück: {p_zur:.2f} €</span><br>
                            🔄 <b>Kombi-Ticket (Roundtrip):</b> {p_rt:.2f} €
                        </div>
                        <div class="flight-card-winner {winner_class}">
                            {winner_text}
                        </div>
                        <div style="margin-top: 10px;">
                            {links_html}
                        </div>
                    </div>
                    """
                    with cols[col_idx]:
                        st.markdown(card_html, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

        # Tab 2: Preisverlauf
        with tab2:
            st.markdown("### 📈 Preisverlauf über die Zeit")
            
            # Prepare long format dataframe for Plotly
            plot_data = []
            for _, row in df_filtered.iterrows():
                pod_id = row['pod_id']
                ts = row['timestamp']
                
                # Option A (Oneways)
                plot_data.append({
                    "timestamp": ts,
                    "pod_id": pod_id,
                    "Typ": "Option A (Oneways Gesamt)",
                    "Preis (EUR)": row['display_oneway_total'],
                    "Vergleichslinie": f"{pod_id}: Oneways Gesamt"
                })
                
                # Option B (Roundtrip)
                plot_data.append({
                    "timestamp": ts,
                    "pod_id": pod_id,
                    "Typ": "Option B (Roundtrip)",
                    "Preis (EUR)": row['display_roundtrip'],
                    "Vergleichslinie": f"{pod_id}: Kombi-Ticket"
                })
                
            if plot_data:
                plot_df = pd.DataFrame(plot_data)
                
                # Create line plot
                fig = px.line(
                    plot_df,
                    x="timestamp",
                    y="Preis (EUR)",
                    color="Vergleichslinie",
                    markers=True,
                    labels={
                        "timestamp": "Zeitpunkt",
                        "Preis (EUR)": y_label,
                        "Vergleichslinie": "Buchungsweg"
                    },
                    title="Preisentwicklung: Oneways vs. Roundtrip"
                )
                
                # Optimize layout for mobile viewport: Legende unten, Ränder minimiert
                fig.update_layout(
                    legend=dict(
                        orientation="h",
                        yanchor="top",
                        y=-0.2,
                        xanchor="center",
                        x=0.5
                    ),
                    margin=dict(l=10, r=10, t=40, b=10),
                    hovermode="x unified",
                    xaxis_title="Abfragezeitpunkt",
                    yaxis_title=y_label
                )
                
                # Render without Plotly modebar on mobile
                st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
            else:
                st.info("Keine Daten zum Zeichnen vorhanden.")

        # Tab 3: Details
        with tab3:
            st.markdown("### 📋 Ungefilterte Flugpreis-Historie")
            
            # Format and show raw database table
            details_df = df.copy()
            details_df = details_df.rename(columns={
                "timestamp": "Zeitpunkt (UTC)",
                "pod_id": "Flug-Pod ID",
                "price_oneway_hin": "Hin Oneway (€)",
                "price_oneway_zurueck": "Zurück Oneway (€)",
                "price_oneway_total": "Gesamt Oneways (€)",
                "price_roundtrip": "Kombi Roundtrip (€)",
                "airline_hin": "Airline Hin",
                "airline_zurueck": "Airline Zurück",
                "airline_roundtrip": "Airline Roundtrip",
                "flight_date_hin": "Datum Hin",
                "flight_date_zurueck": "Datum Zurück",
                "is_live_check": "Live-Abfrage"
            })
            
            # Sort by timestamp descending for viewing
            details_df = details_df.sort_values(by="Zeitpunkt (UTC)", ascending=False)
            
            # Render interactive dataframe
            st.dataframe(details_df, width='stretch')


