import serial
import time
import sys

# 使用方法: python test_esp32_serial.py /dev/ttyUSB0 115200

def main():
    if len(sys.argv) < 2:
        print("用法: python test_esp32_serial.py <serial_port> [baudrate]")
        sys.exit(1)
    port = sys.argv[1]
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        print(f"已連接到 {port}，baudrate={baudrate}")
        print("按 Ctrl+C 結束...")
        while True:
            line = ser.readline()
            if line:
                print(f"收到: {line.decode(errors='replace').strip()}")
            time.sleep(0.05)
    except Exception as e:
        print(f"連接失敗: {e}")

if __name__ == "__main__":
    main()
