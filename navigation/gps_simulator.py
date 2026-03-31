#!/usr/bin/env python3
"""
Lightweight NMEA GPS simulator for Linux dev boxes without hardware.
- Opens a pseudo-tty under /dev/pts/* and streams GNRMC/GPGGA sentences.
- Default: 1 Hz updates, valid fix, 50 km/h constant speed.
- Optional sine wave speed profile for basic movement testing.
- --inject-obd: Also simulate OBD speed via datagrab for calibration testing.
"""
import argparse
import datetime
import math
import os
import pty
import sys
import time


def checksum(sentence: str) -> str:
    """Return NMEA 0183 checksum for the payload."""
    value = 0
    for ch in sentence:
        value ^= ord(ch)
    return f"{value:02X}"


def nmea(msg_type: str, *fields: str) -> str:
    payload = f"{msg_type},{','.join(fields)}"
    return f"${payload}*{checksum(payload)}\r\n"


def format_lat_lon(lat: float, lon: float) -> tuple[str, str, str, str]:
    """Convert decimal degrees to NMEA ddmm.mmmm and hemisphere flags."""
    lat_deg = int(abs(lat))
    lat_min = (abs(lat) - lat_deg) * 60
    lat_str = f"{lat_deg:02d}{lat_min:06.3f}".zfill(9)
    lon_deg = int(abs(lon))
    lon_min = (abs(lon) - lon_deg) * 60
    lon_str = f"{lon_deg:03d}{lon_min:06.3f}".zfill(10)
    return lat_str, ("N" if lat >= 0 else "S"), lon_str, ("E" if lon >= 0 else "W")


def speed_profile(mode: str, base_speed: float, t: float) -> float:
    if mode == "sine":
        return max(0.0, base_speed * (0.5 + 0.5 * math.sin(2 * math.pi * t / 30.0)))
    return max(0.0, base_speed)


def main() -> int:
    parser = argparse.ArgumentParser(description="NMEA GPS simulator (pseudo-tty)")
    parser.add_argument("--speed", type=float, default=50.0, help="Base speed in km/h (default: 50)")
    parser.add_argument("--mode", choices=["fixed", "sine"], default="fixed", help="Speed profile: fixed or sine")
    parser.add_argument("--hz", type=float, default=1.0, help="Update rate in Hz (default: 1)")
    parser.add_argument("--lat", type=float, default=25.0330, help="Starting latitude (default: Taipei 25.0330)")
    parser.add_argument("--lon", type=float, default=121.5654, help="Starting longitude (default: 121.5654)")
    parser.add_argument("--no-fix", action="store_true", help="Send invalid fix (Quality=0 / Status=V)")
    parser.add_argument("--inject-obd", action="store_true", help="Also inject OBD speed into datagrab for calibration testing")
    parser.add_argument("--obd-offset", type=float, default=3.0, help="OBD speed = GPS speed + offset (default: +3 km/h, simulates speedometer over-read)")
    args = parser.parse_args()

    # Optional: inject fake OBD speed into datagrab
    datagrab_module = None
    if args.inject_obd:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import datagrab
            datagrab_module = datagrab
            print(f"[OBD injection enabled] OBD speed = GPS speed + {args.obd_offset} km/h")
        except ImportError:
            print("[Warning] datagrab module not found, --inject-obd ignored")
            datagrab_module = None

    master, slave = pty.openpty()
    port_path = os.ttyname(slave)

    print("=" * 60)
    print("GPS SIMULATOR (NMEA -> pseudo-tty)")
    print(f"Port: {port_path}")
    print("Usage: point your app to this serial port (baud 38400). Keep this running.")
    print("Ctrl+C to stop.")
    print("=" * 60)

    lat = args.lat
    lon = args.lon
    start = time.time()
    interval = 1.0 / max(args.hz, 0.1)

    try:
        while True:
            now = datetime.datetime.now(datetime.timezone.utc)
            t = time.time() - start
            speed_kmh = speed_profile(args.mode, args.speed, t)
            speed_knots = speed_kmh * 0.539957

            if speed_kmh > 0:
                lat += 0.00001  # Tiny drift to show movement

            lat_str, lat_ns, lon_str, lon_ew = format_lat_lon(lat, lon)
            time_str = now.strftime("%H%M%S.%f")[:-3]
            date_str = now.strftime("%d%m%y")

            status = "V" if args.no_fix else "A"
            quality = "0" if args.no_fix else "1"

            rmc = nmea(
                "GNRMC",
                time_str,
                status,
                lat_str,
                lat_ns,
                lon_str,
                lon_ew,
                f"{speed_knots:.2f}",
                "0.0",
                date_str,
                "",
                "",
                "A",
            )

            gga = nmea(
                "GPGGA",
                time_str,
                lat_str,
                lat_ns,
                lon_str,
                lon_ew,
                quality,
                "08",
                "1.0",
                "10.0",
                "M",
                "0.0",
                "M",
                "",
                "",
            )

            os.write(master, rmc.encode("ascii"))
            os.write(master, gga.encode("ascii"))

            # Optionally inject OBD speed
            if datagrab_module is not None:
                obd_speed = speed_kmh + args.obd_offset
                datagrab_module.data_store["OBD"]["speed"] = obd_speed
                datagrab_module.data_store["OBD"]["speed_smoothed"] = obd_speed
                datagrab_module.data_store["OBD"]["last_update"] = time.time()

            fix_str = 'NO' if args.no_fix else 'YES'
            obd_str = f" | OBD={speed_kmh + args.obd_offset:.1f}" if datagrab_module else ""
            print(f"\rSpeed={speed_kmh:5.1f} km/h | Fix={fix_str}{obd_str} | Port={port_path}", end="", flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    except Exception as exc:  # pragma: no cover
        print(f"\nError: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
