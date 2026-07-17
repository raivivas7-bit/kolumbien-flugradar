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
    Sende einen GET-Request an den Oneway-Search-Endpoint der Kiwi RapidAPI.
    Unterstützt sowohl einzelne Reisedaten als auch Datumsbereiche (z.B. "2026-07-31..2026-08-03").
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
    # Wenn ein Datumsbereich (mit "..") vorliegt, konvertiere beide Daten
    api_date = date
    if ".." in date:
        parts = date.split("..")
        try:
            d1 = datetime.datetime.strptime(parts[0], "%d/%m/%Y").strftime("%Y-%m-%d")
            d2 = datetime.datetime.strptime(parts[1], "%d/%m/%Y").strftime("%Y-%m-%d")
            api_date = f"{d1}..{d2}"
        except ValueError:
            pass
    else:
        try:
            api_date = datetime.datetime.strptime(date, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
        
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
            
        # FILTER: Only keep itineraries where departure and arrival match exactly the requested IATA codes
        valid_itineraries = []
        for it in itineraries:
            out_segments = it.get("outbound", {}).get("segments", [])
            if out_segments:
                dep_airport = out_segments[0].get("source", {}).get("station", {}).get("code", "")
                arr_airport = out_segments[-1].get("destination", {}).get("station", {}).get("code", "")
                if dep_airport.upper() == start.upper() and arr_airport.upper() == dest.upper():
                    valid_itineraries.append(it)
                    
        if not valid_itineraries:
            return None
            
        cheapest = min(valid_itineraries, key=lambda x: x.get("price", {}).get("amount", float('inf')))
        
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
            
        # Extrahiere das Datum aus dem Hinflug-Segment
        segments = cheapest.get("outbound", {}).get("segments", [])
        flight_date_str = date
        if segments:
            local_time = segments[0].get("source", {}).get("local_time", "")
            if "T" in local_time:
                try:
                    dt = datetime.datetime.strptime(local_time.split("T")[0], "%Y-%m-%d")
                    flight_date_str = dt.strftime("%d/%m/%Y")
                except ValueError:
                    pass
            
        return {
            "price": float(price_val),
            "airlines": airlines,
            "deep_link": booking_link,
            "bags_price": cheapest.get("bags_price", {}),
            "date": flight_date_str
        }
    except Exception as e:
        print(f"  [RapidAPI-Fehler] Ausnahme bei Oneway-Anfrage: {e}")
        return None

def fetch_flight_price_roundtrip(start: str, dest: str, date_out: str, date_in: str, passengers_count: int, currency: str = "EUR") -> Optional[dict]:
    """
    Sende einen GET-Request an den Roundtrip-Search-Endpoint der Kiwi RapidAPI.
    Unterstützt sowohl einzelne Reisedaten als auch Datumsbereiche (z.B. "2026-07-31..2026-08-03").
    """
    key, host = get_rapidapi_credentials()
    if not key or not host:
        print("  [RapidAPI] Fehler: RAPIDAPI_KEY oder RAPIDAPI_HOST fehlt in der Konfiguration!")
        return None
        
    url = f"https://{host}/api/v1/flights/search-roundtrip"
    
    headers = {
        "x-rapidapi-key": key,
        "x-rapidapi-host": host
    }
    
    # Konvertiere Hinflugs- und Rückflugsdaten
    api_date_out = date_out
    if ".." in date_out:
        parts = date_out.split("..")
        try:
            d1 = datetime.datetime.strptime(parts[0], "%d/%m/%Y").strftime("%Y-%m-%d")
            d2 = datetime.datetime.strptime(parts[1], "%d/%m/%Y").strftime("%Y-%m-%d")
            api_date_out = f"{d1}..{d2}"
        except ValueError:
            pass
    else:
        try:
            api_date_out = datetime.datetime.strptime(date_out, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
            
    api_date_in = date_in
    if ".." in date_in:
        parts = date_in.split("..")
        try:
            d1 = datetime.datetime.strptime(parts[0], "%d/%m/%Y").strftime("%Y-%m-%d")
            d2 = datetime.datetime.strptime(parts[1], "%d/%m/%Y").strftime("%Y-%m-%d")
            api_date_in = f"{d1}..{d2}"
        except ValueError:
            pass
    else:
        try:
            api_date_in = datetime.datetime.strptime(date_in, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
        
    params = {
        "source": start,
        "destination": dest,
        "departure_date": api_date_out,
        "return_date": api_date_in,
        "currency": currency,
        "adults": passengers_count,
        "limit": 5
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
            
        # FILTER: Only keep itineraries where departure and arrival match exactly the requested IATA codes for both outbound and inbound
        valid_itineraries = []
        for it in itineraries:
            out_segments = it.get("outbound", {}).get("segments", [])
            in_segments = it.get("inbound", {}).get("segments", [])
            if out_segments and in_segments:
                dep_out = out_segments[0].get("source", {}).get("station", {}).get("code", "")
                arr_out = out_segments[-1].get("destination", {}).get("station", {}).get("code", "")
                dep_in = in_segments[0].get("source", {}).get("station", {}).get("code", "")
                arr_in = in_segments[-1].get("destination", {}).get("station", {}).get("code", "")
                
                if (dep_out.upper() == start.upper() and arr_out.upper() == dest.upper() and 
                    dep_in.upper() == dest.upper() and arr_in.upper() == start.upper()):
                    valid_itineraries.append(it)
                    
        if not valid_itineraries:
            return None
            
        cheapest = min(valid_itineraries, key=lambda x: x.get("price", {}).get("amount", float('inf')))
        
        price_val = cheapest.get("price", {}).get("amount")
        if price_val is None:
            return None
            
        # Extrahiere Carrier-Namen
        carriers = cheapest.get("outbound", {}).get("carriers", [])
        if "inbound" in cheapest and cheapest["inbound"]:
            carriers += cheapest.get("inbound", {}).get("carriers", [])
            
        airlines = list(dict.fromkeys([c.get("name", "Unknown Airline") for c in carriers if c.get("name")]))
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
            "bags_price": cheapest.get("bags_price", {})
        }
    except Exception as e:
        print(f"  [RapidAPI-Fehler] Ausnahme bei Roundtrip-Anfrage: {e}")
        return None

def calculate_price_with_bags(flight: dict, bags_to_add: int, is_roundtrip: bool = False) -> Tuple[float, float]:
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
        multiplier = 2 if is_roundtrip else 1
        bag_cost = 45.0 * bags_to_add * multiplier
                
    return bag_cost, base_price + bag_cost

def find_pod_pairs(hinfluege: List[dict], rueckfluege: List[dict]) -> List[Tuple[dict, dict]]:
    """
    Findet Hinflug- und Rückflug-Pods, die zusammengehören, basierend auf überlappenden Passagieren.
    """
    pairs = []
    for hin in hinfluege:
        hin_pax = set(hin.get("passengers", []))
        for rueck in rueckfluege:
            rueck_pax = set(rueck.get("passengers", []))
            # Wenn mindestens ein Passagier übereinstimmt
            if hin_pax.intersection(rueck_pax):
                pairs.append((hin, rueck))
    return pairs

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

    # Paarbildung der Flüge
    pod_pairs = find_pod_pairs(hinfluege, rueckfluege)
    
    print(f"Starte Abfrage für insgesamt {len(pod_pairs)} Flug-Kombinationen...\n")
    
    currency = search_settings.get("currency", "EUR")
    is_live_check = True
    
    for hin_pod, rueck_pod in pod_pairs:
        hin_id = hin_pod.get("id")
        rueck_id = rueck_pod.get("id")
        pod_pair_id = f"{hin_id}__{rueck_id}"
        
        # Gepäck und Passagiere basieren auf der Rückflug-Gruppe (Ziel-Vergleichs-Gruppe)
        bags_to_add = rueck_pod.get("bags_to_add", 0)
        passengers_count = len(rueck_pod.get("passengers", ["P"]))
        
        print(f"Verarbeite Kombination: {pod_pair_id} ({hin_pod.get('from')} -> {hin_pod.get('to')} / {rueck_pod.get('from')} -> {rueck_pod.get('to')})...")
        
        # Datumsbereiche erstellen
        date_range_hin = f"{hin_pod['date_from']}..{hin_pod['date_to']}"
        date_range_zurueck = f"{rueck_pod['date_from']}..{rueck_pod['date_to']}"
        
        origins_hin = [o.strip() for o in hin_pod.get("from", "").split(",") if o.strip()]
        dests_hin = [d.strip() for d in hin_pod.get("to", "").split(",") if d.strip()]
        origins_zurueck = [o.strip() for o in rueck_pod.get("from", "").split(",") if o.strip()]
        dests_zurueck = [d.strip() for d in rueck_pod.get("to", "").split(",") if d.strip()]
        
        # 1. Hinflug Oneway Abfrage
        print("  -> Query Outbound Oneway...")
        cheapest_hin = None
        for org in origins_hin:
            for dst in dests_hin:
                flight = fetch_flight_price_rapidapi(org, dst, date_range_hin, passengers_count, currency)
                if flight:
                    if cheapest_hin is None or flight["price"] < cheapest_hin["price"]:
                        cheapest_hin = flight
                time.sleep(1.0)
                
        # 2. Rückflug Oneway Abfrage
        print("  -> Query Inbound Oneway...")
        cheapest_zurueck = None
        for org in origins_zurueck:
            for dst in dests_zurueck:
                flight = fetch_flight_price_rapidapi(org, dst, date_range_zurueck, passengers_count, currency)
                if flight:
                    if cheapest_zurueck is None or flight["price"] < cheapest_zurueck["price"]:
                        cheapest_zurueck = flight
                time.sleep(1.0)
                
        # 3. Roundtrip Abfrage
        print("  -> Query Combined Roundtrip...")
        cheapest_rt = None
        for org in origins_hin:
            for dst in dests_hin:
                flight = fetch_flight_price_roundtrip(org, dst, date_range_hin, date_range_zurueck, passengers_count, currency)
                if flight:
                    if cheapest_rt is None or flight["price"] < cheapest_rt["price"]:
                        cheapest_rt = flight
                time.sleep(1.0)
                
        if cheapest_hin and cheapest_zurueck and cheapest_rt:
            # Gepäck und Gesamtkosten berechnen
            bag_cost_hin, price_hin = calculate_price_with_bags(cheapest_hin, bags_to_add, is_roundtrip=False)
            bag_cost_zurueck, price_zurueck = calculate_price_with_bags(cheapest_zurueck, bags_to_add, is_roundtrip=False)
            price_oneway_total = price_hin + price_zurueck
            
            bag_cost_rt, price_rt = calculate_price_with_bags(cheapest_rt, bags_to_add, is_roundtrip=True)
            
            airline_hin_str = ", ".join(cheapest_hin.get("airlines", []))
            airline_zurueck_str = ", ".join(cheapest_zurueck.get("airlines", []))
            airline_rt_str = ", ".join(cheapest_rt.get("airlines", []))
            
            booking_link_hin = cheapest_hin.get("deep_link")
            booking_link_zurueck = cheapest_zurueck.get("deep_link")
            booking_link_rt = cheapest_rt.get("deep_link")
            
            flight_date_hin = cheapest_hin.get("date")
            flight_date_zurueck = cheapest_zurueck.get("date")
            
            # Bester Deal ermitteln
            if price_oneway_total < price_rt:
                winner = "Option A (Getrennt gebucht)"
                savings = price_rt - price_oneway_total
            else:
                winner = "Option B (Zusammen gebucht)"
                savings = price_oneway_total - price_rt
                
            current_cheapest = min(price_oneway_total, price_rt)
            
            # Schwellenwert-Logik mit dem jeweils günstigsten Weg
            latest_cheapest = get_latest_price(pod_pair_id)
            
            if latest_cheapest is not None:
                diff = latest_cheapest - current_cheapest
                if diff > 10.0:
                    msg = (
                        f"🚨 <b>Flugpreis gesunken! ({winner})</b> 🚨\n"
                        f"<b>Kombination:</b> <code>{pod_pair_id}</code>\n"
                        f"<b>Route:</b> {hin_pod.get('from')} ➔ {hin_pod.get('to')} / {rueck_pod.get('from')} ➔ {rueck_pod.get('to')}\n\n"
                        f"🎫 <b>Option A (Getrennt gebucht):</b>\n"
                        f"  • Hin ({flight_date_hin}): {price_hin:.2f} EUR ({airline_hin_str})\n"
                        f"  • Zurück ({flight_date_zurueck}): {price_zurueck:.2f} EUR ({airline_zurueck_str})\n"
                        f"  • <b>Gesamt:</b> {price_oneway_total:.2f} EUR\n\n"
                        f"🔄 <b>Option B (Zusammen gebucht):</b>\n"
                        f"  • Kombi-Ticket: {price_rt:.2f} EUR ({airline_rt_str})\n\n"
                        f"💡 <b>Ersparnis bei {winner}:</b> {savings:.2f} EUR!\n"
                    )
                    if price_oneway_total < price_rt:
                        msg += f"🔗 Link: <a href=\"{booking_link_hin}\">Hinflug</a> | <a href=\"{booking_link_zurueck}\">Rückflug</a>"
                    else:
                        msg += f"🔗 Link: <a href=\"{booking_link_rt}\">Kombi-Ticket buchen</a>"
                    send_telegram_notification(msg, silent=False)
                    
                elif current_cheapest > latest_cheapest:
                    diff_rise = current_cheapest - latest_cheapest
                    msg = (
                        f"📈 <b>Flugpreis gestiegen</b>\n"
                        f"<b>Kombination:</b> <code>{pod_pair_id}</code>\n"
                        f"<b>Route:</b> {hin_pod.get('from')} ➔ {hin_pod.get('to')} / {rueck_pod.get('from')} ➔ {rueck_pod.get('to')}\n\n"
                        f"🎫 <b>Option A (Getrennt gebucht):</b>\n"
                        f"  • Hin ({flight_date_hin}): {price_hin:.2f} EUR\n"
                        f"  • Zurück ({flight_date_zurueck}): {price_zurueck:.2f} EUR\n"
                        f"  • <b>Gesamt:</b> {price_oneway_total:.2f} EUR\n\n"
                        f"🔄 <b>Option B (Zusammen gebucht):</b>\n"
                        f"  • Kombi-Ticket: {price_rt:.2f} EUR\n\n"
                        f"💡 <b>Neuer Bestpreis:</b> {current_cheapest:.2f} EUR (Differenz: +{diff_rise:.2f} EUR)\n"
                    )
                    send_telegram_notification(msg, silent=True)
                else:
                    print(f"  -> Preisänderung (Letzter Bestpreis: {latest_cheapest:.2f} EUR -> Neuer Bestpreis: {current_cheapest:.2f} EUR) löst keine Benachrichtigung aus.")
            else:
                print(f"  -> Erster Eintrag für Kombination '{pod_pair_id}' in der Datenbank (kein historischer Vergleich möglich).")

            try:
                insert_flight(
                    pod_id=pod_pair_id,
                    price_oneway_hin=price_hin,
                    price_oneway_zurueck=price_zurueck,
                    price_oneway_total=price_oneway_total,
                    price_roundtrip=price_rt,
                    airline_hin=airline_hin_str,
                    airline_zurueck=airline_zurueck_str,
                    airline_roundtrip=airline_rt_str,
                    booking_link_hin=booking_link_hin,
                    booking_link_zurueck=booking_link_zurueck,
                    booking_link_roundtrip=booking_link_rt,
                    flight_date_hin=flight_date_hin,
                    flight_date_zurueck=flight_date_zurueck,
                    is_live_check=is_live_check
                )
                print(f"  -> Preise erfolgreich gespeichert:")
                print(f"     Oneways: {price_hin:.2f} EUR + {price_zurueck:.2f} EUR = {price_oneway_total:.2f} EUR")
                print(f"     Roundtrip: {price_rt:.2f} EUR")
                print(f"     Bester Weg: {winner}")
            except Exception as db_err:
                print(f"  -> Fehler beim Speichern in die Datenbank: {db_err}")
        else:
            print(f"  -> [Warning] Unvollständige Flugdaten für Pod-Kombination '{pod_pair_id}'.")
        print()

if __name__ == "__main__":
    init_db()
    run_tracker()
