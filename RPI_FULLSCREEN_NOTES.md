# Raspberry Pi 全螢幕模式授權視窗測試

## 問題說明

在 Raspberry Pi 的全螢幕模式下，彈出新視窗可能會遇到以下問題：

1. **視窗被主視窗遮蓋**：新視窗可能顯示在全螢幕視窗背後
2. **無法切換視窗**：觸控螢幕環境下難以切換到授權視窗
3. **窗口管理器行為不一致**：不同的桌面環境（X11/Wayland）行為可能不同

## 解決方案

### 方案 A：模態對話框 + 置頂（已實作）

```python
# 在 main.py 的 start_spotify_auth() 中
self.auth_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
self.auth_dialog.setWindowFlags(
    Qt.WindowType.Dialog | 
    Qt.WindowType.WindowStaysOnTopHint |
    Qt.WindowType.FramelessWindowHint
)
```

**優點：**
- ✅ 強制置於最前方
- ✅ 阻止與主視窗互動，引導用戶完成授權
- ✅ 無邊框設計更適合觸控螢幕
- ✅ 自動置中顯示

**缺點：**
- ⚠️ 仍是獨立視窗，某些窗口管理器可能有問題

### 方案 B：內嵌覆蓋層（備選方案）

如果方案 A 在 RPi 上有問題，可以實作覆蓋層方案：

```python
# 在 Dashboard 中添加一個全螢幕覆蓋層
# QR Code 直接顯示在主視窗上方
# 類似 iOS/Android 的全螢幕對話框
```

**優點：**
- ✅ 完全避免視窗管理問題
- ✅ 更符合觸控裝置的 UX 模式
- ✅ 可以添加半透明背景遮罩

**缺點：**
- ⚠️ 需要重構程式碼
- ⚠️ 實作較複雜

## 測試步驟

### 1. 桌面環境測試

```bash
# 正常視窗模式
python main.py
```

**預期結果：**
- QR Code 視窗應該置於主視窗前方
- 無邊框但可以看到內容
- 可以點擊「取消」按鈕關閉

### 2. 全螢幕模式測試

```bash
# 方法 1：程式碼中設定全螢幕
# 在 main.py 的 if __name__ == '__main__': 中添加
dashboard.showFullScreen()

# 方法 2：使用視窗管理器
# F11 或 Alt+Enter 切換全螢幕
```

**預期結果：**
- 點擊「綁定 Spotify」後，QR Code 視窗應該顯示在全螢幕之上
- 視窗應該置中顯示
- 主視窗應該被遮罩（模態效果）
- 能正常使用 QR Code 授權

### 3. Raspberry Pi 測試

```bash
# SSH 到 Raspberry Pi
ssh pi@raspberrypi.local

# 啟動 X11 或確保在桌面環境
export DISPLAY=:0

# 測試全螢幕模式
python main.py
```

**測試重點：**
- [ ] QR Code 視窗能否正常顯示
- [ ] 視窗是否置於最前方
- [ ] 觸控操作是否正常
- [ ] 能否完成授權流程
- [ ] 授權完成後視窗能否正常關閉

## 可能遇到的問題

### 問題 1：視窗仍然被遮蓋

**解決方案：**
```python
# 在顯示視窗後強制激活
self.auth_dialog.show()
self.auth_dialog.raise_()
self.auth_dialog.activateWindow()
```

### 問題 2：Wayland 環境下 WindowStaysOnTopHint 無效

**檢查當前環境：**
```bash
echo $XDG_SESSION_TYPE  # 顯示 x11 或 wayland
```

**解決方案：**
```bash
# 強制使用 X11
export QT_QPA_PLATFORM=xcb
python main.py
```

### 問題 3：無邊框視窗無法移動

這是設計上的取捨，如果需要可移動：

**方案 A：添加拖動功能**
```python
# 在視窗中添加自訂標題欄，支援拖動
```

**方案 B：保留邊框**
```python
# 移除 FramelessWindowHint
self.auth_dialog.setWindowFlags(
    Qt.WindowType.Dialog | 
    Qt.WindowType.WindowStaysOnTopHint
)
```

## 建議測試環境

### 最低測試環境

1. **桌面 Linux + X11**：驗證基本功能
2. **Raspberry Pi 4 + X11 + 觸控螢幕**：最接近實際使用環境
3. **全螢幕模式**：模擬車載環境

### 完整測試環境

| 環境 | 視窗系統 | 測試重點 |
|------|---------|---------|
| Ubuntu Desktop | X11 | 基本功能 |
| Ubuntu Desktop | Wayland | Wayland 相容性 |
| Raspberry Pi OS | X11 | 效能 + 觸控 |
| 全螢幕模式 | 任意 | 視窗置頂 |

## 回退方案

如果模態對話框方案在 RPi 上有問題，可以快速切換到內嵌方案：

```python
# 建立一個簡單的測試來決定使用哪種方案
def test_modal_dialog():
    # 測試模態對話框是否正常工作
    # 如果不行，使用內嵌覆蓋層
    pass
```

## 推薦配置

```python
# 在 main.py 中
if platform.system() == 'Linux':
    # Linux (包括 RPi)
    if 'arm' in platform.machine().lower():
        # Raspberry Pi - 使用更保守的設定
        USE_MODAL_DIALOG = True
        USE_FRAMELESS = True
    else:
        # 桌面 Linux
        USE_MODAL_DIALOG = True
        USE_FRAMELESS = False  # 保留邊框方便開發
```

## 參考資料

- Qt Window Flags: https://doc.qt.io/qt-6/qt.html#WindowType-enum
- Qt Modal Dialogs: https://doc.qt.io/qt-6/qdialog.html#modal-dialogs
- Raspberry Pi Touch Display: https://www.raspberrypi.com/products/raspberry-pi-touch-display/
