#!/bin/bash
#============================================
# USB 控制器健康檢查 + 重置腳本
#
# 適用：Raspberry Pi 4 (VL805 USB 3.0 控制器)
#
# 檢測方式：列舉 USB device count，與歷史 baseline 比對
#           若明顯少於預期，視為 USB 掛了，執行 unbind/bind 重置
#
# 用法：
#   sudo bash reset_usb.sh           # 檢測並自動重置
#   sudo bash reset_usb.sh --force   # 強制重置（不檢測）
#   sudo bash reset_usb.sh --check   # 只檢測不回應
#   sudo bash reset_usb.sh --dry-run # 測試模式（只顯示會做什麼）
#
# 由 systemd reset-usb.timer 定期執行（每 5 分鐘）
#============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/var/log/reset_usb.log"
STATE_DIR="/var/lib/reset_usb"
# 預期最少 USB 數量：觸控螢幕 + CAN 轉接器 + GPS
MIN_USB_EXPECTED="${MIN_USB_EXPECTED:-3}"
# 容忍度：最多容忍比預期少 1 個（即低於 2 就警示，低於等於 1 才重置）
TOLERANCE=1

MODE="${1:-auto}"  # auto | force | check | dry-run

#------------------
#  日誌工具
#------------------
log() {
    local level="$1"
    shift
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $*"
    echo "$msg"
    if [ -w "$(dirname "$LOG_FILE")" ] 2>/dev/null; then
        echo "$msg" >> "$LOG_FILE"
    fi
}

#------------------
#  檢查是否需要以 root 執行
#------------------
check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo "❌ 此腳本需要 root 權限"
        echo "   請用: sudo bash $0"
        exit 1
    fi
}

#------------------
#  偵測 USB 控制器 PCI 路徑（自動適配）
#------------------
detect_usb_host() {
    # === 主要候選路徑 ===
    # RPi 4: VL805 USB 3.0 控制器，PCIe 路徑固定是 0000:01:00.0
    if [ -d "/sys/bus/pci/drivers/xhci_hcd/0000:01:00.0" ]; then
        echo "0000:01:00.0"
        return 0
    fi

    # RPi 4 可能落在不同的 PCIe bus number，列舉所有已 bind 的 xhci_hcd
    for pci_path in /sys/bus/pci/drivers/xhci_hcd/*; do
        if [ -d "$pci_path" ]; then
            local path
            path=$(basename "$pci_path")
            # 確認是 USB 控制器（class 應該是 0c0330 = USB xHCI）
            if [ -f "$pci_path/class" ]; then
                local class_id
                class_id=$(cat "$pci_path/class" 2>/dev/null | cut -c1-6)
                if [ "$class_id" = "0c0330" ]; then
                    echo "Found xhci_hcd at $path (class=0c0330)"
                    echo "$path"
                    return 0
                fi
            fi
        fi
    done

    echo "ERROR: 無法找到 USB xhci_hcd 控制器" >&2
    return 1
}

#------------------
#  取得目前 USB device 數量
#------------------
count_usb_devices() {
    # lsusb 輸出行數 = USB 設備數
    if command -v lsusb &>/dev/null; then
        lsusb 2>/dev/null | wc -l
    else
        # 沒有 lsusb，就用 sysfs 枚舉
        find /sys/bus/usb/devices -name "idVendor" -maxdepth 2 2>/dev/null | wc -l
    fi
}

#------------------
#  讀取或建立 Baseline
#------------------
load_baseline() {
    mkdir -p "$STATE_DIR"
    if [ -f "$STATE_DIR/baseline" ]; then
        cat "$STATE_DIR/baseline"
    else
        # 第一次，建立 baseline
        local count
        count=$(count_usb_devices)
        echo "$count" > "$STATE_DIR/baseline"
        log "INFO" "建立 USB Baseline: $count 設備"
        echo "$count"
    fi
}

#------------------
#  更新 Baseline
#------------------
update_baseline() {
    mkdir -p "$STATE_DIR"
    local count
    count=$(count_usb_devices)
    echo "$count" > "$STATE_DIR/baseline"
    log "INFO" "更新 USB Baseline: $count 設備"
}

#------------------
#  重置 USB 控制器（核心）
#------------------
do_reset() {
    local host_path="$1"
    local sys_path="/sys/bus/pci/drivers/xhci_hcd/${host_path}"

    if ! [ -d "$sys_path" ]; then
        log "ERROR" "USB 控制器路徑不存在: $sys_path"
        return 1
    fi

    log "WARN" "=========================================="
    log "WARN" "USB 控制器異常！開始重置..."
    log "WARN" "=========================================="

    # 記錄重置前的 USB 狀態
    if command -v lsusb &>/dev/null; then
        mkdir -p "$STATE_DIR"
        lsusb > "$STATE_DIR/lsusb_before_$(date +%Y%m%d_%H%M%S).log" 2>/dev/null || true
    fi

    # === 主要方法：unbind + bind xhci_hcd（RPi4 VL805 專用）===
    # 這會觸發 Linux 重新枚舉 USB 埠，相當於「軟體插拔」USB 控制器
    log "INFO" "執行: unbind $host_path"
    echo "$host_path" > /sys/bus/pci/drivers/xhci_hcd/unbind 2>&1
    sleep 2

    log "INFO" "執行: bind $host_path"
    echo "$host_path" > /sys/bus/pci/drivers/xhci_hcd/bind 2>&1
    sleep 3

    # 驗證
    local new_count
    new_count=$(count_usb_devices)
    log "INFO" "重置後 USB 設備數: $new_count"

    if [ "$new_count" -gt 0 ]; then
        log "INFO" "✅ USB 控制器 unbind/bind 成功"
        update_baseline
        return 0
    fi

    # === 備援：如果 unbind/bind 不夠（罕見），重載 VL805 Firmware ===
    # 某些情況下 VL805 晶片需要重新灌 firmware 才能恢復
    log "WARN" "⚠️  unbind/bind 未完全恢復，嘗試重載 VL805 firmware..."
    if command -v systemctl &>/dev/null; then
        # 觸發 rpi-eeprom-update 服務重新載入 VL805 firmware
        log "INFO" "呼叫 systemctl start rpi-eeprom-update..."
        systemctl start rpi-eeprom-update 2>&1 || true
        sleep 5
        new_count=$(count_usb_devices)
        if [ "$new_count" -gt 0 ]; then
            log "INFO" "✅ VL805 firmware 重載成功"
            update_baseline
            return 0
        fi
    fi

    log "ERROR" "❌ USB 控制器重置後仍無設備！可能需要整機重開機才能完全恢復"
    return 2
}

#------------------
#  主邏輯
#------------------
main() {
    check_root

    # 嘗試建立日誌目錄
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true

    # 自動偵測 USB 控制器路徑
    local host_path
    host_path=$(detect_usb_host) || {
        log "ERROR" "找不到 USB 控制器，退出"
        exit 1
    }
    log "INFO" "USB 控制器: $host_path"

    # --dry-run: 只顯示會做什麼
    if [ "$MODE" = "--dry-run" ] || [ "$MODE" = "dry-run" ]; then
        echo "🔍 [Dry-run 模式] 以下是會執行的動作："
        echo ""
        echo "  1. 偵測 USB 控制器: $host_path"
        echo "  2. 取得目前 USB 設備數..."
        echo "  3. 載入 Baseline..."
        echo "  4. 若低於閾值:"
        echo "       echo '$host_path' > /sys/bus/pci/drivers/xhci_hcd/unbind"
        echo "       sleep 2"
        echo "       echo '$host_path' > /sys/bus/pci/drivers/xhci_hcd/bind"
        echo "       sleep 3"
        echo "       更新 Baseline"
        echo ""
        echo "  USB 控制器路徑: $host_path"
        echo "  目前設備數: $(count_usb_devices)"
        echo "  Baseline:     $(load_baseline)"
        echo "  預期最少:     $MIN_USB_EXPECTED"
        exit 0
    fi

    # --force: 強制重置
    if [ "$MODE" = "--force" ]; then
        log "INFO" "模式: 強制重置 USB"
        do_reset "$host_path"
        exit $?
    fi

    # --check: 只檢測不回應
    if [ "$MODE" = "--check" ]; then
        local count baseline
        count=$(count_usb_devices)
        baseline=$(load_baseline)
        echo "USB 設備數: $count"
        echo "Baseline:   $baseline"
        echo "預期最少:   $MIN_USB_EXPECTED"
        if [ "$count" -lt "$MIN_USB_EXPECTED" ] || [ "$count" -lt "$(( baseline / 2 ))" ]; then
            echo "⚠️  USB 設備數明顯低於預期"
            exit 2
        fi
        echo "✅ USB 正常"
        exit 0
    fi

    # --auto: 自動檢測 + 重置（預設）
    local current_count baseline

    current_count=$(count_usb_devices)
    baseline=$(load_baseline)
    log "INFO" "USB 設備檢測: 目前=$current_count, Baseline=$baseline, 預期最少=$MIN_USB_EXPECTED"

    # 重置條件（滿足任一即重置）：
    # 1. 目前數量 <= 1（只剩 1 個或 0 個，幾乎全部設備掛掉）
    # 2. 比 baseline 少超過容忍數量（正常波動不會觸發）
    if [ "$current_count" -le 1 ] || \
       [ "$current_count" -lt "$(( baseline - TOLERANCE ))" ]; then
        log "WARN" "USB 異常: 設備數 $current_count，預期 $MIN_USB_EXPECTED，Baseline $baseline（容忍度 $TOLERANCE）"
        do_reset "$host_path"
        exit $?
    else
        log "INFO" "✅ USB 正常 ($current_count 設備)"
        # 更新 baseline（慢慢適應正常波動）
        if [ "$current_count" -gt "$baseline" ]; then
            update_baseline
        fi
        exit 0
    fi
}

main
