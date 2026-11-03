# EduXplore Ad Helper — Server

Backend cho `gui_app.py` (chưa nối, xem TODO cuối file): đăng ký/đăng nhập, khoá 1-tài-khoản-game-1-máy-cùng-lúc,
log sử dụng, đồng bộ thư viện quảng cáo, kiểm tra bản mới. Thiết kế đầy đủ: `../SERVER_DESIGN.md`.

## Chạy thử cục bộ

```powershell
powershell -File run.ps1
```

Mở `http://127.0.0.1:8000/admin/login` (mật khẩu mặc định `admin123`, đổi bằng biến môi trường
`EDUXPLORE_ADMIN_PASSWORD` trước khi chạy). Tài liệu API tự sinh ở `http://127.0.0.1:8000/docs`.

Dữ liệu lưu ở `data/app.db` (SQLite, tự tạo, không commit — đã có trong `.gitignore`).

## Biến môi trường khi triển khai thật

| Biến | Việc | Mặc định (CHỈ để thử cục bộ) |
|---|---|---|
| `EDUXPLORE_SECRET_KEY` | Ký JWT + cookie admin | chuỗi cố định trong `config.py` — **phải đổi** |
| `EDUXPLORE_ADMIN_PASSWORD` | Mật khẩu trang `/admin` | `admin123` — **phải đổi** |

## Giao diện quản trị (`/admin`)

Tổng quan, Người dùng (đổi gói free/pro, khoá/mở khoá), Phiên đang chạy (xem + ngắt thủ công),
Nhật ký (200 sự kiện gần nhất, lỗi tô màu), Thư viện (công thức đóng quảng cáo gộp từ mọi máy),
Bản phát hành (thêm bản mới cho auto-update).

## API cho exe

Xem `SERVER_DESIGN.md` mục 2. Tóm tắt nhanh — `POST /auth/register`, `POST /auth/login`,
`POST /auth/refresh`, `POST /auth/logout`, `POST /session/acquire|heartbeat|release`,
`POST /telemetry/events|error`, `GET|POST /library/recipes`, `GET /releases/latest`.

## TODO (chưa làm)

- `gui_app.py` đã nối đăng nhập + khoá phiên + heartbeat + telemetry (`server_client.py`). Còn thiếu:
  đồng bộ `library/` hai chiều, kiểm tra `/releases/latest` khi mở app.
- Giới hạn tốc độ (rate limit) cho `/auth/login`, `/auth/register` — hiện CHƯA có, dễ bị dò mật khẩu tự động.
- Đổi SQLite sang Postgres nếu lượng người dùng lớn.
