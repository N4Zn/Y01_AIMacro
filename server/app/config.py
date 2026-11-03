"""Cấu hình server. Mọi giá trị nhạy cảm đọc từ biến môi trường, có mặc định CHỈ để chạy thử cục bộ.

Khi triển khai thật: đặt EDUXPLORE_SECRET_KEY (ký JWT + cookie admin) và EDUXPLORE_ADMIN_PASSWORD
qua biến môi trường, không dùng giá trị mặc định bên dưới.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # .../server
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "app.db"

SECRET_KEY = os.environ.get("EDUXPLORE_SECRET_KEY", "DEV-ONLY-KHONG-DUNG-THAT-" + "x" * 32)
ADMIN_PASSWORD = os.environ.get("EDUXPLORE_ADMIN_PASSWORD", "admin123")

ACCESS_TOKEN_MINUTES = 30
REFRESH_TOKEN_DAYS = 180
HEARTBEAT_TIMEOUT_SEC = 90          # không nhịp tim quá mốc này -> coi phiên đã chết, tự giải phóng

# free/pro quyết định hạng mục nào tool cho chạy (gui_app.py lọc theo entitlements khi đăng nhập).
# Phải khớp các cid trong engine.CATEGORIES — thêm category mới ở đó thì nhớ thêm cả ở đây.
ENTITLEMENTS = {
    "free": ["mainmenu", "shop"],
    "pro": ["mainmenu", "shop", "marble", "jackpot", "cloud_garden"],
}
