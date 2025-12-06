import sys
import time
import json
import serial
import requests
import glob
import threading
import os

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
    potential_ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
    baud_rates = [38400, 9600, 115200, 4800]
    
    print(f"[*] Scanning ports: {potential_ports}")
    
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
                
                result = parse_nmea_coords(line)
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

def notify_current_location():
    """
    Main entry point to be called by shutdown monitor.
    """
    print("[Notifier] Starting location notification sequence...")
    
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
        
        message = f"🚗 車輛已熄火\n📍 位置: {lat:.6f}, {lon:.6f}{note}\n🔗 {maps_url}"
        send_telegram_message(token, chat_id, message)
    else:
        print("[GPS] 未找到 GPS 位置")
        # Optional: Send a "Last known location unknown" message?
        # send_telegram_message(token, chat_id, "🚗 Car Engine OFF. GPS Fix not available.")

if __name__ == "__main__":
    # Test mode
    notify_current_location()
