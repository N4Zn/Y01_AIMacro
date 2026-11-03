"""Lõi chạy tự động cho giao diện: đọc cấu trúc game qua DevTools, tự điều hướng, cuộn, xem quảng cáo.

Game dựng giao diện bằng DOM (viewport 1067x600 CSS px, devicePixelRatio 1.5 => màn adb 1600x900) nên:
  - vị trí nút lấy từ getBoundingClientRect, không dùng toạ độ cố định;
  - nút nằm ngoài viewport (thẻ Shop bên phải/trái) => biết cần cuộn hướng nào;
  - hạn mức từng mục đọc từ REWARD_AD.place_cfg.
Chỉ ĐỌC trạng thái game; mọi thao tác là chạm/vuốt qua adb.
"""
import json
import random
import time

import ad_autoplayer as a
import library
import shop_ads

# Thao tác trong màn chơi (S_GAME):
#   - Nhân vật 1-5: Android KEYCODE_1..5 (8..12), webview tự dịch đúng như phím số thật (xác nhận hoạt động).
#   - Thiên thạch (Meteor): KeyDefine.down = JS keyCode 40 (ArrowDown) -> Android KEYCODE_DPAD_DOWN (20),
#     đọc trực tiếp từ hàm S_GAME.keyDown của game (xác nhận qua mã nguồn, chưa có người dùng báo hỏng).
#   - Tên lửa (Missile) và Khoáng (Mineral): KHÔNG phải phím (ban đầu đoán nhầm bằng mã phím TV-remote,
#     dùng sai, người dùng báo không có tác dụng) — đọc lại qua DOM thật: đây là 2 NÚT TRÊN MÀN HÌNH nằm
#     cạnh nhau trong thanh điều khiển dưới cùng (`game_bottom_ui_missile`, `game_bottom_ui_mineral`),
#     toạ độ cố định, đã xác nhận bằng `el()` ngay trong trận thật. Toạ độ dưới đây lấy dự phòng khi không
#     đọc được DOM (vd network chậm) — `auto_play_stage` ưu tiên đọc `el()` trước, chỉ dùng số cố định này
#     nếu đọc thất bại.
STAGE_CHAR_KEYCODE = {str(i): 7 + i for i in range(1, 6)}     # "1".."5" -> KEYCODE_1..5 (8..12)
STAGE_METEOR_KEYCODE = 20          # KEYCODE_DPAD_DOWN (xác nhận qua KeyDefine.down)
STAGE_MISSILE_XY = (185, 791)      # dự phòng — ưu tiên đọc el("game_bottom_ui_missile")
STAGE_MINERAL_XY = (394, 791)      # dự phòng — ưu tiên đọc el("game_bottom_ui_mineral")

MAIN = "S_MAINMENU"
SHOP = "S_PACKAGE_STORE"

# Cách quay về màn trước, từng màn một, tới khi về menu chính. ("id", phần tử) hoặc ("css", x, y)
BACK = {
    "S_PACKAGE_STORE": ("css", 35, 33),
    "S_STAGECLEAR": ("id", "SC_btn3"),       # nút "Main Menu" — dùng id (động), KHÔNG dùng toạ độ cố định:
    # đã thử toạ độ cố định 1 lần, bố cục đổi theo màn khiến bấm trúng chỗ khác, vô tình vào nhầm 1 trận
    "S_SELECTEVENT": ("id", "SE_back_btn"),
    "S_MARBLE": ("id", "EM_btn1"),
    "S_JACKPOT_GACHA": ("id", "JG_back_btn"),
}

# Hạng mục. route = các bước từ menu chính: (id phần tử cần chạm, màn hình mong đợi sau khi chạm)
CATEGORIES = {
    "mainmenu": {"label": "Menu chính", "scene": MAIN, "route": [], "place": "mainmenu",
                 "button": "MM_ad_btn", "items": {"mainmenu": "Ruby ×30 (nút ngoài màn hình)"}},
    "shop": {"label": "Shop › Quảng cáo", "scene": SHOP, "route": [("MM_menu4", SHOP)], "place": "shop_ad",
             "items": {}},      # mục lấy động từ REWARD_AD.place_cfg.shop_ad.limits
    "marble": {"label": "Sự kiện › EldoMarble", "scene": "S_MARBLE", "place": "marble", "button": "EM_btn3",
               "route": [("AE_main_icon", "S_SELECTEVENT"), ("SE_event_btn2", "S_MARBLE")],
               "items": {"marble": "Thêm xúc xắc"}},
    "jackpot": {"label": "Sự kiện › Jackpot Draw", "scene": "S_JACKPOT_GACHA", "place": "jackpot",
                "button": "JG_ad_btn",
                "route": [("AE_main_icon", "S_SELECTEVENT"), ("SE_event_btn3", "S_JACKPOT_GACHA")],
                "items": {"jackpot": "Thêm lượt quay"}},
    "cloud_garden": {"label": "Cloud Garden", "scene": "S_RANKING_CLOUD_GARDEN", "place": "cloud_garden",
                     "button": "RCG_ad_btn",
                     "route": [("MM_menu7", "S_MODE_SELECT"), ("SWIPE:right", None),
                               ("MOS_card_div_6", "S_RANKING_CLOUD_GARDEN")],
                     "items": {"cloud_garden": "Thêm mây (xem ngay khi vào, không cần chơi xong)"}},
}
SHOP_LABELS = {"gold": "Gold ×1.000.000", "ruby": "Ruby ×30", "cloud": "Cloud Piece", "cel_essence":
               "Celestial Essence", "day_ticket": "Vé Daily Dungeon", "garden_ticket": "Vé Cloud Garden",
               "pvp_ticket": "Vé PVP", "boss_ticket": "Vé World Boss"}
# vị trí quảng cáo game có nhưng tool chưa biết đường tới (chỉ hiển thị hạn mức)
UNSUPPORTED = {"stageselect": "Chọn màn", "stageclear": "Kết thúc màn (xem bằng tuỳ chọn tự chơi màn)",
               "four_gods": "Tứ thần (xem bằng nút riêng)", "attendance": "Điểm danh", "attend_x2": "Điểm danh ×2",
               "guild_donate": "Quyên góp bang hội", "guild_boss_result": "Boss bang hội",
               "boss_result": "Boss", "gacha_complete": "Gacha", "board_buff": "Buff bảng"}


class NavError(Exception):
    pass


class Stopped(Exception):
    pass


EL_JS = """(function(id){var e=document.getElementById(id); if(!e) return null;
 var r=e.getBoundingClientRect(), d=devicePixelRatio, cs=getComputedStyle(e);
 var cx=r.left+r.width/2, cy=r.top+r.height/2;      // "trong khung nhìn" xét theo TÂM nút, không phải
 return JSON.stringify({x:Math.round(cx*d), y:Math.round(cy*d),                  // cả hộp — nút to (vd
  shown:r.width>0&&r.height>0&&cs.display!=='none'&&cs.visibility!=='hidden',    // GAME START) có thể rộng
  inview:cx>=0&&cx<=innerWidth&&cy>=0&&cy<=innerHeight,                         // hơn viewport mà vẫn bấm được
  vw:Math.round(innerWidth*d), dpr:d});})(%s)"""

TEXT_JS = """(function(id){var e=document.getElementById(id); return e ? JSON.stringify(e.textContent.trim()) : null;})(%s)"""

FIND_AD_JS = """JSON.stringify((function(){var found=null;
 Object.keys(REWARD_AD.btn_list).forEach(function(id){
   if(found) return;
   var el=document.getElementById(id); if(!el) return;
   var r=el.getBoundingClientRect(); if(r.width<=0||r.height<=0) return;
   var cs=getComputedStyle(el); if(cs.visibility==='hidden'||cs.display==='none') return;
   var b=REWARD_AD.btn_list[id], cfg=REWARD_AD.place_cfg[b.place];
   if(!cfg||!cfg.on) return;
   var used = (typeof cfg.used==='object'&&cfg.used!==null) ? (cfg.used[b.sub]||0) : cfg.used;
   var limit = (typeof cfg.limits==='object'&&cfg.limits!==null) ? (cfg.limits[b.sub]||0) : cfg.limit;
   if(used>=limit) return;
   var d=devicePixelRatio;
   found={id:id, place:b.place, sub:b.sub||null, used:used, limit:limit,
          x:Math.round((r.left+r.width/2)*d), y:Math.round((r.top+r.height/2)*d)};
 });
 return found;})())"""

SNAP_JS = """JSON.stringify((function(){var o={scene:g_sceneinfo.cur_scene,places:{}};
 var pc=REWARD_AD.place_cfg;
 for (var k in pc){var v=pc[k]; if(typeof v.used==='object'&&v.used!==null){
    o.places[k]={on:v.on,used:v.used,limits:v.limits||null,limit:v.limit};}
  else o.places[k]={on:v.on,used:v.used,limit:v.limit};}
 o.shop_day={total:pc.shop_ad.day_total,used:pc.shop_ad.day_used};
 return o;})())"""


class Engine:
    def __init__(self, cfg, log, should_stop=lambda: False):
        self.cfg, self.log, self.stopped = cfg, log, should_stop
        self.adb = a.Adb(cfg)
        self.tpls = a.load_templates()
        self.lib = library.AdLibrary(root=a.APP_DIR / "library", log=log)
        self.dpr = 1.5

    # ---- đọc game
    def js(self, expr):
        return a.cdp_eval(self.adb, self.cfg, expr)

    def scene(self):
        return a.game_scene(self.adb, self.cfg)

    def snapshot(self):
        v = self.js(SNAP_JS)
        return json.loads(v) if v else None

    def el(self, eid):
        v = self.js(EL_JS % json.dumps(eid))
        if not v:
            return None
        d = json.loads(v)
        self.dpr = d["dpr"]
        return d

    def text(self, eid):
        v = self.js(TEXT_JS % json.dumps(eid))
        return json.loads(v) if v else None

    def game_account(self, tries=3, wait_sec=2.0):
        """Tên tài khoản game hiển thị ở menu chính (Txt_MM_top_name) — dùng để khoá phiên server
        (SERVER_DESIGN.md mục 4: khoá theo tài khoản game, không theo máy). None nếu không đọc được.
        Thử lại vài lần: lúc chuyển tài khoản (vd Android <-> tivi) màn hình có đoạn "Connecting
        account..." mà tên chưa kịp cập nhật, đọc trúng lúc đó sẽ ra rỗng dù không phải lỗi thật."""
        for i in range(tries):
            if self.scene() != MAIN:
                try:
                    self.go_main()
                except NavError:
                    pass
            name = self.text("Txt_MM_top_name")
            if name:
                return name
            if i < tries - 1:
                self.log(f"  chưa đọc được tên tài khoản (lần {i + 1}/{tries}, có thể đang 'Connecting "
                         f"account...'), thử lại sau {wait_sec:.0f}s")
                time.sleep(wait_sec)
        return None

    def find_visible_ad(self):
        """Quét màn hiện tại tìm 1 nút quảng cáo GAME BIẾT (REWARD_AD.btn_list) đang hiện + còn hạn mức —
        tổng quát cho mọi vị trí (kết quả màn thường/Cloud Garden/boss…), không cần biết trước id.
        Trả về {id, place, sub, used, limit, x, y} hoặc None."""
        v = self.js(FIND_AD_JS)
        return json.loads(v) if v and v != "null" else None

    def quota(self, cat, key):
        """(used, limit) của 1 mục; None nếu không đọc được hoặc game tắt mục này."""
        snap = self.snapshot()
        if not snap:
            return None
        p = snap["places"].get(cat["place"])
        if not p or not p.get("on"):
            return None
        if cat["place"] == "shop_ad":
            return p["used"].get(key, 0), (p["limits"] or {}).get(key, 0)
        return p["used"], p["limit"]

    def list_items(self):
        """Hạng mục + mục + hạn mức hiện tại, để giao diện hiển thị. None nếu không đọc được game."""
        snap = self.snapshot()
        if not snap:
            return None
        out = []
        for cid, cat in CATEGORIES.items():
            p = snap["places"].get(cat["place"])
            if not p or not p.get("on"):
                continue
            if cid == "shop":
                items = {k: (SHOP_LABELS.get(k, k), p["used"].get(k, 0), lim)
                         for k, lim in (p["limits"] or {}).items() if lim > 0}
            else:
                k, label = next(iter(cat["items"].items()))
                items = {k: (label, p["used"], p["limit"])}
            if items:
                out.append((cid, cat["label"], items))
        extra = [(UNSUPPORTED[k], p["used"] if not isinstance(p["used"], dict) else sum(p["used"].values()),
                  p["limit"]) for k, p in snap["places"].items() if k in UNSUPPORTED and p.get("on") and
                 (p.get("limit") or 0) > 0]
        return snap["scene"], out, extra

    # ---- thao tác
    def tap_css(self, x, y):
        self.adb.tap(x * self.dpr, y * self.dpr)

    def wait_scene(self, scene, timeout=8):
        t0 = time.time()
        while time.time() - t0 < timeout:
            self._check_stop()
            if self.scene() == scene:
                return True
            time.sleep(0.5)
        return False

    def tap_el(self, eid, timeout=6):
        t0 = time.time()
        while time.time() - t0 < timeout:
            self._check_stop()
            e = self.el(eid)
            if e and e["shown"] and e["inview"]:
                self.adb.tap(e["x"], e["y"])
                return True
            time.sleep(0.5)
        return False

    def _check_stop(self):
        if self.stopped():
            raise Stopped()

    def go_main(self):
        for _ in range(6):
            self._check_stop()
            s = self.scene()
            if s == MAIN:
                return
            how = BACK.get(s)
            if how:
                self.log(f"  quay về menu chính (đang ở {s})")
                if how[0] == "id":
                    if not self.tap_el(how[1]):
                        raise NavError(f"không thấy nút quay lại ({how[1]}) ở {s}")
                else:
                    self.tap_css(how[1], how[2])
            elif self.tap_el("Img_MM_top_back", timeout=1):
                # dự phòng chung: nhiều màn dùng chung nút back này (vd S_MAKETEAM, S_CLEVELUP) —
                # không có trong BACK vì chưa xác nhận hết mọi màn dùng đúng id này
                self.log(f"  quay về menu chính (đang ở {s}, dùng nút back chung)")
            else:
                raise NavError(f"đang ở màn '{s}', tool chưa biết cách thoát — hãy tự về menu chính")
            time.sleep(2.0)
        raise NavError("không về được menu chính (có thể có popup che màn hình)")

    def ensure_in(self, cid):
        cat = CATEGORIES[cid]
        s = self.scene()
        if s is None:
            raise NavError("không đọc được trạng thái game (game đã tắt/chưa bật debug WebView?)")
        if s != cat["scene"]:
            self.go_main()
            for eid, expect in cat["route"]:
                self._check_stop()
                if eid.startswith("SWIPE:"):
                    direction = eid.split(":", 1)[1]
                    self.log(f"  cuộn {direction}")
                    x0, x1 = (1300, 300) if direction == "right" else (300, 1300)
                    self.adb._run("shell", f"input swipe {x0} 450 {x1} 450 600")
                    time.sleep(1.2)
                    continue
                self.log(f"  mở {eid} → {expect}")
                if not self.tap_el(eid) or not self.wait_scene(expect):
                    raise NavError(f"không vào được {expect} (có thể có popup che màn hình)")
                time.sleep(1.0)
        if cid == "shop":
            self.ensure_ad_tab()

    def shop_btn_ids(self):
        v = self.js("JSON.stringify(Object.keys(REWARD_AD.btn_list).filter(function(k){var b=REWARD_AD.btn_list[k];"
                    "return b.place==='shop_ad';}).map(function(k){return [k,REWARD_AD.btn_list[k].sub];}))")
        return dict((sub, k) for k, sub in json.loads(v)) if v else {}

    def ensure_ad_tab(self):
        ids = self.shop_btn_ids()
        if any((self.el(i) or {}).get("shown") for i in ids.values()):
            return
        self.log("  chọn tab Quảng cáo")
        if not self.tap_el("Img_MS_basic_bg_8"):
            raise NavError("không thấy tab Quảng cáo")
        time.sleep(1.5)

    def locate(self, cid, key):
        """Toạ độ nút xem quảng cáo của mục, tự cuộn trái/phải nếu nút ngoài màn hình. None nếu không có."""
        cat = CATEGORIES[cid]
        eid = self.shop_btn_ids().get(key) if cid == "shop" else cat["button"]
        if not eid:
            return None
        for _ in range(8):
            self._check_stop()
            e = self.el(eid)
            if not e or not e["shown"]:
                return None
            if e["inview"]:
                return e
            dist = int(min(max(abs(e["x"] - e["vw"] / 2), 250), 1000))
            if e["x"] > e["vw"] / 2:                       # nút bên phải -> vuốt sang trái
                x0, x1 = 1300, 1300 - dist
            else:
                x0, x1 = 300, 300 + dist
            self.log(f"  cuộn {'phải' if e['x'] > e['vw'] / 2 else 'trái'} để tìm {key}")
            self.adb._run("shell", f"input swipe {x0} 450 {x1} 450 600")
            time.sleep(1.2)
        return None

    # ---- chạy
    def run(self, plan):
        """plan: [(cid, key, số lượt)]. Trả về (tổng số quảng cáo đã xem, [{"category","item","requested","done"}])."""
        total, results = 0, []
        try:
            for cid, key, count in plan:
                done = self._run_item(cid, key, count)
                total += done
                results.append({"category": cid, "item": key, "requested": count, "done": done})
        except Stopped:
            self.log("■ Đã dừng theo yêu cầu")
        self.log(f"Kết thúc. Đã xem {total} quảng cáo.")
        return total, results

    def _run_item(self, cid, key, count):
        cat = CATEGORIES[cid]
        label = SHOP_LABELS.get(key, key) if cid == "shop" else cat["items"][key]
        self.log(f"▶ {cat['label']} › {label} (tối đa {count} lượt)")
        done = miss = 0
        while done < count:
            self._check_stop()
            q = self.quota(cat, key)
            if q is None:
                self.log(f"  không đọc được hạn mức hoặc mục đang tắt, bỏ qua {label}")
                break
            used, limit = q
            if used >= limit:
                self.log(f"  {label}: đã đủ hạn mức {used}/{limit}")
                break
            try:
                self.ensure_in(cid)
                btn = self.locate(cid, key)
            except NavError as e:
                self.log(f"  ⚠ {e}")
                break
            if not btn:
                self.log(f"  ⚠ không thấy nút xem quảng cáo của {label}, bỏ qua")
                break
            if done:
                time.sleep(random.uniform(1.0, 4.0))
            self.log(f"  {label}: {used}/{limit} → bấm nút xem quảng cáo")
            self.adb.tap(btn["x"], btn["y"])
            ok = shop_ads.watch_ad(self.adb, self.cfg, self.tpls, self.lib, should_stop=self.stopped)
            self._check_stop()
            if not ok:
                miss += 1
                self.log(f"  ⚠ không thấy quảng cáo mở ({miss}/3)")
                if miss >= 3 or self.adb.focus()[0] != self.cfg["game_package"]:
                    self.log("  dừng mục này")
                    break
                time.sleep(2)
                continue
            a.pause(self.cfg, 1.5)
            q2 = self.quota(cat, key)
            if q2 and q2[0] <= used:
                self.log(f"  ⚠ đã xem xong nhưng hạn mức không tăng ({q2[0]}/{q2[1]}), dừng mục này")
                break
            done, miss = done + 1, 0
        self.log(f"  ✓ {label}: xem {done} lượt")
        return done

    # ---- tự chơi màn (gọi nhân vật/tên lửa/khoáng/thiên thạch lặp lại tới khi hết màn)
    def auto_play_stage(self, chars="12345", missile=True, mineral=False, meteor=False,
                        interval=1.0, repeat=1, gap=0.05, max_sec=3600, wait_entry_sec=60,
                        watch_result_ad=True):
        """Tool không tự chọn màn/đội — chờ tới wait_entry_sec giây để BẠN tự vào màn chơi (S_GAME),
        rồi mới gọi lặp. Dừng khi màn kết thúc (cur_scene đổi), should_stop(), hoặc hết max_sec.
        Trả về số lượt đã gọi."""
        try:
            return self._auto_play_stage_impl(chars, missile, mineral, meteor, interval, repeat, gap,
                                              max_sec, wait_entry_sec, watch_result_ad)
        except Stopped:
            self.log("  ■ đã dừng theo yêu cầu")
            return 0

    def _auto_play_stage_impl(self, chars, missile, mineral, meteor, interval, repeat, gap,
                              max_sec, wait_entry_sec, watch_result_ad):
        start_scene = self.scene()
        if start_scene != "S_GAME":
            self.log(f"  đang ở '{start_scene}' — tự vào màn chơi trong {wait_entry_sec:.0f}s để bắt đầu…")
            t_wait = time.time()
            while time.time() - t_wait < wait_entry_sec:
                self._check_stop()
                start_scene = self.scene()
                if start_scene == "S_GAME":
                    self.log("  ✓ đã vào màn chơi")
                    break
                time.sleep(1.0)
            else:
                self.log("  ⚠ hết thời gian chờ, chưa vào màn chơi — bỏ qua bước này")
                return 0
        # Thứ tự theo yêu cầu người dùng: Nhân vật (đúng thứ tự đã chọn) trước -> Khoáng -> Tên lửa -> Thiên thạch
        steps = []
        for c in chars:
            if c in STAGE_CHAR_KEYCODE:
                steps += [("key", STAGE_CHAR_KEYCODE[c])] * repeat
        if mineral:
            e = self.el("game_bottom_ui_mineral")               # đọc toạ độ thật trong trận, có dự phòng
            steps.append(("tap", (e["x"], e["y"]) if e and e["shown"] else STAGE_MINERAL_XY))
        if missile:
            e = self.el("game_bottom_ui_missile")
            steps.append(("tap", (e["x"], e["y"]) if e and e["shown"] else STAGE_MISSILE_XY))
        if meteor:
            steps.append(("key", STAGE_METEOR_KEYCODE))
        if not steps:
            self.log("  ⚠ chưa chọn thao tác nào (tên lửa/khoáng/thiên thạch/nhân vật)")
            return 0
        cmd = f"; sleep {gap}; ".join(
            f"input tap {xy[0]} {xy[1]}" if kind == "tap" else f"input keyevent {xy}" for kind, xy in steps)
        self.log(f"  ▶ tự chơi màn: {cmd} mỗi {interval}s")
        t0, rounds, lost = time.time(), 0, 0
        while time.time() - t0 < max_sec:
            self._check_stop()
            loop_t0 = time.time()
            scene = self.scene()
            if scene is None:
                lost += 1
                if lost >= 3:
                    self.log("  mất đọc cur_scene 3 lần liên tiếp, dừng")
                    break
            else:
                lost = 0
                if scene != start_scene:
                    self.log(f"  đã chuyển sang {scene} (hết màn), dừng sau {rounds} lượt")
                    if watch_result_ad:
                        self._watch_any_result_ad()
                    break
                self.adb._run("shell", cmd)
                rounds += 1
                if rounds % 10 == 0:
                    self.log(f"  {rounds} lượt")
            time.sleep(max(0, interval - (time.time() - loop_t0)))
        else:
            self.log(f"  hết thời gian tối đa, dừng sau {rounds} lượt")
        return rounds

    # ---- Chơi liên tục theo thời gian: KHÔNG tự chuyển màn — bạn tự vào màn nào cũng được, mỗi lần tool
    # phát hiện (S_GAME) thì tự chơi tới khi màn đó kết thúc, rồi lại CHỜ bạn tự vào màn tiếp theo, lặp vậy
    # tới khi hết duration_sec hoặc bị dừng. Khác auto_play_stage (chỉ 1 lần) và farm_stages (tự điều hướng).
    def watch_and_play(self, duration_sec=3600, chars="12345", missile=True, mineral=False, meteor=False,
                       interval=1.0, repeat=1, gap=0.05, stage_max_sec=3600, wait_entry_sec=0,
                       watch_result_ad=True):
        """wait_entry_sec=0 (mặc định ở đây) nghĩa là chờ KHÔNG giới hạn cho mỗi lượt (chỉ `duration_sec`
        tổng mới có hạn) — phù hợp vì người dùng có thể chơi tay 1 lúc rồi mới vào màn tiếp."""
        try:
            return self._watch_and_play_impl(duration_sec, chars, missile, mineral, meteor, interval,
                                             repeat, gap, stage_max_sec, wait_entry_sec, watch_result_ad)
        except Stopped:
            self.log("  ■ đã dừng theo yêu cầu")
            return 0

    def _watch_and_play_impl(self, duration_sec, chars, missile, mineral, meteor, interval, repeat, gap,
                             stage_max_sec, wait_entry_sec, watch_result_ad):
        t0, done = time.time(), 0
        per_wait = wait_entry_sec if wait_entry_sec else max(1, duration_sec)
        while True:
            self._check_stop()
            left = duration_sec - (time.time() - t0)
            if left <= 0:
                break
            self.log(f"── Chơi liên tục: lượt {done + 1} (còn {left:.0f}s) ──")
            self.auto_play_stage(chars=chars, missile=missile, mineral=mineral, meteor=meteor,
                                 interval=interval, repeat=repeat, gap=gap,
                                 max_sec=min(stage_max_sec, max(1, left)),
                                 wait_entry_sec=min(per_wait, max(1, left)),
                                 watch_result_ad=watch_result_ad)
            done += 1
        self.log(f"  ✓ Chơi liên tục: xong {done} lượt trong {duration_sec:.0f}s")
        return done

    # ---- Tự cày nhiều màn liên tiếp: thắng xong tự bấm "Chọn bàn" (SC_btn5 trên S_STAGECLEAR) rồi bấm
    # ô màn kế tiếp (đang focus sẵn, `[id$="_stages_focus"]`) để vào thẳng trận tiếp theo, không cần chọn
    # lại đội. Chỉ đi tiếp khi màn trước THẮNG (về đúng S_STAGECLEAR) — thua/ra màn lạ thì dừng, không đoán.
    SC_BTN5_XY = (1119, 831)           # "Chọn bàn" trên S_STAGECLEAR, đường ngắn nhất lặp lại
    STAGE_FOCUS_JS = ("""JSON.stringify((function(){var e=document.querySelector('[id$="_stages_focus"]');"""
                      """ if(!e) return null; var r=e.getBoundingClientRect(), d=devicePixelRatio;"""
                      """ return {x:Math.round((r.left+r.width/2)*d), y:Math.round((r.top+r.height/2)*d)};"""
                      """})())""")

    def farm_stages(self, times=5, watch_ads=True, chars="12345", missile=True, mineral=False, meteor=False,
                    interval=2.0, repeat=2, gap=0.2, stage_max_sec=600, wait_entry_sec=60):
        """Tự lặp 'times' màn liên tiếp. Màn đầu chờ bạn tự vào (như auto_play_stage); từ màn 2 trở đi tự
        vào không cần bạn làm gì, miễn màn trước đó thắng. Trả về số màn đã hoàn thành."""
        try:
            return self._farm_stages_impl(times, watch_ads, chars, missile, mineral, meteor, interval,
                                          repeat, gap, stage_max_sec, wait_entry_sec)
        except Stopped:
            self.log("  ■ đã dừng theo yêu cầu")
            return 0

    def _farm_stages_impl(self, times, watch_ads, chars, missile, mineral, meteor, interval, repeat, gap,
                          stage_max_sec, wait_entry_sec):
        done = 0
        for n in range(1, times + 1):
            self._check_stop()
            self.log(f"── Tự cày: màn {n}/{times} ──")
            self.auto_play_stage(chars=chars, missile=missile, mineral=mineral, meteor=meteor,
                                 interval=interval, repeat=repeat, gap=gap, max_sec=stage_max_sec,
                                 wait_entry_sec=wait_entry_sec if n == 1 else 15, watch_result_ad=watch_ads)
            scene = self.scene()
            if scene != "S_STAGECLEAR":
                self.log(f"  ⚠ đang ở '{scene}' (không phải màn hình thắng) — dừng tự cày, có thể bạn "
                         f"vừa thua hoặc chưa vào màn")
                break
            done += 1
            if n == times:
                break
            self._check_stop()
            self.adb.tap(*self.SC_BTN5_XY)
            time.sleep(2.0)
            if self.scene() not in ("S_SELECTSTAGE_HARD", "S_SELECTSTAGE"):
                self.log(f"  ⚠ 'Chọn bàn' không vào được màn chọn số (đang ở {self.scene()}), dừng")
                break
            v = self.js(self.STAGE_FOCUS_JS)
            focus = json.loads(v) if v and v != "null" else None
            if not focus:
                self.log("  ⚠ không tìm thấy ô màn kế tiếp đang chọn sẵn, dừng")
                break
            self.adb.tap(focus["x"], focus["y"])
            time.sleep(2.0)
        self.log(f"  ✓ Tự cày màn: hoàn thành {done}/{times} màn")
        return done

    # ---- Lặp lại ĐÚNG 1 màn cố định (vd "màn 38 Thường"), theo số lần — khác farm_stages (tiến dần).
    # Cơ chế đã xác nhận bằng thao tác thật (không đoán): số_màn = (bản_đồ-1)*20 + ô_trong_bản_đồ (1..20).
    # Đường vào: menu chính -> GAME START (MM_menu7) -> S_MODE_SELECT -> thẻ Story Mode (MOS_card_div_1)
    # -> S_SELECTMAP (Thường) hoặc S_SELECTMAP_HARD (Khó), đổi qua lại bằng Img_SM_mode_bt -> cuộn
    # trái/phải (Img_SM(H)_leftarrow/rightarrow) tới khi thấy đúng bản đồ (SM(H)_map_N) -> bấm bản đồ đó
    # (vào thẳng lưới 20 ô, 1 tap = chọn+vào) -> bấm đúng ô (SS(H)_menuN, 1 tap = chọn+vào thẳng trận).
    def goto_stage(self, stage_num, hard=False):
        """Vào thẳng đúng số màn `stage_num` (ví dụ 115) ở chế độ Khó (hard=True) hoặc Thường (hard=False).
        Trả về True nếu vào được S_GAME, False/ném NavError nếu không. Không tự lùi khi lỗi — dừng tại chỗ
        để người dùng tự xử lý (tránh đoán sai càng bấm càng sai)."""
        try:
            return self._goto_stage_impl(stage_num, hard)
        except Stopped:
            self.log("  ■ đã dừng theo yêu cầu")
            return False

    def _goto_stage_impl(self, stage_num, hard):
        if stage_num < 1:
            self.log("  ⚠ số màn không hợp lệ")
            return False
        target_map = (stage_num - 1) // 20 + 1
        target_cell = (stage_num - 1) % 20 + 1
        map_scene = "S_SELECTMAP_HARD" if hard else "S_SELECTMAP"
        stage_scene = "S_SELECTSTAGE_HARD" if hard else "S_SELECTSTAGE"
        map_prefix = "SMH" if hard else "SM"
        stage_prefix = "SSH" if hard else "SS"
        mode_label = "Khó" if hard else "Thường"

        self.go_main()
        if not self.tap_el("MM_menu7") or not self.wait_scene("S_MODE_SELECT"):
            raise NavError("không vào được Mode Select (GAME START)")
        time.sleep(1.0)
        if not self.tap_el("MOS_card_div_1"):
            raise NavError("không bấm được thẻ Story Mode")
        time.sleep(1.5)
        scene = self.scene()
        if scene not in ("S_SELECTMAP", "S_SELECTMAP_HARD"):
            raise NavError(f"Story Mode không vào màn chọn bản đồ (đang ở {scene})")
        if scene != map_scene:
            self.log(f"  chuyển chế độ sang {mode_label}")
            if not self.tap_el("Img_SM_mode_bt") or not self.wait_scene(map_scene):
                raise NavError(f"không chuyển được sang {mode_label}")
            time.sleep(1.0)

        for _ in range(8):                                 # cuộn tới trang có bản đồ target_map (5/trang)
            self._check_stop()
            found = self.el(f"{map_prefix}_map_{target_map}")
            if found and found["shown"] and found["inview"]:
                break
            right = self.el(f"Img_{map_prefix}_rightarrow")
            left = self.el(f"Img_{map_prefix}_leftarrow")
            if right and right["shown"]:
                self.adb.tap(right["x"], right["y"])
            elif left and left["shown"]:
                self.adb.tap(left["x"], left["y"])
            else:
                raise NavError(f"không tìm thấy bản đồ {target_map} (có thể chưa mở khoá)")
            time.sleep(1.2)
        else:
            raise NavError(f"cuộn quá nhiều lần vẫn không thấy bản đồ {target_map}")

        e = self.el(f"{map_prefix}_map_{target_map}")
        if not e or not e["shown"]:
            raise NavError(f"bản đồ {target_map} chưa mở khoá hoặc không tồn tại")
        self.adb.tap(e["x"], e["y"])
        if not self.wait_scene(stage_scene):
            raise NavError(f"bấm bản đồ {target_map} không vào được lưới chọn màn")
        time.sleep(1.0)

        cell = self.el(f"{stage_prefix}_menu{target_cell}")
        if not cell or not cell["shown"]:
            raise NavError(f"ô màn {target_cell} trong bản đồ {target_map} chưa mở khoá hoặc không tồn tại")
        self.adb.tap(cell["x"], cell["y"])
        if not self.wait_scene("S_GAME"):
            raise NavError(f"bấm ô màn {stage_num} không vào được trận")
        time.sleep(1.0)
        self.log(f"  ✓ đã vào màn {stage_num} ({mode_label})")
        return True

    def run_fixed_stage(self, stage_num, hard=False, times=1, watch_ads=True, chars="12345", missile=True,
                        mineral=False, meteor=False, interval=1.0, repeat=1, gap=0.05, stage_max_sec=600):
        """Lặp lại ĐÚNG màn `stage_num` (không tiến dần) 'times' lần. Trả về số lượt hoàn thành."""
        try:
            return self._run_fixed_stage_impl(stage_num, hard, times, watch_ads, chars, missile, mineral,
                                              meteor, interval, repeat, gap, stage_max_sec)
        except Stopped:
            self.log("  ■ đã dừng theo yêu cầu")
            return 0

    def _run_fixed_stage_impl(self, stage_num, hard, times, watch_ads, chars, missile, mineral, meteor,
                              interval, repeat, gap, stage_max_sec):
        done = 0
        for n in range(1, times + 1):
            self._check_stop()
            self.log(f"── Lặp màn {stage_num} ({'Khó' if hard else 'Thường'}): lượt {n}/{times} ──")
            try:
                ok = self.goto_stage(stage_num, hard=hard)
            except NavError as e:
                self.log(f"  ⚠ {e}")
                break
            if not ok:
                break
            self.auto_play_stage(chars=chars, missile=missile, mineral=mineral, meteor=meteor,
                                 interval=interval, repeat=repeat, gap=gap, max_sec=stage_max_sec,
                                 wait_entry_sec=1, watch_result_ad=watch_ads)
            if self.scene() != "S_STAGECLEAR":
                self.log(f"  ⚠ đang ở '{self.scene()}' (không phải màn thắng) — dừng lặp")
                break
            done += 1
        self.log(f"  ✓ Lặp màn {stage_num}: hoàn thành {done}/{times} lượt")
        return done

    # ---- Tứ thần (mỗi vị thần đã mở khoá có 1 quảng cáo/ngày riêng — dùng chung find_visible_ad())
    FOUR_GODS_SLOTS = ["FG_select_box_1", "FG_select_box_2", "FG_select_box_3", "FG_select_box_4"]

    def ensure_in_four_gods(self):
        if self.scene() != "S_FOUR_GODS":
            self.go_main()
            if not self.tap_el("BD_main_button") or not self.wait_scene("S_FOUR_GODS"):
                raise NavError("không vào được Tứ thần (nút 'Đền' ở menu chính)")
            time.sleep(1.0)

    def run_four_gods(self):
        """Vào từng vị thần đã mở khoá, xem quảng cáo nếu màn đó đang hiện nút (dùng find_visible_ad)."""
        try:
            return self._run_four_gods_impl()
        except Stopped:
            self.log("  ■ đã dừng theo yêu cầu")
            return 0

    def _run_four_gods_impl(self):
        done = 0
        try:
            self.ensure_in_four_gods()
        except NavError as e:
            self.log(f"  ⚠ {e}")
            return 0
        for slot in self.FOUR_GODS_SLOTS:
            self._check_stop()
            e = self.el(slot)
            if not e or not e["shown"]:
                continue
            # không đoán trạng thái khoá qua FG_select_lock_N nữa (tên gây hiểu nhầm — không phản ánh đúng
            # khoá/mở thật trong game, đã xác nhận qua ảnh chụp màn hình thật: cả 4 thẻ đều không có biểu
            # tượng khoá). Cứ bấm thử; nếu thần thật sự chưa chơi được thì màn sẽ không đổi (xử lý ở dưới).
            self.adb.tap(e["x"], e["y"])
            time.sleep(2.0)
            scene = self.scene()
            if scene and scene != "S_FOUR_GODS":
                found = self.find_visible_ad()
                if found and found["place"] == "four_gods":
                    self.log(f"  {scene}: xem QC tứ thần ({found['used']}/{found['limit']})")
                    self.adb.tap(found["x"], found["y"])
                    shop_ads.watch_ad(self.adb, self.cfg, self.tpls, self.lib, should_stop=self.stopped)
                    done += 1
                else:
                    self.log(f"  {scene}: đã xem hôm nay hoặc không có quảng cáo")
                # màn con mỗi vị thần (vd S_BLUE_DRAGON) không có nút lùi chung (Img_MM_top_back) nên
                # go_main() không tự thoát được — bấm thẳng nút lùi ở vị trí cố định (cùng layout cho
                # cả 4 vị thần, chỉ đổi hình/tên) trước, dự phòng mới đi vòng qua ensure_in_four_gods()
                self.adb.tap(519, 786)
                time.sleep(1.5)
            else:
                self.log(f"  {slot}: bấm nhưng màn không đổi (thần chưa chơi được hoặc chưa có trong đội)")
            if self.scene() != "S_FOUR_GODS":
                try:
                    self.ensure_in_four_gods()
                except NavError:
                    self.log("  ⚠ không quay lại được màn chọn thần, dừng")
                    break
        self.log(f"  ✓ Tứ thần: xem {done} quảng cáo")
        return done

    def _watch_any_result_ad(self, settle_sec=2.0, tries=3):
        """Sau khi màn kết thúc: chờ màn kết quả vẽ xong, quét 1 nút quảng cáo bất kỳ game đang cho xem
        (vd +2000% vàng sau màn thường, Cloud Garden, boss…) và xem nó nếu có + còn hạn mức."""
        for _ in range(tries):
            self._check_stop()
            time.sleep(settle_sec)
            found = self.find_visible_ad()
            if found:
                break
        else:
            return
        self.log(f"  tìm thấy quảng cáo kết quả: {found['place']}"
                 f"{('.' + found['sub']) if found['sub'] else ''} ({found['used']}/{found['limit']}) → xem")
        self.adb.tap(found["x"], found["y"])
        shop_ads.watch_ad(self.adb, self.cfg, self.tpls, self.lib, should_stop=self.stopped)
