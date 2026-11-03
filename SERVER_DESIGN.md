# Thiết kế backend EduXplore Ad Helper

Cập nhật 2026-11-03. Thiết kế trước khi code (theo yêu cầu). Stack: Python FastAPI + SQLite (đủ cho quy mô cá nhân, nâng lên Postgres sau nếu cần). HTTPS bắt buộc cho mọi endpoint — không có HTTPS thì các phần dưới đều vô nghĩa (mật khẩu, token đi rõ trên mạng).

## 1. Dữ liệu

**users**
| cột | ý nghĩa |
|---|---|
| id | khoá chính |
| email | duy nhất |
| password_hash | argon2/bcrypt, không bao giờ lưu/log mật khẩu rõ |
| plan | `free` \| `pro` |
| max_devices | số máy tối đa (free=1, pro=N, cấu hình theo plan) |
| is_active | để khoá tài khoản vi phạm |
| created_at | |

**active_sessions** — khoá theo TÀI KHOẢN ĐĂNG NHẬP (email), **chỉ 1 máy đăng nhập tại 1 thời điểm** (xem mục 4; bản đơn giản hoá, KHÔNG còn đọc tài khoản game nữa — theo yêu cầu người dùng: 1 người dùng có nhiều tài khoản game trong cùng 1 game là chuyện bình thường, không liên quan license).
| cột | ý nghĩa |
|---|---|
| id | khoá chính |
| user_id | tài khoản license (email) |
| device_fingerprint | định danh máy — CÓ dùng để phân biệt "cùng máy" hay "máy khác" (khác với bản trước, lúc đó chỉ để log) |
| started_at, last_heartbeat | tool gửi nhịp tim mỗi 20-30s suốt lúc app còn mở (không chỉ lúc đang chạy 1 tác vụ); quá 90s không nhịp tim → coi như phiên đã chết, máy khác đăng nhập được |

Phiên được tạo/chiếm lại tại `/auth/login` và `/auth/refresh` (không còn `/session/acquire` riêng — xem mục 2):
- Không có phiên sống nào khác của `user_id` → tạo mới.
- Có phiên sống với `device_fingerprint` KHÁC → 409 "tài khoản đang đăng nhập ở máy khác".
- Có phiên sống với CÙNG `device_fingerprint` (mở lại app trên chính máy đó) → giữ nguyên `session_id` cũ, chỉ cập nhật nhịp tim (quan trọng: không tạo id mới, nếu không id phía client cũ sẽ lệch khỏi phiên thực tế đang sống).

`POST /session/heartbeat` {session_id} mỗi 20-30s SUỐT lúc app còn mở; `POST /session/release` {session_id} khi Đăng xuất hoặc đóng app.

**refresh_tokens** (JWT access token sống ngắn 30-60 phút, không lưu DB; refresh token sống dài, lưu để thu hồi được)
| cột | ý nghĩa |
|---|---|
| id, user_id, device_id | |
| token_hash | không lưu token rõ |
| expires_at, revoked | thu hồi khi logout hoặc khi admin khoá máy |

**usage_events** (telemetry, gửi theo lô)
| cột | ý nghĩa |
|---|---|
| id, user_id, device_id, ts | |
| type | `app_start` \| `app_stop` \| `category_run` \| `ad_watched` \| `error` |
| payload | JSON tự do: {category, item, count, duration_sec, ...} |

**library_recipes** (server giữ bản gốc, hợp nhất từ mọi máy — logic gộp giống `library.py merge` hiện có, nhưng qua API)
| cột | ý nghĩa |
|---|---|
| key | `activity\|kind\|x_bucket\|y_bucket` |
| activity, kind, x, y | |
| count, sec_min, sec_max, sec_sum | |
| first_seen, last_seen, updated_at | `updated_at` dùng để đồng bộ tăng dần (chỉ tải phần đổi) |

**releases** (cập nhật bản mới)
| cột | ý nghĩa |
|---|---|
| version, channel | channel: `stable` \| `beta` |
| download_url, sha256 | kiểm tra toàn vẹn file tải về |
| notes, force_update | `force_update`: bản cũ quá hạn, bắt buộc cập nhật mới cho chạy tiếp |
| published_at | |

## 2. API

| Endpoint | Việc |
|---|---|
| `POST /auth/register` | {email, password} |
| `POST /auth/login` | {email, password, device_fingerprint} → access_token, refresh_token, entitlements, **session_id** (xem mục 3,4). 409 nếu máy khác đang đăng nhập |
| `POST /auth/refresh` | {refresh_token, device_fingerprint} → access_token mới + **session_id** (cũng kiểm khoá 1-máy-1-lúc — tự đăng nhập lại lúc mở app phải qua cùng khoá, không thì máy khác lách được qua đường refresh) |
| `POST /auth/logout` | {refresh_token, session_id} — thu hồi refresh_token + giải phóng phiên |
| `POST /session/heartbeat` | {session_id} — gọi định kỳ suốt lúc app còn mở |
| `POST /session/release` | {session_id} — khi Đăng xuất hoặc đóng app |
| `POST /telemetry/events` | gửi lô sự kiện (auth bắt buộc) |
| `POST /telemetry/error` | gửi báo lỗi kèm traceback rút gọn |
| `GET /library/recipes?since=ts` | tải công thức đổi/mới kể từ lần đồng bộ trước |
| `POST /library/recipes` | đẩy công thức máy này học được lên để gộp |
| `GET /releases/latest?channel=stable` | kiểm tra bản mới |

## 3. Free / trả phí

Không tách bằng code riêng, tách bằng **entitlements** trả về lúc đăng nhập — ví dụ free chỉ có `["mainmenu","shop"]`, pro có `["all"]`. `gui_app.py` ẩn/khoá các hạng mục không nằm trong entitlements. Đổi gói chỉ cần đổi dữ liệu ở server, không cần phát hành bản exe mới.

## 4. Khoá theo tài khoản đăng nhập + 1 máy tại 1 thời điểm (bản hiện tại)

**Lịch sử:** bản đầu khoá theo TÀI KHOẢN GAME (đọc `Txt_MM_top_name` qua DevTools, không OCR) để cho phép đổi máy tự do miễn không 2 máy cùng chạy 1 tài khoản game. Đã bỏ hẳn theo yêu cầu người dùng: 1 người dùng có nhiều tài khoản game (vd tài khoản Android + tài khoản liên kết tivi trong cùng 1 game) là chuyện bình thường, không nên khiến tool phải đọc/phân biệt — và việc đọc chi tiết tài khoản người dùng bị coi là hơi nhạy cảm.

**Bản hiện tại, đơn giản hơn:** khoá thẳng vào tài khoản ĐĂNG NHẬP (email) — chỉ 1 máy đăng nhập tại 1 thời điểm, không quan tâm đang chơi tài khoản game nào. Dùng `device_fingerprint` (băm `MachineGuid` + serial ổ đĩa + tên máy, không gửi thông tin thô) để phân biệt "mở lại trên chính máy này" (cho qua, giữ nguyên phiên) với "máy khác" (chặn, trả 409). Kiểm tra ngay lúc `/auth/login` và `/auth/refresh` (tự đăng nhập lại lúc mở app), không còn một bước `/session/acquire` riêng lúc bắt đầu chạy — nghĩa là phiên "đang đăng nhập" sống suốt lúc mở app, không chỉ lúc đang xem quảng cáo.

## 5. Luồng phía exe (`gui_app.py`)

1. Mở app → có token cũ còn hạn (lưu mã hoá cạnh exe) thì tự đăng nhập lại qua `/auth/refresh`; không thì hiện màn đăng nhập/đăng ký (`LoginDialog`, tự điền sẵn email + mật khẩu nếu còn tick "Ghi nhớ đăng nhập" lần trước).
2. Đăng nhập/refresh thành công → nhận `session_id`, bắt đầu gửi `POST /session/heartbeat` mỗi 25s NGAY LÚC ĐÓ, sống suốt lúc app còn mở (không phải chỉ lúc Bắt đầu). Bị 409 (máy khác đang đăng nhập) → báo trong log, mở màn đăng nhập.
3. Bấm Bắt đầu / Chạy hàng đợi: chạy thẳng (`eng.run(...)`, `eng.run_four_gods()`, `eng.auto_play_stage(...)`) — không còn bước khoá phiên riêng, vì phiên đã sống từ lúc đăng nhập.
4. Đăng xuất hoặc đóng app → dừng nhịp tim + `POST /session/release`.
5. Trong lúc chạy: `GET /library/recipes` đồng bộ về, chạy xong gửi `POST /library/recipes` đẩy công thức mới học + `POST /telemetry/events` theo lô (không chặn luồng chính nếu mất mạng — lỗi mạng chỉ log, không dừng việc xem quảng cáo).
6. Lỗi bất kỳ → `POST /telemetry/error` kèm traceback rút gọn.
7. *(Chưa làm)* `GET /releases/latest` khi mở app, báo có bản mới.

## 6. Bảo mật / giới hạn thành thật

- Chặn được: chia sẻ tài khoản tràn lan, xem lướt thư viện khi tool không chạy, dùng tool mà không qua đăng ký.
- Không chặn được: người dùng có chủ đích bắt gói tin trên chính máy họ (tự cài chứng chỉ gốc để xem HTTPS), hoặc dùng debugger/Frida đọc bộ nhớ lúc tool đang chạy. Đã thống nhất từ trước: mục tiêu là không lộ liễu, không phải bất khả xâm phạm.
- Giới hạn tốc độ (rate limit) cho `/auth/login` và `/auth/register` để chặn dò mật khẩu tự động.
