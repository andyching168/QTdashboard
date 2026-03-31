#!/bin/bash

# ========================================
# CANable v2 韌體刷寫腳本
# 支援 slcan 和 candleLight (socketcan) 韌體
# ========================================

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 韌體下載 URL（官方最新版本）
# CANable v2 韌體
CANABLE2_SLCAN_URL="https://canable.io/builds/canable2/slcan/canable2-b158aa7.bin"
CANABLE2_CANDLELIGHT_URL="https://canable.io/builds/canable2/candlelight/canable2_fw-ba6b1dd.bin"

# CANable v1 韌體（原版）
CANABLE1_SLCAN_URL="https://canable.io/builds/slcan-firmware/canable-0e2e916.bin"
CANABLE1_CANDLELIGHT_URL="https://canable.io/builds/candlelight-firmware/gsusb_canable_68df7d5.bin"

# 韌體儲存目錄
FIRMWARE_DIR="$HOME/.canable_firmware"

# DFU 參數
DFU_VID_PID="0483:df11"
DFU_ALT="0"
DFU_ADDRESS="0x08000000"

# ========================================
# 函數定義
# ========================================

print_banner() {
    echo -e "${CYAN}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║           CANable v2 韌體刷寫工具                          ║"
    echo "║           支援 slcan / candleLight (socketcan)             ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 檢查必要工具
check_dependencies() {
    print_info "檢查必要工具..."
    
    local missing_deps=()
    
    # 檢查 dfu-util
    if ! command -v dfu-util &> /dev/null; then
        missing_deps+=("dfu-util")
    fi
    
    # 檢查 curl 或 wget
    if ! command -v curl &> /dev/null && ! command -v wget &> /dev/null; then
        missing_deps+=("curl 或 wget")
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "缺少必要工具: ${missing_deps[*]}"
        echo ""
        echo "請安裝缺少的工具:"
        echo ""
        
        if [[ "$OSTYPE" == "darwin"* ]]; then
            echo "  macOS (使用 Homebrew):"
            echo "    brew install dfu-util"
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            echo "  Ubuntu/Debian:"
            echo "    sudo apt-get install dfu-util curl"
            echo ""
            echo "  Fedora/RHEL:"
            echo "    sudo dnf install dfu-util curl"
            echo ""
            echo "  Arch Linux:"
            echo "    sudo pacman -S dfu-util curl"
        fi
        exit 1
    fi
    
    print_success "所有必要工具已安裝"
}

# 建立韌體目錄
create_firmware_dir() {
    if [ ! -d "$FIRMWARE_DIR" ]; then
        mkdir -p "$FIRMWARE_DIR"
        print_info "建立韌體目錄: $FIRMWARE_DIR"
    fi
}

# 下載韌體
download_firmware() {
    local url=$1
    local filename=$2
    local filepath="$FIRMWARE_DIR/$filename"
    
    if [ -f "$filepath" ]; then
        print_info "韌體已存在: $filename"
        read -p "是否重新下載? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 0
        fi
    fi
    
    print_info "下載韌體: $filename"
    
    if command -v curl &> /dev/null; then
        # 加入 -k 跳過 SSL 憑證驗證
        curl -k -L -o "$filepath" "$url" --progress-bar
    else
        # wget 使用 --no-check-certificate
        wget --no-check-certificate -O "$filepath" "$url"
    fi
    
    if [ -f "$filepath" ]; then
        local size=$(ls -lh "$filepath" | awk '{print $5}')
        print_success "下載完成: $filename ($size)"
    else
        print_error "下載失敗: $filename"
        exit 1
    fi
}

# 下載所有韌體
download_all_firmware() {
    print_info "下載所有韌體..."
    echo ""
    
    # CANable v2
    download_firmware "$CANABLE2_SLCAN_URL" "canable2-slcan.bin"
    download_firmware "$CANABLE2_CANDLELIGHT_URL" "canable2-candlelight.bin"
    
    # CANable v1
    download_firmware "$CANABLE1_SLCAN_URL" "canable1-slcan.bin"
    download_firmware "$CANABLE1_CANDLELIGHT_URL" "canable1-candlelight.bin"
    
    echo ""
    print_success "所有韌體下載完成!"
}

# 檢測 DFU 裝置
detect_dfu_device() {
    print_info "偵測 DFU 裝置..."
    
    local dfu_devices=$(dfu-util -l 2>/dev/null | grep -i "0483:df11" || true)
    
    if [ -z "$dfu_devices" ]; then
        print_warning "未偵測到 DFU 裝置"
        echo ""
        echo -e "${YELLOW}請將 CANable 設定為 DFU 模式:${NC}"
        echo ""
        echo "  CANable v2:"
        echo "    1. 按住裝置上的按鈕"
        echo "    2. 同時插入 USB"
        echo "    3. 放開按鈕"
        echo ""
        echo "  CANable v1 / Pro:"
        echo "    1. 將 BOOT jumper 移至 Boot 位置"
        echo "    2. 插入 USB"
        echo ""
        return 1
    fi
    
    print_success "偵測到 DFU 裝置:"
    echo "$dfu_devices"
    return 0
}

# 刷寫韌體
flash_firmware() {
    local firmware_path=$1
    local firmware_name=$(basename "$firmware_path")
    
    if [ ! -f "$firmware_path" ]; then
        print_error "韌體檔案不存在: $firmware_path"
        exit 1
    fi
    
    print_info "準備刷寫韌體: $firmware_name"
    
    # 確認 DFU 裝置
    if ! detect_dfu_device; then
        read -p "按 Enter 重新偵測，或 Ctrl+C 取消..." 
        if ! detect_dfu_device; then
            print_error "仍未偵測到 DFU 裝置，請檢查連接"
            exit 1
        fi
    fi
    
    echo ""
    print_warning "即將刷寫韌體，此操作會覆蓋現有韌體!"
    read -p "確定要繼續嗎? (y/N): " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "取消刷寫"
        exit 0
    fi
    
    print_info "開始刷寫..."
    
    # 執行 dfu-util
    if sudo dfu-util -d "$DFU_VID_PID" -c 1 -i 0 -a "$DFU_ALT" -s "$DFU_ADDRESS" -D "$firmware_path"; then
        echo ""
        print_success "韌體刷寫成功!"
        echo ""
        echo -e "${GREEN}接下來請:${NC}"
        echo "  1. 拔掉 USB"
        echo "  2. 將 BOOT jumper 移回原位 (CANable v1/Pro)"
        echo "  3. 重新插入 USB"
        echo ""
        
        if [[ "$firmware_name" == *"candlelight"* ]]; then
            echo -e "${CYAN}candleLight 韌體使用方式:${NC}"
            echo "  # 設定 CAN 介面"
            echo "  sudo ip link set can0 up type can bitrate 500000"
            echo ""
            echo "  # 檢視 CAN 流量"
            echo "  candump can0"
        else
            echo -e "${CYAN}slcan 韌體使用方式:${NC}"
            echo "  # 建立 CAN 介面"
            echo "  sudo slcand -o -c -s6 /dev/ttyACM0 can0"
            echo "  sudo ifconfig can0 up"
            echo ""
            echo "  # 檢視 CAN 流量"
            echo "  candump can0"
        fi
    else
        print_error "韌體刷寫失敗!"
        exit 1
    fi
}

# 列出可用韌體
list_firmware() {
    echo ""
    echo -e "${CYAN}可用韌體:${NC}"
    echo ""
    
    if [ -d "$FIRMWARE_DIR" ]; then
        local count=0
        for f in "$FIRMWARE_DIR"/*.bin; do
            if [ -f "$f" ]; then
                count=$((count + 1))
                local size=$(ls -lh "$f" | awk '{print $5}')
                local name=$(basename "$f")
                echo "  [$count] $name ($size)"
            fi
        done
        
        if [ $count -eq 0 ]; then
            print_warning "尚未下載任何韌體"
            echo "  請先執行: $0 download"
        fi
    else
        print_warning "韌體目錄不存在"
        echo "  請先執行: $0 download"
    fi
    echo ""
}

# 互動式刷寫
interactive_flash() {
    print_banner
    
    echo "請選擇 CANable 版本:"
    echo ""
    echo "  [1] CANable v2 (2.0)"
    echo "  [2] CANable v1 (原版/Pro)"
    echo ""
    read -p "請輸入選項 (1-2): " -n 1 -r version_choice
    echo ""
    
    echo ""
    echo "請選擇韌體類型:"
    echo ""
    echo "  [1] slcan (串列介面，跨平台)"
    echo "      - 使用虛擬串列埠通訊"
    echo "      - 需要 slcand 建立 SocketCAN 介面"
    echo "      - 支援 Windows/Mac/Linux"
    echo ""
    echo "  [2] candleLight (原生 SocketCAN)"
    echo "      - Linux 原生 CAN 裝置"
    echo "      - 無需 slcand，效能更好"
    echo "      - 僅支援 Linux"
    echo ""
    read -p "請輸入選項 (1-2): " -n 1 -r firmware_choice
    echo ""
    
    local firmware_file=""
    
    case "$version_choice" in
        1)
            case "$firmware_choice" in
                1) firmware_file="canable2-slcan.bin" ;;
                2) firmware_file="canable2-candlelight.bin" ;;
                *) print_error "無效選項"; exit 1 ;;
            esac
            ;;
        2)
            case "$firmware_choice" in
                1) firmware_file="canable1-slcan.bin" ;;
                2) firmware_file="canable1-candlelight.bin" ;;
                *) print_error "無效選項"; exit 1 ;;
            esac
            ;;
        *)
            print_error "無效選項"
            exit 1
            ;;
    esac
    
    local firmware_path="$FIRMWARE_DIR/$firmware_file"
    
    if [ ! -f "$firmware_path" ]; then
        print_warning "韌體檔案不存在，正在下載..."
        
        case "$firmware_file" in
            "canable2-slcan.bin")
                download_firmware "$CANABLE2_SLCAN_URL" "$firmware_file"
                ;;
            "canable2-candlelight.bin")
                download_firmware "$CANABLE2_CANDLELIGHT_URL" "$firmware_file"
                ;;
            "canable1-slcan.bin")
                download_firmware "$CANABLE1_SLCAN_URL" "$firmware_file"
                ;;
            "canable1-candlelight.bin")
                download_firmware "$CANABLE1_CANDLELIGHT_URL" "$firmware_file"
                ;;
        esac
    fi
    
    flash_firmware "$firmware_path"
}

# 顯示使用說明
show_usage() {
    print_banner
    echo "使用方式:"
    echo ""
    echo "  $0 [命令]"
    echo ""
    echo "命令:"
    echo "  download    下載所有韌體到本地"
    echo "  flash       互動式刷寫韌體"
    echo "  list        列出已下載的韌體"
    echo "  detect      偵測 DFU 裝置"
    echo "  help        顯示此說明"
    echo ""
    echo "快速刷寫:"
    echo "  $0 flash-v2-slcan         刷寫 CANable v2 slcan 韌體"
    echo "  $0 flash-v2-candlelight   刷寫 CANable v2 candleLight 韌體"
    echo "  $0 flash-v1-slcan         刷寫 CANable v1 slcan 韌體"
    echo "  $0 flash-v1-candlelight   刷寫 CANable v1 candleLight 韌體"
    echo ""
    echo "範例:"
    echo "  $0 download               # 先下載韌體"
    echo "  $0 flash                  # 互動式刷寫"
    echo "  $0 flash-v2-candlelight   # 快速刷寫 v2 candleLight"
    echo ""
}

# ========================================
# 主程式
# ========================================

main() {
    check_dependencies
    create_firmware_dir
    
    case "${1:-}" in
        download)
            print_banner
            download_all_firmware
            ;;
        flash)
            interactive_flash
            ;;
        flash-v2-slcan)
            print_banner
            download_firmware "$CANABLE2_SLCAN_URL" "canable2-slcan.bin"
            flash_firmware "$FIRMWARE_DIR/canable2-slcan.bin"
            ;;
        flash-v2-candlelight)
            print_banner
            download_firmware "$CANABLE2_CANDLELIGHT_URL" "canable2-candlelight.bin"
            flash_firmware "$FIRMWARE_DIR/canable2-candlelight.bin"
            ;;
        flash-v1-slcan)
            print_banner
            download_firmware "$CANABLE1_SLCAN_URL" "canable1-slcan.bin"
            flash_firmware "$FIRMWARE_DIR/canable1-slcan.bin"
            ;;
        flash-v1-candlelight)
            print_banner
            download_firmware "$CANABLE1_CANDLELIGHT_URL" "canable1-candlelight.bin"
            flash_firmware "$FIRMWARE_DIR/canable1-candlelight.bin"
            ;;
        list)
            print_banner
            list_firmware
            ;;
        detect)
            print_banner
            detect_dfu_device
            ;;
        help|--help|-h)
            show_usage
            ;;
        "")
            show_usage
            ;;
        *)
            print_error "未知命令: $1"
            show_usage
            exit 1
            ;;
    esac
}

main "$@"
