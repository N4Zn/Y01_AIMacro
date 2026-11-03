# ad_autoplayer

Tự bấm xem/đóng quảng cáo của 1 game trong BlueStacks. Chạy local, không cần AI, cửa sổ BlueStacks có thể bị che.
Cần: Python 3, `pip install opencv-python numpy`, `adb`, BlueStacks bật ADB (Settings > Advanced, `127.0.0.1:5555`).

```
python ad_autoplayer.py run [--max-ads N] [--duration GIÂY] [--debug]
python ad_autoplayer.py shot                       # lưu debug/shot.png + activity hiện tại
python ad_autoplayer.py find [--image file.png]    # dò nút đóng, không bấm; lưu debug/find.png
python ad_autoplayer.py learn close_abc 1545 89    # cắt mẫu 48px quanh (x,y) từ màn hình hiện tại
```

## Cách hoạt động

Mỗi vòng: `dumpsys window` lấy activity có focus, rồi

- **Activity chứa `ad_markers`** (AdMob, Unity Ads, AppLovin...): đang ở quảng cáo. Chụp màn hình, nếu thấy mẫu `wait_*` thì đợi (đang đếm ngược). Quá `min_watch_sec` thì dò nút đóng và bấm.
- **Activity của game**: bấm `popup_*`, rồi `trigger_*` (hoặc `trigger_xy`) để mở quảng cáo mới, nghỉ `trigger_cooldown_sec` (quảng cáo tải có lúc >60s).
- **App khác** (Play Store do lỡ bấm quảng cáo): BACK, không được thì mở lại game.
- Quảng cáo quá `ad_timeout_sec` chưa đóng được: bấm BACK.

Dò nút đóng, theo thứ tự ưu tiên:
1. Mẫu `close_*` / `tap_*` do bạn cắt (so khớp toàn màn hình).
2. Dò tổng quát bằng hình học: chữ X (nét mảnh/dày, sáng/tối) và tam giác skip ▶| ở 4 góc màn hình và 4 góc vùng nội dung (bỏ viền đen). Góc dưới cần điểm cao hơn vì hay dính logo Play/App Store. Tam giác trơn ▶ tắt mặc định (`generic_kinds`).

UI dump của `uiautomator` không dùng được vì quảng cáo là WebView.

## Mẫu (`templates/*.png`)

| Tiền tố | Ý nghĩa |
|---|---|
| `close_`, `tap_` | nút cần bấm trong quảng cáo (X lạ, "Skip", "Claim"...) |
| `wait_` | còn thấy thì chưa đóng (vd. `wait_seconds.png`, chữ "seconds" của pill "Reward in N seconds") |
| `trigger_` | nút mở quảng cáo trong game (vd. `trigger_xemqc.png`, biểu tượng phim ở "Xem QC") |
| `popup_` | popup trong game cần bấm (OK, Nhận thưởng...) |

Gặp quảng cáo mà tool không bấm được: đứng ở màn hình đó, `find` xem có ứng viên không; nếu không, `learn close_xxx x y` rồi chạy lại.

## Lưu ý

- Bấm đóng sớm có thể mất thưởng. Tăng `min_watch_sec`, hoặc cắt thêm mẫu `wait_` cho quảng cáo có đếm ngược. Tool không kiểm tra thưởng đã nhận.
- `--debug` lưu ảnh chú thích mỗi lần bấm vào `debug/`, để kiểm tra nó bấm đúng chỗ.
- Cấu hình ghi đè trong `config.json`; xem `DEFAULT_CONFIG` đầu file.
