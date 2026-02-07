"""
CLIMB GUI 主題設定
==================
配色、字型、間距常數。統一管理 UI 外觀。
"""

import platform

# ============================================================
# 字型
# ============================================================

_IS_WINDOWS = platform.system() == "Windows"

# Windows 優先使用微軟正黑體，macOS 用蘋方，Linux 用 Noto
if _IS_WINDOWS:
    FONT_FAMILY = "Microsoft JhengHei UI"
    FONT_MONO = "Consolas"
elif platform.system() == "Darwin":
    FONT_FAMILY = "PingFang TC"
    FONT_MONO = "Menlo"
else:
    FONT_FAMILY = "Noto Sans CJK TC"
    FONT_MONO = "Monospace"

FONT_NORMAL = (FONT_FAMILY, 13)
FONT_SMALL = (FONT_FAMILY, 11)
FONT_HEADING = (FONT_FAMILY, 15, "bold")
FONT_MONO_NORMAL = (FONT_MONO, 12)
FONT_MONO_SMALL = (FONT_MONO, 11)

# ============================================================
# 間距
# ============================================================

PAD_X = 12
PAD_Y = 8
PAD_SECTION = 16      # 區塊之間的間距
PAD_INNER = 6         # 區塊內部元素間距

# ============================================================
# 日誌顏色（用於 CTkTextbox tag）
# ============================================================

LOG_COLORS = {
    "DEBUG":    "#888888",   # 灰色
    "INFO":     "#DCE4EE",   # 淺白（深色主題）
    "WARNING":  "#F0A030",   # 橘色
    "ERROR":    "#FF4444",   # 紅色
    "CRITICAL": "#FF0000",   # 鮮紅
}

# ============================================================
# 狀態圖示
# ============================================================

STATUS_ICONS = {
    "success":  "✅",
    "failed":   "❌",
    "skipped":  "⏭️",
    "running":  "⏳",
    "pending":  "⬜",
    "cancelled": "🚫",
}

# ============================================================
# 平台徽章顏色
# ============================================================

PLATFORM_COLORS = {
    "PTT":      "#4A90D9",
    "Medium":   "#00AB6C",
    "Facebook": "#1877F2",
    "LINE":     "#00C300",
    "新聞":     "#E74C3C",
    "部落格":   "#9B59B6",
    "獸醫學會": "#F39C12",
    "其他":     "#95A5A6",
}

# ============================================================
# 視窗預設尺寸
# ============================================================

WINDOW_MIN_WIDTH = 900
WINDOW_MIN_HEIGHT = 650
WINDOW_DEFAULT_SIZE = "1050x720"
