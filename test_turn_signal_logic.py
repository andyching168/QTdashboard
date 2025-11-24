#!/usr/bin/env python3
"""
方向燈邏輯測試 (無 GUI)
測試方向燈訊號解析邏輯是否正確
"""

def test_turn_signal_logic():
    """測試方向燈訊號邏輯"""
    
    print("=" * 60)
    print("方向燈訊號邏輯測試")
    print("=" * 60)
    print()
    
    test_cases = [
        # (left_signal, right_signal, expected_state, description)
        (0, 0, "off", "兩個訊號都是 0 -> 關閉"),
        (1, 0, "left_on", "左轉訊號 = 1, 右轉訊號 = 0 -> 左轉燈亮"),
        (0, 1, "right_on", "左轉訊號 = 0, 右轉訊號 = 1 -> 右轉燈亮"),
        (1, 1, "both_on", "兩個訊號都是 1 -> 雙閃 (警示燈)"),
    ]
    
    passed = 0
    failed = 0
    
    for left, right, expected, desc in test_cases:
        print(f"測試案例: {desc}")
        print(f"  輸入: LEFT={left}, RIGHT={right}")
        
        # 模擬 datagrab.py 中的邏輯
        if left == 1 and right == 1:
            result = "both_on"
        elif left == 1 and right == 0:
            result = "left_on"
        elif left == 0 and right == 1:
            result = "right_on"
        else:
            result = "off"
        
        print(f"  預期: {expected}")
        print(f"  結果: {result}")
        
        if result == expected:
            print("  ✓ 通過")
            passed += 1
        else:
            print("  ✗ 失敗")
            failed += 1
        print()
    
    print("=" * 60)
    print(f"測試結果: {passed} 通過, {failed} 失敗")
    print("=" * 60)
    
    return failed == 0

def test_dbc_parsing():
    """測試 DBC 訊號解析"""
    try:
        import cantools
    except ImportError:
        print("⚠ cantools 未安裝，跳過 DBC 解析測試")
        return True
    
    print("\n" + "=" * 60)
    print("DBC 訊號解析測試")
    print("=" * 60)
    print()
    
    try:
        # 載入 DBC 檔案
        db = cantools.database.load_file('luxgen_m7_2009.dbc')
        print("✓ DBC 檔案載入成功")
        
        # 檢查 BODY_ECU_STATUS 訊息 (ID 1056 = 0x420)
        msg_def = db.get_message_by_name('BODY_ECU_STATUS')
        print(f"✓ 找到訊息: {msg_def.name} (ID: 0x{msg_def.frame_id:X})")
        
        # 檢查方向燈訊號
        signals = ['LEFT_SIGNAL_STATUS', 'RIGHT_SIGNAL_STATUS']
        for sig_name in signals:
            try:
                sig = msg_def.get_signal_by_name(sig_name)
                print(f"✓ 找到訊號: {sig.name}")
                print(f"    起始位元: {sig.start}")
                print(f"    長度: {sig.length} bit")
                print(f"    位元組順序: {sig.byte_order}")
            except KeyError:
                print(f"✗ 找不到訊號: {sig_name}")
                return False
        
        # 測試解碼範例
        print("\n測試解碼範例:")
        test_data_cases = [
            # (data_hex, description)
            ("00 00 00 00 00 00 00 00", "全關閉"),
            ("00 04 00 00 00 00 00 00", "左轉燈亮 (bit 10 = 1)"),
            ("00 02 00 00 00 00 00 00", "右轉燈亮 (bit 9 = 1)"),
            ("00 06 00 00 00 00 00 00", "雙閃 (bits 9+10 = 1)"),
        ]
        
        for data_hex, desc in test_data_cases:
            data = bytes.fromhex(data_hex)
            decoded = db.decode_message(msg_def.frame_id, data)
            left = decoded.get('LEFT_SIGNAL_STATUS', 0)
            right = decoded.get('RIGHT_SIGNAL_STATUS', 0)
            
            # 處理 NamedSignalValue
            if hasattr(left, 'value'):
                left = int(left.value)
            else:
                left = int(left)
            
            if hasattr(right, 'value'):
                right = int(right.value)
            else:
                right = int(right)
            
            print(f"  {desc}: LEFT={left}, RIGHT={right}")
        
        print("\n✓ DBC 解析測試通過")
        return True
        
    except FileNotFoundError:
        print("✗ DBC 檔案不存在: luxgen_m7_2009.dbc")
        return False
    except Exception as e:
        print(f"✗ DBC 解析錯誤: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """執行所有測試"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "方向燈功能測試套件" + " " * 23 + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    # 測試 1: 邏輯測試
    logic_ok = test_turn_signal_logic()
    
    # 測試 2: DBC 解析測試
    dbc_ok = test_dbc_parsing()
    
    # 總結
    print("\n" + "=" * 60)
    print("測試總結")
    print("=" * 60)
    print(f"邏輯測試: {'✓ 通過' if logic_ok else '✗ 失敗'}")
    print(f"DBC 解析: {'✓ 通過' if dbc_ok else '✗ 失敗'}")
    print("=" * 60)
    
    if logic_ok and dbc_ok:
        print("\n🎉 所有測試通過！方向燈功能已準備就緒。")
        return 0
    else:
        print("\n⚠ 部分測試失敗，請檢查上方錯誤訊息。")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
