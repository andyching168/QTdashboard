import os
import pty
import time
import math
import datetime

def checksum(sentence):
    """Calculate NMEA 0183 checksum (XOR of all bytes between $ and *)"""
    calc_cksum = 0
    for char in sentence:
        calc_cksum ^= ord(char)
    return "{:02X}".format(calc_cksum)

def format_nmea(msg_type, *args):
    """Format an NMEA sentence with checksum"""
    content = ",".join(map(str, args))
    csum = checksum(msg_type + "," + content)
    return f"${msg_type},{content}*{csum}\r\n"

def main():
    # Create pseudo-terminal
    master, slave = pty.openpty()
    s_name = os.ttyname(slave)
    
    print("="*60)
    print(f"VIRTUAL GPS SIMULATOR")
    print(f"Port Created: {s_name}")
    print("="*60)
    print("Instructions:")
    print("1. Keep this script running.")
    print("2. In a separate terminal/tab, update your Dashboard or test script")
    print(f"   to connect to: {s_name}")
    print("="*60)
    
    # Simulation State
    speed_kmh = 0.0
    lat = 25.0330
    lon = 121.5654
    phase = "SEARCHING" # SEARCHING, FIXED_STOP, ACCEL, DECEL
    start_time = time.time()
    
    try:
        while True:
            now = datetime.datetime.now(datetime.timezone.utc)
            time_str = now.strftime("%H%M%S.%f")[:-3]
            date_str = now.strftime("%d%m%y")
            
            # Scenario Logic
            elapsed = time.time() - start_time
            
            if elapsed < 10:
                phase = "FIXED_STOP"
                is_fixed = True
                speed_kmh = 0
            elif elapsed < 40:
                phase = "ACCEL"
                is_fixed = True
                # Accel from 0 to 100 km/h over 20s
                progress = (elapsed - 20) / 20.0
                speed_kmh = progress * 100.0
            elif elapsed < 60:
                phase = "DECEL"
                is_fixed = True
                # Decel from 100 to 0 km/h over 20s
                progress = (elapsed - 40) / 20.0
                speed_kmh = 100.0 * (1.0 - progress)
            else:
                # Loop back to stop
                start_time = time.time() - 10 # Go back to FIXED_STOP
                continue
                
            # Convert Speed to Knots (1 km/h = 0.539957 knots)
            speed_knots = speed_kmh * 0.539957
            
            # Info print
            print(f"\r[{phase}] Speed: {speed_kmh:.1f} km/h | Fix: {is_fixed}", end="", flush=True)

            # --- Generate NMEA Sentences ---
            
            # 1. GNRMC (Recommended Minimum)
            # $GNRMC,time,status,lat,NS,lon,EW,spd,cog,date,mv,mvEW,mode*cs
            status_char = 'A' if is_fixed else 'V'
            # Fake movement of coords
            if speed_kmh > 0:
                lat += 0.00001
            
            lat_str = f"{int(lat)*100 + (lat % 1)*60:.4f}"
            lon_str = f"{int(lon)*100 + (lon % 1)*60:.4f}"
            
            msg_rmc = format_nmea("GNRMC", time_str, status_char, lat_str, "N", lon_str, "E", f"{speed_knots:.2f}", "0.0", date_str, "", "", "A")
            os.write(master, msg_rmc.encode('ascii'))
            
            # 2. GPGGA (Fix Data)
            # $GPGGA,time,lat,NS,lon,EW,quality,numSV,HDOP,alt,M,sep,M,dGPS_age,dGPS_ref*cs
            qual = '1' if is_fixed else '0' # 1=GPS Fix
            msg_gga = format_nmea("GPGGA", time_str, lat_str, "N", lon_str, "E", qual, "08", "1.0", "10.0", "M", "0.0", "M", "", "")
            os.write(master, msg_gga.encode('ascii'))

            time.sleep(1.0) # 1Hz update rate
            
    except KeyboardInterrupt:
        print("\n\nVirtual GPS Stopped.")
    except Exception as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    main()
