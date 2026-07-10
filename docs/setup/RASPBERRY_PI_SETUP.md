# Raspberry Pi 部署指南

本指南說明如何在 Raspberry Pi 上部署儀表板系統，配合 USB 觸控螢幕使用。

## 硬體需求

- **Raspberry Pi**: Pi 4 (推薦) 或 Pi 3B+
- **螢幕**: 8.8 吋 USB 觸控螢幕 (1920x480 解析度)
- **CAN 轉接器** (可選): 用於連接實際車輛 CAN Bus
- **SD 卡**: 至少 16GB，推薦 32GB Class 10

## 軟體安裝

### 1. 更新系統

```bash
sudo apt update
sudo apt upgrade -y
```

### 2. 安裝 Python 3.11+

```bash
sudo apt install python3 python3-pip python3-venv -y
```

### 3. 安裝系統依賴

```bash
# PyQt6 所需
sudo apt install python3-pyqt6 python3-pyqt6.qtcore python3-pyqt6.qtgui python3-pyqt6.qtwidgets -y

# 或者安裝基礎依賴後用 pip 安裝
sudo apt install libgl1-mesa-glx libegl1-mesa libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 libxcb-xfixes0 -y
```

### 4. 安裝專案依賴

```bash
cd ~/
git clone <your-repo-url> QTdashboard
cd QTdashboard

# 創建虛擬環境
python3 -m venv venv
source venv/bin/activate

# 安裝依賴
pip install -r requirements.txt
```

## 觸控螢幕設定

### 1. 檢測觸控設備

```bash
xinput list
```

找到你的觸控螢幕設備名稱。

### 2. 校準觸控 (如需要)

```bash
sudo apt install xinput-calibrator -y
xinput_calibrator
```

按照螢幕上的指示進行校準。

### 3. 自動旋轉螢幕 (如需要)

編輯 `/boot/config.txt`：

```bash
sudo nano /boot/config.txt
```

添加（根據你的螢幕方向）：

```
# 旋轉螢幕 (0=0°, 1=90°, 2=180°, 3=270°)
display_rotate=0

# 8.8吋 1920x480 螢幕設定
hdmi_group=2
hdmi_mode=87
hdmi_cvt=1920 480 60 6 0 0 0
```

重啟：
```bash
sudo reboot
```

## 運行模式

### 演示模式 (無需硬體)

```bash
cd ~/QTdashboard
source venv/bin/activate
python demo_mode.py
```

### 連接實際 CAN Bus

```bash
# 1. 確認 CAN 介面
ls /dev/tty*

# 2. 運行主程式
python datagrab.py
```

## 自動啟動設定

### 方法 1: 使用 systemd

創建服務檔案：

```bash
sudo nano /etc/systemd/system/qtdashboard.service
```

內容：

```ini
[Unit]
Description=QT Dashboard
After=graphical.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/QTdashboard
Environment="DISPLAY=:0"
Environment="XAUTHORITY=/home/pi/.Xauthority"
ExecStart=/home/pi/QTdashboard/venv/bin/python /home/pi/QTdashboard/demo_mode.py
Restart=on-failure

[Install]
WantedBy=graphical.target
```

啟用服務：

```bash
sudo systemctl daemon-reload
sudo systemctl enable qtdashboard.service
sudo systemctl start qtdashboard.service
```

### 方法 2: 使用 autostart (LXDE/Openbox)

```bash
mkdir -p ~/.config/autostart
nano ~/.config/autostart/qtdashboard.desktop
```

內容：

```ini
[Desktop Entry]
Type=Application
Name=QT Dashboard
Exec=/home/pi/QTdashboard/venv/bin/python /home/pi/QTdashboard/demo_mode.py
Terminal=false
```

## 效能優化

### 1. 停用不需要的服務

```bash
sudo systemctl disable bluetooth.service
sudo systemctl disable cups.service
```

### 2. 超頻 (Raspberry Pi 4)

編輯 `/boot/config.txt`：

```bash
sudo nano /boot/config.txt
```

添加：

```
# 超頻設定 (謹慎使用，需要良好散熱)
over_voltage=6
arm_freq=2000
gpu_freq=600
```

### 3. 關閉桌面環境 (僅運行儀表板)

```bash
sudo systemctl set-default multi-user.target
```

然後設定在 tty1 自動登入並啟動 X：

編輯 `~/.bashrc`：

```bash
if [ -z "$DISPLAY" ] && [ $(tty) = /dev/tty1 ]; then
    startx
fi
```

## 觸控手勢

### 在 8.8 吋螢幕上使用

- **向左滑動**: 下一張卡片 (油量表 → 音樂播放器)
- **向右滑動**: 上一張卡片 (音樂播放器 → 油量表)
- **圓點指示器**: 底部顯示當前位置

### 手勢設定

調整滑動靈敏度（在 `main.py`）：

```python
self.swipe_threshold = 50  # 調整此值 (30-100)
```

- 數值越小，越容易觸發滑動
- 數值越大，需要更長的滑動距離

## 故障排除

### 觸控不靈敏

```bash
# 檢查觸控設備
xinput list

# 調整觸控靈敏度
xinput set-prop <device-id> "libinput Accel Speed" 0.5
```

### 畫面撕裂

在 `main.py` 中啟用 VSync：

```python
app.setAttribute(Qt.ApplicationAttribute.AA_UseDesktopOpenGL)
```

### 記憶體不足

```bash
# 增加 swap
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# 設定 CONF_SWAPSIZE=1024
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

## CAN Bus 設定 (連接實車)

### 使用 USB CAN 轉接器

```bash
# 載入驅動
sudo modprobe can
sudo modprobe can_raw
> 正式車機請使用 SocketCAN can0。以下 SLCAN 指令僅供舊韌體轉換或桌面除錯，
> Dashboard 在 Raspberry Pi/Linux 上不會自動掃描 serial port 作為 CAN。

sudo modprobe slcan

# 設定 CAN 介面 (假設使用 /dev/ttyUSB0)
sudo slcand -o -c -s6 /dev/ttyUSB0 slcan0
sudo ifconfig slcan0 up

# 測試
candump slcan0
```

### 開機自動設定

創建 `/etc/rc.local`：

```bash
#!/bin/bash
modprobe can
modprobe can_raw
modprobe slcan
slcand -o -c -s6 /dev/ttyUSB0 slcan0
ifconfig slcan0 up
exit 0
```

## 維護

### 查看日誌

```bash
# systemd 服務日誌
sudo journalctl -u qtdashboard.service -f

# 應用程式日誌
cat ~/QTdashboard/qtdashboard.log
```

### 更新程式

```bash
cd ~/QTdashboard
git pull
source venv/bin/activate
pip install -r requirements.txt --upgrade
sudo systemctl restart qtdashboard.service
```

## 建議配置

**Raspberry Pi 4 (4GB RAM) + 8.8" 觸控螢幕**
- CPU: 1.5GHz (標準) 或 2.0GHz (超頻)
- 解析度: 1920x480
- 幀率: 穩定 60 FPS
- 觸控延遲: < 50ms

完美的車用儀表板體驗！🚗💨
