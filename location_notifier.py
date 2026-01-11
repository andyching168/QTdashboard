import sys
import time
import json
import serial
import requests
import glob
import threading
import os
import xml.etree.ElementTree as ET
from datetime import datetime

# Configuration Path
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"[-] Config file not found: {CONFIG_PATH}")
        return None
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[-] Error loading config: {e}")
        return None

def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("[+] Telegram message sent successfully.")
            return True
        else:
            print(f"[-] Telegram send failed: {response.text}")
            return False
    except Exception as e:
        print(f"[-] Telegram error: {e}")
        return False

CPC_PRICE_URL = "https://vipmbr.cpc.com.tw/cpcstn/listpricewebservice.asmx/getCPCMainProdListPrice"

def get_cpc_fuel_prices(timeout=10):
    """Fetch current CPC fuel prices from API"""
    try:
        response = requests.post(CPC_PRICE_URL, timeout=timeout, verify=False)
        if response.status_code == 200:
            return response.text
        else:
            print(f"[-] CPC API request failed: {response.status_code}")
            return None
    except Exception as e:
        print(f"[-] CPC API error: {e}")
        return None

def parse_fuel_prices(xml_data):
    """Parse CPC XML response and extract fuel prices"""
    prices = {}
    try:
        root = ET.fromstring(xml_data)
        # Elements don't have namespace prefix, search directly
        for tbTable in root.findall('.//tbTable'):
            name = tbTable.find('產品名稱')
            price = tbTable.find('參考牌價')
            if name is not None and price is not None and name.text:
                try:
                    prices[name.text] = float(price.text)
                except (ValueError, TypeError):
                    pass
        return prices
    except Exception as e:
        print(f"[-] XML parse error: {e}")
        return prices

def get_fuel_price_by_type(prices, fuel_type='95無鉛汽油'):
    """Get price for specific fuel type, fallback to 95 if not found"""
    if fuel_type in prices:
        return prices[fuel_type]
    # Try different common names
    for name, price in prices.items():
        if fuel_type in name or name in fuel_type:
            return price
    # Default to 95 unleaded if available
    return prices.get('95無鉛汽油')

def parse_nmea_coords(line):
    """
    Parse NMEA GPGGA or GPRMC line to extract lat/lon and fix status.
    Returns (lat_dd, lon_dd, is_fixed) or None.
    is_fixed is True if GPS reports valid fix (A or Quality > 0).
    """
    try:
        line = line.decode('ascii', errors='ignore').strip()
        if not line.startswith('$'):
            return None
            
        parts = line.split(',')
        
        # GPGGA: $GPGGA,time,lat,ns,lon,ew,quality,sats...
        # GNRMC: $GNRMC,time,status,lat,ns,lon,ew...
        
        lat_raw = ""
        ns = ""
        lon_raw = ""
        ew = ""
        is_fixed = False
        
        if line.startswith('$GNGGA') or line.startswith('$GPGGA'):
            if len(parts) < 6: return None
            # Quality '0' is invalid, anything else is a fix (1=GPS, 2=DGPS...)
            if parts[6] != '0': is_fixed = True
            
            lat_raw = parts[2]
            ns = parts[3]
            lon_raw = parts[4]
            ew = parts[5]
            
        elif line.startswith('$GNRMC') or line.startswith('$GPRMC'):
            if len(parts) < 7: return None
            # Status 'A' is Active(Valid), 'V' is Void
            if parts[2] == 'A': is_fixed = True
            
            lat_raw = parts[3]
            ns = parts[4]
            lon_raw = parts[5]
            ew = parts[6]
        else:
            return None
            
        # Check for empty or zero coordinates
        if not lat_raw or not lon_raw:
            return None
            
        try:
            if float(lat_raw) == 0.0 or float(lon_raw) == 0.0:
                return None
        except ValueError:
            return None
            
        # Convert DDMM.MMMM to Decimal Degrees safely
        # Matches both 12345.67 (123d 45.67m) and 1234.56 (12d 34.56m)
        lat_f = float(lat_raw)
        lat_deg = int(lat_f / 100)
        lat_min = lat_f % 100
        lat_dd = lat_deg + (lat_min / 60.0)
        if ns == 'S': lat_dd = -lat_dd
        
        lon_f = float(lon_raw)
        lon_deg = int(lon_f / 100)
        lon_min = lon_f % 100
        lon_dd = lon_deg + (lon_min / 60.0)
        if ew == 'W': lon_dd = -lon_dd
        
        return lat_dd, lon_dd, is_fixed
        
    except Exception:
        return None

def find_gps_and_get_location(timeout=10):
    """
    Scans for GPS, waits up to timeout for a FIX.
    If timeout reached without fix, returns last non-zero coords (approximate).
    Returns (lat, lon, is_approx) or None.
    """
    # 掃描可能的連接埠
    potential_ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*') + glob.glob('/dev/pts/*')
    baud_rates = [38400, 9600, 115200, 4800]
    
    # print(f"[*] Scanning ports: {potential_ports}")
    
    total_start_time = time.time()
    
    # First pass: Find the correct port/baud that emits NMEA
    locked_port = None
    locked_baud = None
    
    for port in potential_ports:
        if locked_port: break
        
        for baud in baud_rates:
            if time.time() - total_start_time > timeout:
                break
                
            print(f"[*] Probing {port} @ {baud}...")
            try:
                with serial.Serial(port, baud, timeout=0.5) as ser:
                    # Quick check (1.5s) to see if we get intelligible data
                    check_start = time.time()
                    valid_nmea_count = 0
                    while time.time() - check_start < 1.5:
                        try:
                            line = ser.readline()
                            if not line: continue
                            # Check for basic NMEA signature
                            line_str = line.decode('ascii', errors='ignore').strip()
                            if line_str.startswith('$') and '*' in line_str:
                                valid_nmea_count += 1
                                if valid_nmea_count >= 2:
                                    locked_port = port
                                    locked_baud = baud
                                    print(f"[+] GPS Detected on {port} @ {baud}!")
                                    break
                        except Exception:
                            continue
                    if locked_port: break
            except serial.SerialException:
                pass
    
    if not locked_port:
        print("[-] Could not identify any GPS device.")
        return None

    # Second pass: Wait for FIX
    remaining_time = timeout - (time.time() - total_start_time)
    if remaining_time < 5: remaining_time = 5 # Minimum wait time
    
    print(f"[*] Waiting for valid GPS Fix on {locked_port} (Max wait: {remaining_time:.1f}s)...")
    
    last_approx_coords = None
    
    try:
        with serial.Serial(locked_port, locked_baud, timeout=1) as ser:
            wait_start = time.time()
            
            while time.time() - wait_start < remaining_time:
                line = ser.readline()
                if not line: continue
                
                # print(f"DEBUG RAW: {line}")
                result = parse_nmea_coords(line)
                if result:
                    lat, lon, is_fixed = result
                    # print(f"DEBUG PARSED: {lat}, {lon}, Fix={is_fixed}")
                else:
                    pass
                    # print("DEBUG PARSED: None")
                
                if result:
                    lat, lon, is_fixed = result
                    
                    if is_fixed:
                        print(f"[+] FIX ACQUIRED: {lat}, {lon}")
                        return lat, lon, False # is_approx = False
                    else:
                        # Found non-zero coords but not fixed yet
                        if last_approx_coords != (lat, lon):
                             print(f"    Found approx coords: {lat}, {lon} (Not fixed yet)")
                        last_approx_coords = (lat, lon)
                             
    except serial.SerialException as e:
        print(f"[-] Error reading locked port: {e}")
        
    if last_approx_coords:
        print(f"[!] Timeout. Using last known approximate coords: {last_approx_coords}")
        return last_approx_coords[0], last_approx_coords[1], True # is_approx = True
    
    print("[-] Timeout and no coordinates found.")
    return None

def notify_current_location(fuel_level=None, avg_fuel=None, elapsed_time=None, trip_distance=None):
    """
    Main entry point to be called by shutdown monitor.
    Args:
        fuel_level: float or None, current fuel percentage.
        avg_fuel: float or None, average fuel consumption (L/100km).
        elapsed_time: str or None, trip elapsed time in "hh:mm" format.
        trip_distance: float or None, trip distance in km.
    """
    print(f"[Notifier] Starting location notification sequence... (Fuel: {fuel_level}, Avg Fuel: {avg_fuel}, Elapsed: {elapsed_time}, Trip Dist: {trip_distance})")
    
    config = load_config()
    if not config:
        print("[Notifier] No config, aborting.")
        return

    token = config.get('telegram_bot_token')
    chat_id = config.get('telegram_chat_id')
    
    if not token or not chat_id or "YOUR_" in token:
        print("[Notifier] Invalid credentials in config.")
        return

    # Find GPS
    result = find_gps_and_get_location(timeout=10)
    
    if result:
        lat, lon, is_approx = result
        
        maps_url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
        
        note = " (約略位置)" if is_approx else ""
        fuel_str = f"⛽ 油量: {fuel_level:.0f}%\n" if fuel_level is not None else ""

        # 格式化運行時間
        time_str = f"🕐 行駛時間: {elapsed_time}\n" if elapsed_time else ""

        # 格式化行駛距離
        dist_str = f"📏 本次里程: {trip_distance:.1f} km\n" if trip_distance is not None and trip_distance > 0 else ""

        # 計算消耗油量 = 平均油耗 * 距離 / 100
        fuel_consumed = 0.0
        if avg_fuel is not None and avg_fuel > 0 and trip_distance is not None and trip_distance > 0:
            fuel_consumed = (avg_fuel * trip_distance) / 100
            fuel_consumed_str = f"⛽ 消耗油量: {fuel_consumed:.2f} L\n"
        else:
            fuel_consumed_str = ""

        avg_fuel_str = f"📊 平均油耗: {avg_fuel:.1f} L/100km\n" if avg_fuel is not None and avg_fuel > 0 else ""

        # Fetch CPC fuel prices and calculate cost
        fuel_cost_str = ""
        if fuel_consumed > 0:
            xml_data = get_cpc_fuel_prices()
            if xml_data:
                prices = parse_fuel_prices(xml_data)
                fuel_price = get_fuel_price_by_type(prices, '95無鉛汽油')
                if fuel_price:
                    cost = fuel_consumed * fuel_price
                    fuel_cost_str = f"💰 推估油錢: ${cost:.0f} (95: ${fuel_price:.1f}/L)\n"
                    print(f"[Notifier] Fuel price: {fuel_price}, Consumed: {fuel_consumed}L, Cost: ${cost}")
                else:
                    print("[Notifier] Could not find fuel price")
            else:
                print("[Notifier] Failed to fetch CPC prices")

        message = f"🚗 車輛已熄火\n{time_str}{dist_str}{fuel_str}{avg_fuel_str}{fuel_consumed_str}{fuel_cost_str}📍 位置: {lat:.6f}, {lon:.6f}{note}\n🔗 {maps_url}"
        send_telegram_message(token, chat_id, message)
    else:
        print("[GPS] 未找到 GPS 位置，發送無位置通知")
        fuel_str = f"⛽ 油量: {fuel_level:.0f}%\n" if fuel_level is not None else ""

        time_str = f"🕐 行駛時間: {elapsed_time}\n" if elapsed_time else ""
        dist_str = f"📏 本次里程: {trip_distance:.1f} km\n" if trip_distance is not None and trip_distance > 0 else ""

        fuel_consumed = 0.0
        if avg_fuel is not None and avg_fuel > 0 and trip_distance is not None and trip_distance > 0:
            fuel_consumed = (avg_fuel * trip_distance) / 100
            fuel_consumed_str = f"⛽ 消耗油量: {fuel_consumed:.2f} L\n"
        else:
            fuel_consumed_str = ""

        avg_fuel_str = f"📊 平均油耗: {avg_fuel:.1f} L/100km\n" if avg_fuel is not None and avg_fuel > 0 else ""

        fuel_cost_str = ""
        if fuel_consumed > 0:
            print(f"[Notifier] Fetching CPC prices... fuel_consumed={fuel_consumed}")
            xml_data = get_cpc_fuel_prices()
            print(f"[Notifier] CPC response: {xml_data[:200] if xml_data else None}...")
            if xml_data:
                prices = parse_fuel_prices(xml_data)
                print(f"[Notifier] Parsed prices: {prices}")
                fuel_price = get_fuel_price_by_type(prices, '95無鉛汽油')
                print(f"[Notifier] Fuel price: {fuel_price}")
                if fuel_price:
                    cost = fuel_consumed * fuel_price
                    fuel_cost_str = f"💰 推估油錢: ${cost:.0f} (95: ${fuel_price:.1f}/L)\n"
                else:
                    print("[Notifier] Could not find fuel price")
            else:
                print("[Notifier] Failed to fetch CPC prices")

        message = f"🚗 車輛已熄火（無 GPS 定位）\n{time_str}{dist_str}{fuel_str}{avg_fuel_str}{fuel_consumed_str}{fuel_cost_str}"
        send_telegram_message(token, chat_id, message)

if __name__ == "__main__":
    # Test mode
    notify_current_location()
