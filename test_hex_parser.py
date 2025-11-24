import struct

def parse_luxgen_hex(hex_str):
    """
    解析 Luxgen M7 CAN ID 0x340 (832) 的原始 HEX 數據
    """
    # 移除空格並轉換為 bytes
    clean_hex = hex_str.replace(" ", "")
    try:
        data = bytes.fromhex(clean_hex)
    except ValueError:
        print(f"❌ 無效的 HEX 格式: {hex_str}")
        return

    if len(data) != 8:
        print(f"❌ 數據長度錯誤 (應為 8 bytes): {len(data)}")
        return

    # 定義檔位映射
    gear_map = {
        0x00: "P/N (停車/空檔)",
        0x01: "D (前進)",
        0x07: "R (倒車)"
    }

    # Byte 0: 變速箱模式
    trans_mode = data[0]
    gear_name = gear_map.get(trans_mode, f"Unknown ({trans_mode:#04x})")

    print(f"\n🔍 解析 HEX: {hex_str}")
    print(f"   ➡️  檔位模式: {gear_name}")

    # 核心 RPM 解析邏輯
    rpm = 0.0
    
    # 提取 Byte 2 和 Byte 3 作為基礎數值 (Big Endian)
    # 這是 P/N 檔的實際轉速，也是 D/R 檔的「怠速基底」
    base_val = (data[2] << 8) | data[3]
    
    if trans_mode == 0x00: # P or N Gear
        # P/N 檔位使用 Byte 6+7 * 2
        raw_val = (data[6] << 8) | data[7]
        rpm = float(raw_val * 2)
        print(f"   ➡️  解析邏輯: 標準模式 (Byte 6+7 * 2)")
        print(f"   ➡️  原始數值: {raw_val}")
        print(f"   ➡️  計算: {raw_val} * 2 = {rpm}")
        
    elif trans_mode in [0x01, 0x07]: # D or R Gear
        # D/R 檔位使用 Base + Delta 算法
        # Byte 7 是增量 (Delta)
        delta = data[7]
        
        # 根據觀察，係數約為 6
        rpm = base_val + (delta * 6.0)
        
        print(f"   ➡️  解析邏輯: 負載模式 (Base + Delta * 6)")
        print(f"   ➡️  基底轉速 (Byte 2+3): {base_val}")
        print(f"   ➡️  增量讀數 (Byte 7):   {delta}")
        print(f"   ➡️  增量計算: {delta} * 6 = {delta * 6}")
        
    else:
        print(f"   ⚠️  未知檔位模式，使用標準解析")
        rpm = float(base_val)

    print(f"   ✅  最終 RPM: {rpm:.1f}")
    print("-" * 40)

if __name__ == "__main__":
    print("=== Luxgen M7 RPM Hex Parser Test ===\n")

    # 使用者提供的新數據 (2025-11-24)
    test_cases = [
        ("P (停車)", "00 80 02 FF 61 00 01 90"),
        ("R (倒車)", "07 87 02 FF 61 00 E0 00"),
        ("N (空檔)", "00 84 02 FF 61 00 01 8D"),
        ("D (前進)", "01 85 02 FF 61 00 20 00"),
    ]

    for label, hex_str in test_cases:
        print(f"--- 測試: {label} ---")
        parse_luxgen_hex(hex_str)
        print("\n")

    # 讓使用者輸入
    while True:
        user_input = input("\n請輸入 HEX 字串 (輸入 q 離開): ")
        if user_input.lower() == 'q':
            break
        parse_luxgen_hex(user_input)
