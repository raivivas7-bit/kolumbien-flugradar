import json
import os
import datetime
import asyncio
import re
import time
from typing import Optional, List, Dict, Tuple
import requests
from telegram import Bot
from database import insert_flight, init_db, get_latest_price

# Paths for configuration file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

async def _send_telegram_message_async(token: str, chat_id: str, text: str, silent: bool) -> None:
    bot = Bot(token=token)
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        disable_notification=silent,
        parse_mode="HTML"
    )

def send_telegram_notification(text: str, silent: bool) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    # Check if they are in .env if not in environment
    if not token or not chat_id:
        env_path = os.path.join(SCRIPT_DIR, ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            if "=" in line:
                                key, val = line.split("=", 1)
                                k = key.strip()
                                v = val.strip().strip('"').strip("'")
                                if k == "TELEGRAM_BOT_TOKEN":
                                    token = v
                                elif k == "TELEGRAM_CHAT_ID":
                                    chat_id = v
            except Exception:
                pass

    if not token or not chat_id:
        print(f"  [Telegram] Überspringe Benachrichtigung (Token oder Chat ID fehlt)")
        return
        
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
            
        if loop and loop.is_running():
            # If there's already a running loop, create a task
            loop.create_task(_send_telegram_message_async(token, chat_id, text, silent))
        else:
            asyncio.run(_send_telegram_message_async(token, chat_id, text, silent))
        print(f"  [Telegram] Benachrichtigung gesendet ({'stumm' if silent else 'hohe Priorität'})")
    except Exception as e:
        print(f"  [Telegram-Fehler] Fehler beim Senden der Nachricht: {e}")

def load_config(config_path: str = CONFIG_PATH) -> dict:
    """
    Lädt die Konfigurationsdaten aus der JSON-Datei.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden unter: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_rapidapi_credentials() -> Tuple[str, str]:
    """
    Liest RAPIDAPI_KEY und RAPIDAPI_HOST aus der .env-Datei oder dem Environment.
    """
    key = os.environ.get("RAPIDAPI_KEY")
    host = os.environ.get("RAPIDAPI_HOST")
    
    if key and host:
        return key, host
        
    env_path = os.path.join(SCRIPT_DIR, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k == "RAPIDAPI_KEY":
                            key = v
                        elif k == "RAPIDAPI_HOST":
                            host = v
        except Exception:
            pass
            
    return key or "", host or ""

def generate_dates(date_from_str: str, date_to_str: str) -> List[str]:
    """
    Generiert eine Liste von Tagen (Format DD/MM/YYYY) zwischen date_from und date_to.
    """
    try:
        d1 = datetime.datetime.strptime(date_from_str, "%d/%m/%Y")
        d2 = datetime.datetime.strptime(date_to_str, "%d/%m/%Y")
    except ValueError as e:
        print(f"Fehler beim Parsen der Reisedaten: {e}")
        return []
        
    dates = []
    curr = d1
    while curr <= d2:
        dates.append(curr.strftime("%d/%m/%Y"))
        curr += datetime.timedelta(days=1)
    return dates

def fetch_flight_price_rapidapi(start: str, dest: str, date: str, passengers_count: int, currency: str = "EUR") -> Optional[dict]:
    """
    Sende einen GET-Request an den Search-Endpoint der Kiwi RapidAPI.
    Extrahiert den günstigsten Flug und gibt die Flugdaten zurück.
    """
    key, host = get_rapidapi_credentials()
    if not key or not host:
        print("  [RapidAPI] Fehler: RAPIDAPI_KEY oder RAPIDAPI_HOST fehlt in der Konfiguration!")
        return None
        
    url = f"https://{host}/api/v1/flights/search-oneway"
    
    headers = {
        "x-rapidapi-key": key,
        "x-rapidapi-host": host
    }
    
    # Konvertiere das Datum von DD/MM/YYYY zu YYYY-MM-DD
    try:
        api_date = datetime.datetime.strptime(date, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        api_date = date
        
    params = {
        "source": start,
        "destination": dest,
        "departure_date": api_date,
        "currency": currency,
        "adults": passengers_count,
        "limit": 5  # Fetch a few results to find the cheapest
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code != 200:
            print(f"  [RapidAPI-Fehler] Status: {response.status_code} | Nachricht: {response.text}")
            return None
            
        data = response.json()
        itineraries = data.get("itineraries", [])
        if not itineraries:
            return None
            
        # Finde den absolut günstigsten Flug aus den Ergebnissen
        cheapest = min(itineraries, key=lambda x: x.get("price", {}).get("amount", float('inf')))
        
        price_val = cheapest.get("price", {}).get("amount")
        if price_val is None:
            return None
            
        # Extrahiere Carrier-Namen
        carriers = cheapest.get("outbound", {}).get("carriers", [])
        airlines = [c.get("name", "Unknown Airline") for c in carriers if c.get("name")]
        if not airlines:
            airlines = ["Kiwi Option"]
            
        # Extrahiere booking_url
        booking_options = cheapest.get("booking_options", [])
        booking_link = ""
        if booking_options:
            booking_link = booking_options[0].get("booking_url", "")
            
        return {
            "price": float(price_val),
            "airlines": airlines,
            "deep_link": booking_link,
            "bags_price": cheapest.get("bags_price", {}),
            "date": date
        }
    except Exception as e:
        print(f"  [RapidAPI-Fehler] Ausnahme bei Anfrage: {e}")
        return None

def calculate_price_with_bags(flight: dict, bags_to_add: int) -> Tuple[float, float]:
    """
    Berechnet den Gesamtpreis inklusive Gepäckgebühren.
    """
    base_price = float(flight.get("price", 0.0))
    if bags_to_add <= 0:
        return 0.0, base_price
    
    # Kiwi.com liefert gewöhnlich bags_price Struktur zurück: {"1": price_for_1_bag, "2": price_for_2_bags}
    bags_price_dict = flight.get("bags_price") or {}
    if not isinstance(bags_price_dict, dict):
        bags_price_dict = {}
        
    bag_cost = 0.0
    
    # Achtung: Keys in bags_price_dict können Strings oder Floats/Ints sein, wir konvertieren
    # Standardgebühr 45 EUR falls nicht vorhanden
    bag_cost_found = False
    for k, v in bags_price_dict.items():
        if str(k) == str(bags_to_add) and v is not None:
            bag_cost = float(v)
            bag_cost_found = True
            break
            
    if not bag_cost_found:
        bag_cost = 45.0 * bags_to_add
                
    return bag_cost, base_price + bag_cost

def filter_flights(flights: list, pod: dict, search_settings: dict) -> list:
    """
    Filtert die Flüge lokal anhand der spezifischen Kriterien des Pods.
    """
    filtered = []
    max_duration_hours = search_settings.get("max_fly_duration_hours")
    
    for flight in flights:
        # 1. Zwischenstopps prüfen
        stopovers = len(flight.get("route", [])) - 1
        if stopovers > search_settings.get("max_stopovers", 1):
            continue
            
        # 2. Flugdauer prüfen
        duration_sec = flight.get("duration", {}).get("total", 0)
        if isinstance(flight.get("duration"), (int, float)):
            duration_sec = flight["duration"]
        
        duration_hours = duration_sec / 3600.0
        if max_duration_hours and duration_hours > max_duration_hours:
            continue
            
        # 3. Abflugzeit prüfen
        time_from = pod.get("time_from")
        if time_from:
            local_dep = flight.get("local_departure", "")
            if "T" in local_dep:
                dep_time = local_dep.split("T")[1][:5]
                if dep_time < time_from:
                    continue
                    
        # 4. Ankunftszeit-Limit prüfen
        arrival_time_to = pod.get("arrival_time_to")
        if arrival_time_to:
            local_arr = flight.get("local_arrival", "")
            if "T" in local_arr:
                arr_time = local_arr.split("T")[1][:5]
                if arr_time > arrival_time_to:
                    continue
                    
        # 5. Ankunftsdatum-Limit prüfen
        arrival_date_to = pod.get("arrival_date_to")
        if arrival_date_to:
            local_arr = flight.get("local_arrival", "")
            if "T" in local_arr:
                arr_date = local_arr.split("T")[0]
                parts = arrival_date_to.split("/")
                iso_arr_date_to = f"{parts[2]}-{parts[1]}-{parts[0]}"
                if arr_date > iso_arr_date_to:
                    continue
                    
        filtered.append(flight)
    return filtered

def fetch_flights_for_pod(pod: dict, search_settings: dict) -> Tuple[Optional[dict], bool]:
    """
    Fragt RapidAPI für einen Pod ab.
    Iteriert über alle Flughafenkombinationen und Tage,
    ruft die API auf und findet den günstigsten Flug.
    Gibt ein Tupel (cheapest_flight, is_live) zurück.
    """
    pod_id = pod.get("id")
    origins = [o.strip() for o in pod.get("from", "").split(",") if o.strip()]
    destinations = [d.strip() for d in pod.get("to", "").split(",") if d.strip()]
    
    date_from_str = pod.get("date_from")
    date_to_str = pod.get("date_to")
    
    if not date_from_str:
        return None, False
        
    if not date_to_str:
        date_to_str = date_from_str
        
    dates = generate_dates(date_from_str, date_to_str)
    if not dates:
        return None, False
        
    passengers_count = len(pod.get("passengers", ["P"]))
    currency = search_settings.get("currency", "EUR")
    
    print(f"  [RapidAPI] Starte Abfragen für Pod '{pod_id}' (Kombinationen: {len(origins)}x{len(destinations)}x{len(dates)} = {len(origins)*len(destinations)*len(dates)})...")
    
    api_flights = []
    
    for origin in origins:
        for dest in destinations:
            for d in dates:
                flight_data = fetch_flight_price_rapidapi(origin, dest, d, passengers_count, currency)
                if flight_data:
                    api_flights.append(flight_data)
                    print(f"    -> Preis für {origin.upper()} -> {dest.upper()} am {d}: {flight_data.get('price'):.2f} {currency} ({', '.join(flight_data.get('airlines', []))})")
                else:
                    print(f"    -> Kein Ergebnis oder Fehler für {origin} -> {dest} am {d}")
                # Rate limit sleep
                time.sleep(1.0)
                
    if api_flights:
        # Günstigsten Flug unter allen Kombinationen finden
        cheapest = min(api_flights, key=lambda x: x.get("price", float('inf')))
        
        # Um die Kompatibilität zu wahren, passen wir die Struktur an
        flight_format = {
            "price": cheapest.get("price"),
            "bags_price": cheapest.get("bags_price") or {},
            "airlines": cheapest.get("airlines") or [],
            "deep_link": cheapest.get("deep_link") or "",
            "local_departure": cheapest.get("local_departure", ""),
            "local_arrival": cheapest.get("local_arrival", ""),
            "duration": cheapest.get("duration") or {},
            "route": cheapest.get("route") or [],
            "date": cheapest.get("date")
        }
        return flight_format, True
        
    print(f"  [Warning] RapidAPI lieferte keine Ergebnisse für Pod '{pod_id}'.")
    return None, False


def run_tracker() -> None:
    """
    Hauptfunktion des Trackers.
    """
    try:
        config = load_config()
    except Exception as e:
        print(f"Fehler beim Laden der Konfiguration: {e}")
        return

    print("[Info] RapidAPI (Kiwi.com) Modus aktiviert.\n")

    search_settings = config.get("search_settings", {})
    travel_pods = config.get("travel_pods", {})
    hinfluege = travel_pods.get("hinfluege", [])
    rueckfluege = travel_pods.get("rueckfluege", [])

    all_pods = [(pod, "Hinflug") for pod in hinfluege] + [(pod, "Rückflug") for pod in rueckfluege]
    
    print(f"Starte Abfrage für insgesamt {len(all_pods)} Pods...\n")
    
    for pod, direction in all_pods:
        pod_id = pod.get("id")
        bags_to_add = pod.get("bags_to_add", 0)
        
        print(f"Verarbeite {direction} '{pod_id}' ({pod.get('from')} -> {pod.get('to')})...")
        
        flight, is_live = fetch_flights_for_pod(pod, search_settings)
        
        if flight:
            bag_cost, total_price = calculate_price_with_bags(flight, bags_to_add)
            
            airlines = flight.get("airlines", [])
            if not airlines and "route" in flight:
                airlines = list(dict.fromkeys([seg.get("airline") for seg in flight["route"] if seg.get("airline")]))
            airline_str = ", ".join(airlines) if airlines else "Unknown"
            
            booking_link = flight.get("deep_link")
            is_live_val = 1 if is_live else 0
            flight_date = flight.get("date", "-")
            
            latest_price = get_latest_price(pod_id)
            
            if latest_price is not None:
                diff = latest_price - total_price
                if diff > 10.0:
                    msg = (
                        f"🚨 <b>Flugpreis gesunken!</b> 🚨\n"
                        f"<b>Pod:</b> <code>{pod_id}</code> ({direction})\n"
                        f"<b>Route:</b> {pod.get('from')} ➔ {pod.get('to')}\n"
                        f"<b>Datum:</b> {flight_date}\n"
                        f"<b>Alter Preis:</b> {latest_price:.2f} EUR\n"
                        f"<b>Neuer Preis:</b> {total_price:.2f} EUR (Ersparnis: {diff:.2f} EUR)\n"
                        f"<b>Airline:</b> {airline_str}\n"
                        f"<b>Link:</b> <a href=\"{booking_link}\">Jetzt buchen</a>"
                    )
                    send_telegram_notification(msg, silent=False)
                elif total_price > latest_price:
                    diff_rise = total_price - latest_price
                    msg = (
                        f"📈 <b>Flugpreis gestiegen</b>\n"
                        f"<b>Pod:</b> <code>{pod_id}</code> ({direction})\n"
                        f"<b>Route:</b> {pod.get('from')} ➔ {pod.get('to')}\n"
                        f"<b>Datum:</b> {flight_date}\n"
                        f"<b>Alter Preis:</b> {latest_price:.2f} EUR\n"
                        f"<b>Neuer Preis:</b> {total_price:.2f} EUR (Differenz: +{diff_rise:.2f} EUR)\n"
                        f"<b>Airline:</b> {airline_str}\n"
                        f"<b>Link:</b> <a href=\"{booking_link}\">Details ansehen</a>"
                    )
                    send_telegram_notification(msg, silent=True)
                else:
                    print(f"  -> Preisänderung ({latest_price:.2f} EUR -> {total_price:.2f} EUR) löst keine Benachrichtigung aus.")
            else:
                print(f"  -> Erster Eintrag für Pod '{pod_id}' in der Datenbank (kein historischer Vergleich möglich).")

            try:
                insert_flight(
                    pod_id=pod_id,
                    price=total_price,
                    airline=airline_str,
                    booking_link=booking_link,
                    is_live_check=is_live_val,
                    flight_date=flight_date
                )
                print(f"  -> Günstigster Preis gefunden: {total_price:.2f} EUR (inkl. {bag_cost:.2f} EUR Gepäck)")
                print(f"  -> Airline: {airline_str} | Link: {booking_link[:50]}...")
                print(f"  -> In Datenbank gespeichert.")
            except Exception as db_err:
                print(f"  -> Fehler beim Speichern in die Datenbank: {db_err}")
        else:
            print(f"  -> Kein passender Flug für Pod {pod_id} gefunden.")
        print()

if __name__ == "__main__":
    init_db()
    run_tracker()
