# Ghi chú: tự động hoá game "El Dorado" (busidol.mobile.eldorado) trên BlueStacks

Cập nhật 2026-11-03. Đây là ghi chú làm việc, không phải spec. Công thức đọc từ code JS của game lúc chạy, có thể đổi theo bản cập nhật.

## Công cụ trong thư mục này

| File | Việc |
|---|---|
| `ad_autoplayer.py run` | Vòng lặp xem/đóng quảng cáo (adb + OpenCV). `shot`, `find`, `learn`, `collect` là lệnh phụ |
| `stage_caller.py` | Trong màn chơi: mỗi 2s bấm MISSILE (185,800) rồi phím 1-4 (mỗi phím 2 lần, nghỉ 0,2s). Dừng khi `cur_scene` đổi |
| `shop_ads.py` | Xem quảng cáo ở tab Quảng cáo của Shop, kiểm tra hạn mức bằng DevTools |
| `templates/` | Mẫu ảnh: `close_*`, `tap_*`, `wait_*`, `trigger_*`, `popup_*` |
| `samples/` | Mẫu quảng cáo/màn chơi do `collect` lưu (không commit) |

Cần: BlueStacks bật ADB (127.0.0.1:5555), `adb` trên PATH (adb trong Android SDK của máy này không chạy được, dùng `C:\platform-tools-latest-windows`), Python + opencv-python + websockets.

## Server + giao diện quản trị (`server/`)

Thiết kế đầy đủ: `SERVER_DESIGN.md`. Backend FastAPI + SQLite + giao diện quản trị web (Jinja2, tự render, không SPA). Chạy thử: `powershell -File server/run.ps1` → API ở `:8000`, quản trị ở `/admin/login` (mật khẩu `EDUXPLORE_ADMIN_PASSWORD`, mặc định `admin123` — CHỈ để thử). Đã kiểm thật: đăng ký/đăng nhập, khoá 1-máy-1-lúc (409 đúng khi máy khác đang đăng nhập), đổi gói free/pro qua giao diện (xác nhận lại bằng API login), log sự kiện/lỗi, đồng bộ thư viện, thêm bản phát hành qua form.
`gui_app.py` đã nối với server (`server_client.py`): màn đăng nhập/đăng ký khi mở app (lưu token + mật khẩu cục bộ, mã hoá nhẹ, tự đăng nhập lại lần sau), heartbeat mỗi 25s bắt đầu NGAY LÚC ĐĂNG NHẬP (sống suốt lúc app mở, không chỉ lúc Bắt đầu), `/session/release` khi Đăng xuất/đóng app, gửi `/telemetry/events|error`. Hạng mục không nằm trong entitlements hiện mờ "🔒 cần gói Pro" thay vì ẩn. **Đã bỏ hẳn việc đọc tài khoản game khỏi licensing** (xem mục "Khoá 1-máy-1-lúc" bên dưới) — `start()`/`run_queue()` không còn gọi `eng.game_account()` nữa. Đã kiểm thật (không giả lập, kể cả lỗi session_id lệch khi refresh cùng máy): xem `SERVER_DESIGN.md` mục 4.
**Chưa làm:** đồng bộ `library/` 2 chiều với server, kiểm tra bản mới (`/releases/latest`) khi mở app. Chưa có rate limit cho `/auth/login|register`.
**Lỗi thứ 2 đã sửa:** phần tử `FG_select_lock_N` KHÔNG phản ánh đúng trạng thái khoá thật — đoán sai từ tên biến, không kiểm chứng bằng ảnh chụp màn hình. 2 thẻ bị coi nhầm là khoá thực ra chơi được bình thường. Đã bỏ hẳn bước đoán khoá qua tên phần tử; giờ cứ bấm thử mọi ô hiện ra, dựa vào scene có đổi hay không để biết thần đó có vào được không. Đã xác nhận cả 4 vị thần đều được quét đúng, 2 thần "tưởng khoá" trước đó giờ xem được quảng cáo thật.

**Bài học:** đặt tên phương thức `_register` trong `LoginDialog(tk.Toplevel)` trùng với `tkinter.Misc._register` nội bộ (đăng ký callback Tcl) → ghi đè làm hỏng việc dựng Button ngay giữa chừng → cửa sổ hiện trắng dở dang, không báo lỗi gì (app `--windowed` không có console để in traceback). Tránh đặt tên phương thức bắt đầu `_` trên class kế thừa widget tkinter mà không tra trước; đã đổi thành `_do_register` và bọc `_ensure_auth` trong try/except ghi log để lỗi tương tự sau này không còn âm thầm biến mất.
**Lỗi cùng họ gặp lại ở `StageStepDialog`:** `ttk.Checkbutton(..., wraplength=340)` ném `TclError` ("unknown option -wraplength") ngay lúc khởi tạo trên máy test — `ttk.Checkbutton` không nhận `wraplength` làm tham số constructor (khác `ttk.Label`, nơi vẫn dùng bình thường). Hậu quả giống hệt lỗi `_register`: widget dựng dở dang, các phần tử sau đó (cả nút "Thêm vào hàng đợi") không bao giờ được tạo — người dùng mở form chỉ thấy vài ô đầu, không có cách nào chạy tiếp. Đã sửa: bỏ `wraplength` khỏi mọi `Checkbutton`, câu chú thích dài tách ra `Label` riêng (Label dùng `wraplength` bình thường). Cũng tăng kích thước cửa sổ (380×420 → 420×580) và cho phép kéo giãn (`resizable(True, True)`) để phòng trường hợp tương tự (nội dung dài hơn khung cố định) không còn làm mất nút ở cuối. **Rút kinh nghiệm chung: mọi cửa sổ Tkinter mới nên test dựng thật (gọi trực tiếp, không qua UI) trước khi coi là xong — lỗi dạng này im lặng hoàn toàn trên bản exe `--windowed`, không có console để phát hiện.**
**Lưu ý khi cài máy mới:** `pip install -r server/requirements.txt` bản ghim sẵn (fastapi 0.115.6 + starlette 0.41.3 + jinja2 3.1.4) — bản fastapi mới nhất (0.162, cài nếu không ghim version) lỗi `TypeError: unhashable type: 'dict'` khi render Jinja2Templates, chưa rõ nguyên nhân sâu, không điều tra thêm.

## Sửa Khoáng (Mineral) trong tự chơi màn

Người dùng báo Khoáng không có tác dụng — đúng vậy, suy luận mã phím TV-remote (KEYCODE_PROG_GREEN=184) ban đầu sai hoàn toàn. Đọc lại qua DOM thật trong trận: **Tên lửa và Khoáng đều là NÚT TRÊN MÀN HÌNH, không phải phím** — nằm cạnh nhau trong thanh điều khiển dưới cùng (`game_bottom_ui_missile` ở (185,791), `game_bottom_ui_mineral` ở (394,791), toạ độ device px, cách nhau ~210px). `auto_play_stage` giờ đọc toạ độ thật qua `el()` ngay trong trận (có dự phòng bằng số cố định nếu đọc lỗi). Đã xác nhận: lệnh tạo ra đúng `input tap 394 791` cho Khoáng. Thiên thạch vẫn dùng phím (KEYCODE_DPAD_DOWN=20, đọc từ mã nguồn `S_GAME.keyDown`, chưa bị báo lỗi).

## TODO: giao diện cần đúng 2 lựa chọn rõ ràng cho "tự chơi màn" (ĐANG LÀM — dừng giữa đường để đổi session, xem mục "Trạng thái dừng giữa đường" cuối file)

Người dùng chốt lại cách hiển thị trên giao diện — thay cho 1 checkbox "Tự cày" mơ hồ hiện có, cần 2 lựa chọn tách biệt rõ ràng (dạng chọn 1 trong 2, vd radio button):
1. **"Chơi liên tục trong ... giây"** — tool không tự vào/tự chuyển màn; cứ hễ phát hiện bạn đang ở trong màn chơi (`S_GAME`, bất kỳ màn nào) là tự gọi lặp, màn đó kết thúc thì lại tiếp tục CHỜ bạn tự vào màn tiếp theo (bất kỳ màn nào, tự chọn), cứ thế tới khi hết tổng số giây đã đặt. **ĐÃ CODE xong trong `engine.py`**: `watch_and_play(duration_sec, chars, missile, mineral, meteor, interval, repeat, gap, stage_max_sec, wait_entry_sec, watch_result_ad)` + `_watch_and_play_impl` — lặp gọi `auto_play_stage` tới khi hết `duration_sec` hoặc bị Dừng, KHÔNG tự bấm "Chọn bàn" hay tự chuyển màn. Chưa nối vào `gui_app.py`.
2. **"Chơi lặp lại 1 màn cụ thể, theo số lần"** — tool tự vào lại ĐÚNG màn đó sau mỗi lượt (không tiến dần như `farm_stages` hiện có). Chi tiết giao diện (chốt):
   - **2 ô nhập tách riêng**, không gộp 1 ô kiểu "115 khó":
     - **Dropdown Khó/Thường**, mặc định **Thường**.
     - **Ô nhập số** (không phải dropdown danh sách — số màn rất nhiều, gõ số trực tiếp).
   - Cộng thêm ô "số lần lặp" như các bước khác.
   - **Nhớ lựa chọn lần trước** (khó/thường + số màn + số lần) để lần sau mở lại không phải nhập lại — tương tự cách `last_login.json` đang nhớ email/mật khẩu đăng nhập; có thể lưu vào 1 file nhỏ riêng cạnh exe (vd `last_stage_choice.json`), đọc lại làm giá trị mặc định khi mở `StageStepDialog`.
   - Đây là phần đã dò được cơ chế (xem mục "Tự cày màn" bên dưới: công thức số màn = (bản_đồ-1)×20+ô, 2 lớp chọn `S_SELECTMAP_HARD`/`S_SELECTSTAGE_HARD`, cảnh thường là `S_SELECTMAP`/`S_SELECTSTAGE` — chưa xác nhận tên chính xác) nhưng CHƯA code `goto_stage(n, hard)`.

Bỏ/thay thế checkbox "Tự cày liên tiếp nhiều màn" hiện tại (`farm_stages`, tiến dần từng màn) — không đúng nhu cầu, giữ lại code vì có thể còn dùng được nhưng không phải lựa chọn chính hiển thị trên giao diện.

## ĐÃ SỬA: thứ tự + giá trị mặc định của `auto_play_stage`

Đã áp dụng trong `engine.py` (`_auto_play_stage_impl`): thứ tự thao tác mỗi lượt giờ là **Nhân vật (đúng thứ tự người dùng chọn, vd "12345") → Khoáng → Tên lửa → Thiên thạch** (nếu bật). Giá trị mặc định mới trong `auto_play_stage(...)`: `gap=0.05` (trước 0.2), `repeat=1` (trước 2), `interval=1.0` (trước 2.0). **Còn thiếu:** chưa sửa mặc định tương ứng trong `StageStepDialog.__init__` (gui_app.py) — UI vẫn hiển thị giá trị cũ, cần đồng bộ khi làm lại giao diện.

## Tự cày màn (3 chế độ)

1. **Xong, test kỹ** (`engine.auto_play_stage`) — bạn tự vào 1 màn bất kỳ, tool tự phát hiện (`cur_scene == S_GAME`) rồi mới gọi lặp.
2. **Xong code, CHƯA test live trọn vẹn** (`engine.farm_stages`) — tiến dần từng màn (không phải nhu cầu chính, giữ code không ưu tiên UI).
3. **Cơ chế đã CONFIRM LIVE + code xong `goto_stage`/`run_fixed_stage` trong `engine.py`, nhưng CHƯA test live trọn vẹn qua đúng các hàm đã code** (xem mục "Trạng thái dừng giữa đường" cuối file):
   - Công thức xác nhận đúng cả Khó và Thường: `target_map = (N-1)//20 + 1`, `target_cell = (N-1)%20 + 1`.
   - Thường dùng prefix `SM`/`SS` (`S_SELECTMAP`/`S_SELECTSTAGE`), Khó dùng `SMH`/`SSH` (`S_SELECTMAP_HARD`/`S_SELECTSTAGE_HARD`) — cấu trúc song song hoàn toàn.
   - Nút chuyển Thường ⇄ Khó: `Img_SM_mode_bt` (đã xác nhận live, đổi cảnh giữa `S_SELECTMAP`/`S_SELECTMAP_HARD`).
   - Đường vào: Main menu → `MM_menu7` (GAME START) → `S_MODE_SELECT` → `MOS_card_div_1` ("Story Mode") → `S_SELECTMAP`/`S_SELECTMAP_HARD` → cuộn trang bằng `Img_{SM|SMH}_leftarrow`/`rightarrow` tới khi `{SM|SMH}_map_{target_map}` hiện `shown+inview` → bấm (vào thẳng `S_SELECTSTAGE`/`S_SELECTSTAGE_HARD`, 1 bấm = chọn+xác nhận) → bấm `{SS|SSH}_menu{target_cell}` (1 bấm = chọn+xác nhận, vào thẳng `S_GAME`).
   - Màn thắng `S_STAGECLEAR`: `SC_btn3`="Main Menu", `SC_btn5`="Chọn bàn" (vào thẳng `S_SELECTSTAGE`/`S_SELECTSTAGE_HARD` CÙNG bản đồ, dùng cho `farm_stages`).
   - PVP và Sky Garden hoàn toàn chưa đụng tới.

## Hàng đợi bước chạy + preset có tên + tự chơi màn

`gui_app.py` có khung "Hàng đợi bước chạy": thêm nhiều bước (QC hoặc tự chơi màn) chạy tuần tự dưới 1 phiên khoá duy nhất. Lưu/nạp cấu hình theo tên (`presets.json` cạnh exe).
**Tự chơi màn** (`engine.Engine.auto_play_stage`, dùng chung cho GUI và `stage_caller.py` CLI): tool KHÔNG tự chọn màn/đội — bước chờ tới `wait_entry_sec` (mặc định 60s) để người dùng tự vào màn chơi (`S_GAME`), rồi mới gọi lặp. Thao tác điều khiển trong màn — đọc thẳng từ `S_GAME.keyDown` của game, không đoán:
- Nhân vật 1-5: Android keyevent 8-12 (KEYCODE_1..5) — đã dùng từ trước, xác nhận hoạt động.
- Thiên thạch (Meteor): Android keyevent 20 (KEYCODE_DPAD_DOWN) — khớp `KeyDefine.down` → `S_GAME.run_metor()`.
- Tên lửa (Missile): vẫn tap toạ độ (185,800) như cũ (đã xác nhận) — phím `KeyDefine.RED`/`A` dùng mã JS keyCode TV-remote (227), không gõ được qua `adb input keyevent` thường.
- Khoáng (Mineral): thử Android keyevent 184 (KEYCODE_PROG_GREEN, suy từ `KeyDefine.GREEN`=178) — **CHƯA kiểm chứng trong trận thật**.

## Giao diện exe (cho người dùng không có AI)

`gui_app.py` (tkinter) + `engine.py` (lõi). Build: `powershell -File build_exe.ps1` → `dist\EduXploreAdHelper\` (+ `.zip`, ~68MB, kèm `adb\` nên máy khác không cần cài adb; hướng dẫn trong `HUONG_DAN.txt`). Dữ liệu ghi cạnh exe: `logs\`, `library\`, `config.json`.
Tìm adb: `adb\adb.exe` cạnh exe → PATH → `HD-Adb.exe` của BlueStacks → Android SDK. Nút "Kết nối/Tìm" quét cổng 5555..5595 (BlueStacks mỗi instance 1 cổng).
Cấu trúc game (đọc qua DevTools, chỉ đọc): giao diện là DOM, viewport 1067x600 CSS px × `devicePixelRatio` 1.5 = màn 1600x900. Nút lấy bằng `document.getElementById(id).getBoundingClientRect()`; ngoài viewport (`inview=false`) = thẻ Shop cần cuộn → vuốt trái/phải tới khi vào khung. `REWARD_AD.btn_list[id] = {place, sub}` ánh xạ nút ↔ mục (Shop `MS_ad_btn_1..8`, menu `MM_ad_btn`, Marble `EM_btn3`, Jackpot `JG_ad_btn`, Điểm danh `AE_ad_btn`). Hạn mức: `REWARD_AD.place_cfg`.
Đường đi từ menu chính (id DOM): Shop `MM_menu4` rồi tab Quảng cáo `Img_MS_basic_bg_8`; Event `AE_main_icon` rồi `SE_event_btn1/2/3` = Điểm danh / EldoMarble / Jackpot. Quay lại: Shop (35,33 css), `SE_back_btn`, `EM_btn1`, `JG_back_btn`. Màn lạ = dừng, không đoán.
Chưa hỗ trợ điều hướng (có hạn mức, hiển thị mờ trong GUI): stageselect, stageclear, cloud_garden, four_gods, attendance, guild_donate, guild_boss_result.

## Các vị trí quảng cáo khác đã dò (REWARD_AD.place_cfg)

Xác nhận menu-navigable, CHƯA đưa vào CATEGORIES (ưu tiên sau): Điểm danh (`AE_ad_btn`, qua Sự kiện), Tứ thần (`S_FOUR_GODS`, qua nút "Đền" ở main menu — cần chọn 1 vị thần, ad button trong màn con chưa dò tới). `attend_x2` và `stageselect`(`SS_ad_btn`) đã thấy xuất hiện trong `REWARD_AD.btn_list` khi người dùng tự chơi nhưng chưa dò được vị trí/đường vào qua tool.
**Sửa lại: Cloud Garden ĐÃ xem được ngay khi vào** (không cần chơi xong — người dùng chỉnh lại nhận định sai trước đó). Đường vào: menu chính → `MM_menu7` (GAME START) → `S_MODE_SELECT` → **cuộn phải** (thẻ chế độ chơi cuộn ngang, Cloud Garden là thẻ thứ 6, ẩn ngoài màn hình lúc đầu) → `MOS_card_div_6` → `S_RANKING_CLOUD_GARDEN`, nút `RCG_ad_btn`. Đã thêm vào `CATEGORIES["cloud_garden"]`, `ensure_in()` hỗ trợ bước `("SWIPE:right", None)` trong route. Đã xem thật 1 quảng cáo, hạn mức tăng 0→1 đúng.
**Bài học quan trọng:** `MM_menu7` (GAME START) rộng hơn viewport (lồi ra ngoài `innerWidth`), nên điều kiện "trong khung nhìn" cũ (yêu cầu CẢ HỘP nằm trọn) luôn sai dù bấm được bình thường → `tap_el()` thất bại ngẫu nhiên tuỳ nút. Đã sửa `EL_JS`: `inview` xét theo TÂM nút, không phải cả hộp. Ảnh hưởng tốt tới mọi nút to tương tự trong tương lai, không riêng Cloud Garden.
**Vẫn chưa "đi tới" được (màn kết quả sau trận):** `stageclear` (multi 20 = +2000% vàng), `boss_result`, `guild_boss_result` — xem qua cơ chế `watch_result_ad` tổng quát trong tự chơi màn (mục dưới), không qua CATEGORIES.
**Đã giải quyết bằng cơ chế tổng quát** thay vì dò riêng từng cái: `Engine.find_visible_ad()` quét `REWARD_AD.btn_list` tìm BẤT KỲ nút quảng cáo nào game đang cho hiện + còn hạn mức trên màn hiện tại (không cần biết trước id). `auto_play_stage(..., watch_result_ad=True)` gọi hàm này ngay khi phát hiện màn kết thúc (scene đổi) và tự xem nếu có — áp dụng được cho stageclear/Cloud Garden/boss mà không cần map riêng từng màn. Checkbox "Xem QC kết quả sau khi hết màn" trong form tự chơi màn (mặc định bật). Đã xác nhận JS không lỗi trên game thật; chưa xác nhận dương tính (chưa ai hoàn thành 1 màn kể từ khi thêm — sẽ tự lộ khi có người chơi).
`guild_donate`: cần đang ở trong 1 bang hội thật (tài khoản test đang ở màn "vào/lập bang hội", chưa trong bang hội nào) — chưa kiểm chứng được.

## TODO: quảng cáo mở thẳng Play Store giữa chừng (CHƯA xử lý trong tool)

Gặp thật 1 lần: quảng cáo "Amaze GO!" lúc đang xem tự mở thẳng trang Google Play thật (focus app đổi hẳn sang `com.android.vending`, activity `com.google.android.finsky.transparentmainactivity.HsdpAlias`) — không phải WebView quảng cáo trong app như bình thường. Phần thưởng (`Reward granted`) đã ghi nhận ngay từ lúc này, có nút X cạnh chữ đó đóng được ngay. Đóng xong quay về đúng `AdActivity` gốc, màn "end card" (logo app + nút X, cũng có sẵn `Reward granted`) — đóng tiếp là xong, không có gì bất thường, chỉ là tool hiện **chưa nhận diện được** `com.android.vending` như 1 trạng thái "trong quảng cáo" (`is_ad()`/`ad_markers` không có package này) nên nếu gặp lúc chạy tự động sẽ bị tính là "app lạ", dừng lại chờ xử lý (an toàn nhưng không tự đóng được).
**Việc cần làm:** thêm `com.android.vending` (hoặc cụ thể hơn: activity `finsky.transparentmainactivity`) vào danh sách nhận diện "vẫn đang trong luồng quảng cáo" (không phải app lạ thật sự) — tìm nút X theo mẫu ảnh hoặc theo text "Reward granted" kế bên, rồi quay lại vòng lặp đóng quảng cáo bình thường.

## Game nhiều tài khoản (Android + "tài khoản tivi")

Game có tính năng kết nối tivi riêng, đổi sang 1 tài khoản khác hẳn tài khoản Android ban đầu — bình thường, không phải lỗi. Gặp lỗi `game_account()` đọc rỗng khi vừa đổi tài khoản, phải thử đọc lại — rồi người dùng yêu cầu bỏ hẳn, chuyển hướng licensing khác (xem dưới). `engine.game_account()`/`ensure_in_four_gods` không liên quan vẫn còn trong code (đọc tên hiển thị cho mục đích khác nếu cần sau này), chỉ không còn dùng để khoá phiên.

## Khoá 1-máy-1-lúc (đã đổi từ "khoá theo tài khoản game")

**Theo yêu cầu người dùng: bỏ hẳn việc đọc tài khoản game khỏi licensing — nhạy cảm, và 1 người dùng có nhiều tài khoản game (Android + tivi) là chuyện bình thường.** Đổi sang khoá thẳng tài khoản đăng nhập (email), chỉ 1 máy tại 1 thời điểm, kiểm tra ngay lúc `/auth/login` và `/auth/refresh` — chi tiết đầy đủ ở `SERVER_DESIGN.md` mục 4. Phiên server giờ sống suốt lúc app mở (tạo lúc đăng nhập, nhả lúc đăng xuất/đóng app), không còn gắn với từng lượt Bắt đầu.
**Bài học:** lúc refresh token từ CÙNG 1 máy, nếu server tạo `session_id` mới mỗi lần (xoá cũ tạo mới) thì `session_id` phía client giữ sẵn (vd để gọi `/session/release` lúc đăng xuất) sẽ lệch khỏi phiên thực tế đang sống → đăng xuất tưởng đã nhả phiên nhưng thật ra phiên mới (tạo lúc refresh sau đó) vẫn còn, máy khác vẫn bị chặn nhầm. Sửa: refresh từ cùng `device_fingerprint` phải GIỮ NGUYÊN session cũ (chỉ cập nhật nhịp tim), không tạo mới.

## Tứ thần (`engine.Engine.run_four_gods`)

Vào qua nút "Đền" (`BD_main_button`) ở menu chính → `S_FOUR_GODS` (4 ô `FG_select_box_1..4`, ô khoá có thêm `FG_select_lock_N`). Vào từng ô đã mở khoá → màn riêng mỗi vị thần (vd `S_BLUE_DRAGON`, nút quảng cáo `BD_ad_box`) → dùng `find_visible_ad()` tổng quát để xem nếu còn hạn mức (hạn mức tính theo TỪNG vị thần, 1 quảng cáo/vị/ngày) → quay lại `S_FOUR_GODS` cho ô tiếp theo. Đã xác nhận vị thần 1 (Rồng Xanh) hoạt động đúng (phát hiện đã xem hôm nay, đúng với thực tế). Gọi qua bước hàng đợi loại `"four_gods"` (không cần cấu hình gì thêm — tự xem hết các vị thần đã mở khoá).
**Bài học:** khi bấm bằng toạ độ CSS đọc từ `el()`/dump, PHẢI nhân hệ số `devicePixelRatio` (1.5) trước khi gọi `adb.tap()` trực tiếp — `el()` đã trả toạ độ nhân sẵn, nhưng nếu tự dùng toạ độ CSS thô từ dump khác thì phải tự nhân, nếu không nút bấm trật đi ~1/3.
**Lỗi thật đã sửa:** màn con mỗi vị thần (vd `S_BLUE_DRAGON`, `S_FOUR_TIGER`) không có nút lùi chung `Img_MM_top_back`, nên khi `run_four_gods()` cố quay lại `S_FOUR_GODS` bằng `ensure_in_four_gods()` (đi qua `go_main()`) sẽ bị kẹt — đặc biệt rõ khi vị thần đã xem hôm nay (không có bước bấm xem QC nào xen giữa để "giải phóng" màn hình). Đã sửa: bấm thẳng toạ độ cố định (519,786, device px) trước — vị trí nút lùi giống nhau cho cả 4 vị thần (chỉ đổi hình/tên) — chỉ đi vòng qua `ensure_in_four_gods()` khi cách đó không ăn. Đã xác nhận cả 2 nhánh (thần đã xem hôm nay lẫn thần chưa xem, xem được 1 quảng cáo thật) đều quay lại đúng `S_FOUR_GODS`.

## Thư viện kinh nghiệm quảng cáo (`library/`, `library.py`)

`shop_ads.py` và `ad_autoplayer.py run` tự ghi mỗi lần đóng quảng cáo thành công vào `library/index.json`: công thức khoá theo (activity, loại nút x/skip/back/auto, ô vị trí 40px) + số lần gặp, thời gian đóng min/max/tb, ảnh mẫu 480px (tối đa 5/công thức), mẫu cắt nút. Quảng cáo không đóng được (nhảy sang app lạ) vào `library/unresolved/`.
Không phụ thuộc tài khoản/máy: commit hoặc copy thư mục `library/`; `python library.py merge <thư mục>` gộp từ máy khác, `python library.py report` xem tổng hợp. Hiện thư viện chỉ ghi, chưa dùng ngược lại để dò nút.
Bộ chống bấm nhầm: `CloseTracker` chỉ cho bấm nút đóng khi còn nguyên vị trí và hình qua 3 frame liên tiếp.
Random thao tác: `tap_jitter_px`, `pre_tap_delay`, `delay_jitter` trong config.

## Cách đọc trạng thái game (quan trọng nhất)

Game là app Android thuần, giao diện là web chạy trong WebView, WebView debugging **bật**:

```
adb forward tcp:9222 localabstract:webview_devtools_remote_<pid game>
GET http://127.0.0.1:9222/json   ->  trang index_amo.html  ->  websocket  ->  Runtime.evaluate
```
Tên socket có pid nên đổi mỗi lần game khởi động (`pidof busidol.mobile.eldorado`). Hàm `game_scene()`/`cdp_eval()` trong `ad_autoplayer.py` làm việc này.

- Màn hiện tại: `g_sceneinfo.cur_scene` (ví dụ `S_GAME`, `S_STAGECLEAR`, `S_MAINMENU`, `S_PACKAGE_STORE`). Có 144 scene (các hằng chuỗi `gS_*`).
- Trong màn chơi: `OUR_TEAM_ARRAY`, `YOUR_TEAM_ARRAY`, `CASTLE_OUR`, `CASTLE_YOUR`, `S_GAME.my_mineral`, `USER`.
- Quảng cáo thưởng: `REWARD_AD.place_cfg[<vị trí>]` có `limit` (số lần/ngày), `used`, `multi`.
  Vị trí: stageselect 5, mainmenu 5, stageclear 10, cloud_garden 10, marble 5, jackpot 5, attendance 1, attend_x2 1, four_gods 1, guild_donate 1, guild_boss_result 30, shop_ad (gold 5, ruby 5, cloud 5, cel_essence 1, day_ticket/garden/pvp/boss_ticket 1, tổng 20/ngày).
- Trang Shop: `S_PACKAGE_STORE`, tab "Quảng cáo", nút "Xem QC" ở y=657, x = 225 (Gold), 607 (Ruby), 988 (Cloud Piece), 1370 (Celestial Essence). Các thẻ vé nằm bên phải, phải cuộn.
- Chỉ đọc, **không gọi hàm** của game.

## Quảng cáo (SDK)

Mediation AppLovin MAX + Unity Ads, Vungle, Meta, Pangle, Mintegral, Fyber, AdMob, và mạng Hàn Quốc (Igaworks, Naver GFP, Kakao AdFit, Coupang, Cauly, Mobon, Mobwith). Activity: `com.google.android.gms.ads.AdActivity` (AdMob, nút X góc trên phải, có pill "Reward in N seconds" cần chờ), `com.unity3d.ads.adplayer.FullScreenWebViewDisplay` (Unity, nút skip ▶| trên trái hoặc X trên phải, xuất hiện sau ~30s). UI dump của uiautomator không dùng được (WebView).

## Công thức (đọc từ `CAL`, `USER`, `S_GAME`)

- Nhân vật: `base = start + (end−start)/(p−1)×(cấp−1)`, `p=(sao+1)×10`. `AP/HP = floor(base×(1+u)+cố_định_item)`. `u` cộng dồn: huy chương, % item (base option), bộ item độc quyền, buff bang hội, +100% cho họ nhân vật sự kiện tháng. AP item loại 1, HP loại 3.
- Huy chương n (1..60): 5 màn `(n−1)×5+1..n×5`, hạng A=3, B=2, C=1, thiếu hạng = 0, `value = tổng/15`.
  AP: 0,25·v6+0,5·v17+0,25·v26+0,5·v35+0,5·(v40+v44+v54+v56+v58+v60). HP: 0,25·v7+0,5·v18+0,25·v27+0,25·v36+0,5·(v42+v53+v55+v57+v59).
- Tên lửa: sức mạnh `(100+4×cấp thẻ 4)×(1+0,5·v4+v15+v24+v33+0,5·v43)`. Hồi: `tick×(1−0,5·v3)`, tick = 500−4,5×(L−1) (L≤100).
- HP thành ta: `(15·L²+60)×(1+0,5·v5+v16+v25+v34+0,5·v41+0,2·(v49..v52))` (L=cấp thẻ 5). Số thật khớp: 547.020.
- Mana (huy chương **nhân**): hồi `0,3×cấp thẻ 1×(1+0,5·v1)(1+v13)(1+v22)(1+v31)(1+v45)`; tối đa `100+floor(24·L/10)×10` (L=cấp thẻ 2) `×(1+0,25·v2)(1+0,5·v14)(1+0,5·v23)(1+0,5·v32)(1+0,5·v46)` (khớp 8015).
- Thẻ nâng cấp (9 thẻ): 1 hồi mana, 2 mana tối đa, 3 hồi tên lửa, 4 sức mạnh tên lửa, 5 HP thành, 6 số nhân vật trên màn (max 20), 7 Meteor (chưa đọc), 8 kho nhân vật, 9 kho vật phẩm.
- Damage: nhân vật đánh `attack_power`; lên thành địch từ màn 9 là `/5`; địch ARMOR chỉ nhận 1 mỗi đòn; vài đơn vị chịu tối đa 30% full_hp mỗi đòn.
- Chưa đọc: Meteor (`CAL.get_metor_power`), huy chương vàng/giảm khoáng/tốc độ sản xuất nhân vật.

## Bài học

- **Mẫu `trigger_xemqc` khớp nhầm** (biểu tượng phim có sọc, ảnh xám, mẫu nhỏ, ngưỡng 0,8) vào cánh buồm thuyền Viking ở menu chính và lá cờ ở màn Lập nhóm. Tool bấm lang thang, mở Play Store, bấm BACK ở menu gốc thì **thoát game ra launcher**, rồi adb mất kết nối. Quy tắc: chỉ bấm trigger khi `cur_scene` đúng màn mong đợi, dừng nếu bấm trigger quá 3 lần mà không có quảng cáo, không bấm BACK khi đang ở game.
- Hết hạn mức ngày thì nút xem QC biến mất và game tự về menu.
- `python -I` bỏ qua `PYTHONIOENCODING`, in tiếng Hàn/Việt sẽ lỗi.
- Phím 1-4 nhận được trong game (adb `input keyevent` 8..11). Giữa các phím cần nghỉ 0,2s.
- Mỗi lệnh `adb shell input` tốn khoảng 0,1-0,2s nên vòng 9 thao tác thực tế ~3s, không phải 2s.

## Trạng thái dừng giữa đường (2026-11-03, đổi session vì tốn token)

Đã code xong trong `engine.py` (chưa đụng `gui_app.py`):
- `_auto_play_stage_impl`/`auto_play_stage`: thứ tự + mặc định mới (xem mục "ĐÃ SỬA" trên).
- `watch_and_play`/`_watch_and_play_impl`: mode "chơi liên tục trong ... giây" (xem mục TODO #1 trên).
- `goto_stage`/`_goto_stage_impl`: điều hướng tới đúng 1 màn cố định theo công thức `(map,cell)`.
- `run_fixed_stage`/`_run_fixed_stage_impl`: lặp `goto_stage` + `auto_play_stage` N lần, dừng nếu không về đúng `S_STAGECLEAR`.

**Việc tiếp theo cần làm (chưa làm xong):**
1. **Test live `goto_stage()`/`run_fixed_stage()` qua đúng hàm đã code** (chưa test qua chính hàm, mới test tay từng bước riêng lẻ). Lần thử `eng.goto_stage(38, hard=False)` gặp lỗi `go_main()` không thoát được khỏi `S_STAGECLEAR` (gọi `tap_el("SC_btn3")` 6 lần đều không đổi cảnh), trong khi gọi `eng.el("SC_btn3")` độc lập ngay sau đó lại đúng (toạ độ `(694,831)`, text "Main Menu", `shown=True inview=True`). Chưa rõ nguyên nhân — nghi do đúng lúc đó màn vừa có hiệu ứng/popup che tạm (ngay sau 1 lần bấm nhầm vào trận 123 trước đó), không phải lỗi logic rõ ràng trong `tap_el`/`go_main`. **Việc cần làm: thử lại `goto_stage(n, hard=False)` ở vài màn Thường bình thường (người dùng đã đồng ý "cứ thử ở các bài thường xem nhé"), xem có lặp lại lỗi không; nếu lặp lại, thêm `time.sleep` ngắn trước lần bấm đầu trong `go_main()` hoặc tăng retry/timeout.**
2. Chưa bắt đầu: thiết kế lại `StageStepDialog` trong `gui_app.py` — 3 mode rõ ràng (đã có code (1) auto_play_stage hiện tại, (2) watch_and_play, (3) run_fixed_stage), dropdown Khó/Thường (mặc định Thường) + ô nhập số màn (không dropdown) + ô số lần, nhớ lựa chọn lần trước (file nhỏ cạnh exe, kiểu `last_login.json`). Đồng bộ lại mặc định interval/repeat/gap trong form theo giá trị mới của `auto_play_stage`.
3. Chưa làm: build lại exe + test.
4. Chưa làm: fix nhận diện `com.android.vending`/Play Store deep-link giữa quảng cáo (mục TODO riêng trên).

Script debug cũ dùng sai cách gọi `engine.Engine()` (thiếu `cfg`, `log`) — xem cách gọi đúng trong `gui_app.py`/`ad_autoplayer.py` (dùng `a.load_config()` rồi `Engine(cfg, log_fn)` hoặc tương đương) trước khi viết lại script test mới.
