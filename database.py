import sqlite3
import datetime
import os
from typing import List, Tuple, Optional

# Define database file path in the same directory as this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(SCRIPT_DIR, "flight_radar.db")

def get_connection(db_path: str = DB_NAME) -> sqlite3.Connection:
    """
    Etabliert eine Verbindung zur SQLite-Datenbank.
    """
    return sqlite3.connect(db_path)

def init_db(db_path: str = DB_NAME) -> None:
    """
    Initialisiert die SQLite-Datenbank mit dem neuen Roundtrip-Vergleichs-Schema.
    Migriert automatisch von dem alten Schema, falls dieses noch existiert.
    """
    with get_connection(db_path) as conn:
        # Check if table flights exists and has old schema
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='flights';")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(flights);")
            columns = [row[1] for row in cursor.fetchall()]
            if "price" in columns:
                print("Altes Datenbankschema erkannt. Drop table flights für Migration...")
                conn.execute("DROP TABLE flights;")
                conn.commit()

    query = """
    CREATE TABLE IF NOT EXISTS flights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        pod_id TEXT NOT NULL,
        price_oneway_hin REAL,
        price_oneway_zurueck REAL,
        price_oneway_total REAL,
        price_roundtrip REAL,
        airline_hin TEXT,
        airline_zurueck TEXT,
        airline_roundtrip TEXT,
        booking_link_hin TEXT,
        booking_link_zurueck TEXT,
        booking_link_roundtrip TEXT,
        flight_date_hin TEXT,
        flight_date_zurueck TEXT,
        is_live_check INTEGER NOT NULL CHECK (is_live_check IN (0, 1))
    );
    """
    with get_connection(db_path) as conn:
        conn.execute(query)
        conn.commit()
    print(f"Datenbank erfolgreich initialisiert unter: {os.path.abspath(db_path)}")

def insert_flight(
    pod_id: str,
    price_oneway_hin: float,
    price_oneway_zurueck: float,
    price_oneway_total: float,
    price_roundtrip: float,
    airline_hin: str,
    airline_zurueck: str,
    airline_roundtrip: str,
    booking_link_hin: Optional[str],
    booking_link_zurueck: Optional[str],
    booking_link_roundtrip: Optional[str],
    flight_date_hin: Optional[str],
    flight_date_zurueck: Optional[str],
    is_live_check: bool,
    timestamp: Optional[str] = None,
    db_path: str = DB_NAME
) -> None:
    """
    Fügt einen neuen Flugpreis-Eintrag mit allen Oneway- und Roundtrip-Daten in die Tabelle ein.
    """
    if timestamp is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    query = """
    INSERT INTO flights (
        timestamp, pod_id, 
        price_oneway_hin, price_oneway_zurueck, price_oneway_total, price_roundtrip,
        airline_hin, airline_zurueck, airline_roundtrip,
        booking_link_hin, booking_link_zurueck, booking_link_roundtrip,
        flight_date_hin, flight_date_zurueck, is_live_check
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    live_check_val = 1 if is_live_check else 0
    
    with get_connection(db_path) as conn:
        conn.execute(query, (
            timestamp, pod_id,
            price_oneway_hin, price_oneway_zurueck, price_oneway_total, price_roundtrip,
            airline_hin, airline_zurueck, airline_roundtrip,
            booking_link_hin, booking_link_zurueck, booking_link_roundtrip,
            flight_date_hin, flight_date_zurueck, live_check_val
        ))
        conn.commit()

def get_flights(db_path: str = DB_NAME) -> List[Tuple]:
    """
    Ruft alle aufgezeichneten Flugdaten ab, sortiert nach Zeitstempel absteigend.
    """
    query = """
    SELECT 
        timestamp, pod_id, 
        price_oneway_hin, price_oneway_zurueck, price_oneway_total, price_roundtrip,
        airline_hin, airline_zurueck, airline_roundtrip,
        booking_link_hin, booking_link_zurueck, booking_link_roundtrip,
        flight_date_hin, flight_date_zurueck, is_live_check
    FROM flights 
    ORDER BY timestamp DESC;
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()

def get_latest_price(pod_id: str, db_path: str = DB_NAME) -> Optional[float]:
    """
    Ruft den letzten aufgezeichneten Bestpreis (das Minimum aus Oneway-Gesamtpreis und Roundtrip)
    für eine bestimmte pod_id ab. Gibt None zurück, wenn noch kein Eintrag existiert.
    """
    query = """
    SELECT MIN(price_oneway_total, price_roundtrip) FROM flights 
    WHERE pod_id = ? 
    ORDER BY timestamp DESC 
    LIMIT 1;
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (pod_id,))
        row = cursor.fetchone()
        return row[0] if row else None

if __name__ == "__main__":
    init_db()
