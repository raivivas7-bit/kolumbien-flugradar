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
    Initialisiert die SQLite-Datenbank und erstellt die Tabelle 'flights',
    falls diese noch nicht existiert.
    Fügt auch die Spalte 'flight_date' hinzu, falls sie noch fehlt.
    """
    query = """
    CREATE TABLE IF NOT EXISTS flights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        pod_id TEXT NOT NULL,
        price REAL NOT NULL,
        airline TEXT NOT NULL,
        booking_link TEXT,
        is_live_check INTEGER NOT NULL CHECK (is_live_check IN (0, 1))
    );
    """
    with get_connection(db_path) as conn:
        conn.execute(query)
        conn.commit()
        
        # Sicherstellen, dass flight_date Spalte existiert
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(flights);")
        columns = [row[1] for row in cursor.fetchall()]
        if "flight_date" not in columns:
            conn.execute("ALTER TABLE flights ADD COLUMN flight_date TEXT;")
            conn.commit()
            
    print(f"Datenbank erfolgreich initialisiert unter: {os.path.abspath(db_path)}")

def insert_flight(
    pod_id: str,
    price: float,
    airline: str,
    booking_link: Optional[str],
    is_live_check: bool,
    flight_date: Optional[str] = None,
    timestamp: Optional[str] = None,
    db_path: str = DB_NAME
) -> None:
    """
    Fügt einen neuen Flugpreis-Eintrag in die Tabelle ein.
    Wenn kein Zeitstempel übergeben wird, wird die aktuelle UTC-Zeit im ISO-Format verwendet.
    """
    if timestamp is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    query = """
    INSERT INTO flights (timestamp, pod_id, price, airline, booking_link, is_live_check, flight_date)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """
    live_check_val = 1 if is_live_check else 0
    
    with get_connection(db_path) as conn:
        conn.execute(query, (timestamp, pod_id, price, airline, booking_link, live_check_val, flight_date))
        conn.commit()

def get_flights(db_path: str = DB_NAME) -> List[Tuple]:
    """
    Ruft alle aufgezeichneten Flugdaten ab, sortiert nach Zeitstempel absteigend.
    """
    query = """
    SELECT timestamp, pod_id, price, airline, booking_link, is_live_check, flight_date 
    FROM flights 
    ORDER BY timestamp DESC;
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()
def get_latest_price(pod_id: str, db_path: str = DB_NAME) -> Optional[float]:
    """
    Ruft den letzten aufgezeichneten Preis für eine bestimmte pod_id ab.
    Gibt None zurück, wenn noch kein Eintrag existiert.
    """
    query = """
    SELECT price FROM flights 
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
