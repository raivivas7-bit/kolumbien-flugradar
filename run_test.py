import os
import sys
import shutil
import json

# Add current directory to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(SCRIPT_DIR)

import tracker
import database

def main():
    print("==================================================")
    print("   Kiwi.com RapidAPI Tracker Integration Test")
    print("==================================================\n")
    
    # 1. Check credentials
    key, host = tracker.get_rapidapi_credentials()
    if not key or not host:
        print("[FEHLER] Credentials fehlen!")
        print("Bitte trage RAPIDAPI_KEY und RAPIDAPI_HOST in deine `.env`-Datei ein.")
        print("\nBeispiel-Inhalt der .env:")
        print("PROXY_URL=...")
        print("TELEGRAM_BOT_TOKEN=...")
        print("TELEGRAM_CHAT_ID=...")
        print("RAPIDAPI_KEY=dein_rapidapi_key_hier")
        print("RAPIDAPI_HOST=kiwi-com-cheap-flights.p.rapidapi.com")
        print("\nDer Test wird abgebrochen.")
        return
        
    print(f"[OK] Credentials gefunden:")
    print(f"   Host: {host}")
    print(f"   Key:  {'*' * len(key[:4])}{key[4:8]}...\n")
    
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    backup_path = os.path.join(SCRIPT_DIR, "config.json.bak")
    
    if os.path.exists(backup_path):
        print("Entferne altes Backup von config.json...")
        os.remove(backup_path)
        
    print("Erstelle Backup von config.json...")
    shutil.copy2(config_path, backup_path)
    
    # Write a test config with a matching outbound/inbound pair
    test_config = {
        "search_settings": {
            "max_stopovers": 1,
            "max_fly_duration_hours": 21,
            "currency": "EUR"
        },
        "travel_pods": {
            "hinfluege": [
                {
                    "id": "hin_test_live",
                    "passengers": ["P"],
                    "bags_to_add": 1,
                    "from": "MUC",
                    "to": "BOG",
                    "date_from": "31/07/2026",
                    "date_to": "31/07/2026"
                }
            ],
            "rueckfluege": [
                {
                    "id": "rueck_test_live",
                    "passengers": ["P"],
                    "bags_to_add": 1,
                    "from": "BOG",
                    "to": "MUC",
                    "date_from": "17/08/2026",
                    "date_to": "18/08/2026"
                }
            ]
        }
    }
    
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(test_config, f, indent=2)
            
        print("Datenbank initialisieren...")
        database.init_db()
        
        # Clean up old test runs
        with database.get_connection() as conn:
            conn.execute("DELETE FROM flights WHERE pod_id = ?", ("hin_test_live__rueck_test_live",))
            conn.commit()
            
        # Optional: pre-populate database with a high price to trigger a Telegram price alert
        print("Pre-populating database with a high price of 9999 EUR to trigger drop alert...")
        database.insert_flight(
            pod_id="hin_test_live__rueck_test_live",
            price_oneway_hin=4000.0,
            price_oneway_zurueck=4000.0,
            price_oneway_total=8000.0,
            price_roundtrip=9999.0,
            airline_hin="Mock Airline",
            airline_zurueck="Mock Airline",
            airline_roundtrip="Mock Airline",
            booking_link_hin="http://example.com",
            booking_link_zurueck="http://example.com",
            booking_link_roundtrip="http://example.com",
            flight_date_hin="31/07/2026",
            flight_date_zurueck="17/08/2026",
            is_live_check=True
        )
        
        print("\n--- Starte Live-API-Suche ---")
        tracker.run_tracker()
        print("--- API-Suche abgeschlossen ---\n")
        
        # Verify database write
        latest_price = database.get_latest_price("hin_test_live__rueck_test_live")
        if latest_price and latest_price < 8000.0:
            print(f"[ERFOLG] Ein Flugpreis wurde gefunden und gespeichert!")
            print(f"   Gefundener Preis: {latest_price:.2f} EUR")
        else:
            print("[Warnung] Es konnte kein Flugpreis für den Test-Pod abgerufen werden.")
            
    except Exception as e:
        print(f"[Fehler] Unerwarteter Fehler im Test: {e}")
        
    finally:
        print("\nRestauriere Original-Konfiguration `config.json`...")
        if os.path.exists(backup_path):
            shutil.move(backup_path, config_path)
            print("Originale `config.json` erfolgreich wiederhergestellt.")
            
if __name__ == "__main__":
    main()
