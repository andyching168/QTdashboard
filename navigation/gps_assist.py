import sys
import time
import socket
import serial
import requests
import argparse
import os

# Configuration Defaults (Can be overridden by arguments)
DEFAULT_SERIAL_PORT = '/dev/ttyUSB0'
DEFAULT_BAUDRATE = 9600
# Example u-blox AssistNow Online URL (Requires a valid token to actually work)
# Users should register at u-blox to get their own token.
DEFAULT_AGPS_BASE_URL = "https://online-live1.services.u-blox.com/GetOnlineData.ashx"
DEFAULT_TOKEN = "INSERT_YOUR_UBLOX_TOKEN_HERE" 

def check_internet(host="8.8.8.8", port=53, timeout=3):
    """
    Check if internet is available by trying to connect to a known host.
    """
    print(f"[*] Checking internet connectivity to {host}...")
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        print("[+] Internet connection detected.")
        return True
    except socket.error as ex:
        print(f"[-] No internet connection: {ex}")
        return False

def download_ephemeris(token, save_path="ephemeris_data.ubx"):
    """
    Download A-GPS data (ephemeris) from a service.
    This default implementation targets u-blox AssistNow Online.
    """
    print("[*] Attempting to download ephemeris data...")
    
    if "INSERT_YOUR" in token:
        print("[!] WARNING: Default token is still set.")
        print("    You need a FREE u-blox AssistNow token to download data.")
        print("    Register here: https://www.u-blox.com/en/assistnow-service-registration")
        print("    Then run: python gps_assist.py --token YOUR_NEW_TOKEN")
        return None
    
    # Construct URL for u-blox (example parameters for GPS+GLONASS, specific format)
    # format=mga means UBX-MGA format for M8/M9/M10 modules. 
    # format=aid means legacy UBX-AID format for older modules like NEO-6/7.
    try:
        print(f"[*] Requesting data from u-blox (Token: {token[:5]}...)...")
        # Added more comprehensive parameters sometimes needed
        params = {
            'token': token,
            'gnss': 'gps,glo', # GPS + GLONASS
            'datatype': 'eph,alm,aux', # Ephemeris, Almanac, Aux
            'format': 'mga' 
        }
        
        response = requests.get(DEFAULT_AGPS_BASE_URL, params=params, timeout=10)
        
        if response.status_code == 403:
             print("[-] Error 403: Invalid Token. Please verify your u-blox token.")
             return None
        
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
            
        print(f"[+] Ephemeris data downloaded successfully ({len(response.content)} bytes).")
        return save_path
    
    except requests.RequestException as e:
        print(f"[-] Failed to download ephemeris: {e}")
        print("    Tip: If you cannot get online, your u-blox GPS supports 'AssistNow Autonomous'.")
        print("         It will self-calculate orbits after 15-30 mins of continuous run time.")
        return None

def upload_ephemeris(serial_port, baudrate, file_path):
    """
    Upload the binary ephemeris data to the GPS module via serial.
    """
    if not os.path.exists(file_path):
        print(f"[-] File {file_path} not found. Skipping upload.")
        return

    print(f"[*] Opening serial port {serial_port} @ {baudrate} baud...")
    try:
        with serial.Serial(serial_port, baudrate, timeout=1) as ser:
            print(f"[*] Uploading {file_path} to GPS module...")
            with open(file_path, 'rb') as f:
                data = f.read()
                # Write data in chunks to avoid overwhelming the buffer
                chunk_size = 512
                total_sent = 0
                for i in range(0, len(data), chunk_size):
                    chunk = data[i:i+chunk_size]
                    ser.write(chunk)
                    total_sent += len(chunk)
                    sys.stdout.write(f"\r    Sent {total_sent}/{len(data)} bytes")
                    sys.stdout.flush()
                    # Small delay to let the UART buffer drain/process
                    time.sleep(0.05) 
            print("\n[+] Upload complete.")
            
    except serial.SerialException as e:
        print(f"\n[-] Serial error: {e}")

def parse_nmea(line):
    """
    Simple NMEA parser to extract basic info.
    """
    try:
        if line.startswith(b'$GNGGA') or line.startswith(b'$GPGGA'):
            parts = line.decode('ascii', errors='replace').strip().split(',')
            if len(parts) > 7:
                time_utc = parts[1]
                lat = parts[2]
                lon = parts[4]
                fix_quality = parts[6]
                num_sats = parts[7]
                print(f"   [GPS Status] Time: {time_utc} | Fix: {fix_quality} | Sats: {num_sats} | Lat/Lon: {lat}/{lon}")
                
        elif line.startswith(b'$GNRMC') or line.startswith(b'$GPRMC'):
            parts = line.decode('ascii', errors='replace').strip().split(',')
            if len(parts) > 2:
                status = parts[2] # A=Active, V=Void
                print(f"   [GPS RMC] Status: {'Valid' if status == 'A' else 'Invalid'}")
                
    except Exception:
        pass

def monitor_status(serial_port, baudrate, duration=30, debug=False):
    """
    Monitor the GPS output for a set duration to show status.
    """
    print(f"[*] Monitoring GPS status for {duration} seconds...")
    try:
        with serial.Serial(serial_port, baudrate, timeout=1) as ser:
            start_time = time.time()
            while time.time() - start_time < duration:
                line = ser.readline()
                if debug and line:
                    try:
                        print(f"DEBUG RAW: {line}")
                    except:
                        print(f"DEBUG RAW: {line} (decode fail)")

                if line:
                    parse_nmea(line)
                elif debug:
                     # Only print timeout in debug mode to avoid spamming
                     sys.stdout.write(".") 
                     sys.stdout.flush()
    except serial.SerialException as e:
        print(f"[-] Serial error during monitoring: {e}")


def main():
    parser = argparse.ArgumentParser(description="GPS Assistance Script")
    parser.add_argument("--port", default=DEFAULT_SERIAL_PORT, help="Serial port (e.g., /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUDRATE, help="Baud rate")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="A-GPS Service Token")
    parser.add_argument("--ephemeris-file", default="ephemeris_data.ubx", help="Path to local ephemeris file")
    parser.add_argument("--monitor-only", action="store_true", help="Skip A-GPS steps and only monitor NMEA status (Useful for non-u-blox devices like GT-730F)")
    parser.add_argument("--debug", action="store_true", help="Show raw serial data (helpful for debugging)")
    
    args = parser.parse_args()
    
    if args.monitor_only:
        print("[*] Monitor-only mode enabled. Skipping internet check and A-GPS injection.")
    else:
        # 1. Check Internet
        has_internet = check_internet()
        
        # 2. Download Ephemeris (if internet available)
        downloaded_file = None
        if has_internet:
            downloaded_file = download_ephemeris(args.token, args.ephemeris_file)
        else:
            print("[!] Skipping download due to no internet.")
            # Check if we have a local file to use anyway
            if os.path.exists(args.ephemeris_file):
                print(f"[+] Found local file '{args.ephemeris_file}', using that instead.")
                downloaded_file = args.ephemeris_file
            else:
                print("[-] No local ephemeris file found.")

        # 3. Upload Ephemeris (if we have a file)
        if downloaded_file:
             upload_ephemeris(args.port, args.baud, downloaded_file)
        else:
            print("[!] No ephemeris data to upload.")
        
    # 4. Monitor Status
    monitor_status(args.port, args.baud, debug=args.debug)

if __name__ == "__main__":
    main()
