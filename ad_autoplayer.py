#!/usr/bin/env python3
"""Tự động xem/đóng quảng cáo của 1 game chạy trong BlueStacks.

Chạy nền: chụp màn hình bằng `adb exec-out screencap`, tìm nút đóng (X / tam giác skip)
bằng OpenCV, bấm bằng `adb shell input tap`. Không cần AI, không cần cửa sổ ở trên cùng.

  python ad_autoplayer.py run            # vòng lặp chính
  python ad_autoplayer.py shot           # lưu ảnh màn hình + activity hiện tại
  python ad_autoplayer.py find           # dò nút đóng trên màn hình hiện tại (không bấm)
  python ad_autoplayer.py learn close_a 1545 89   # cắt mẫu nút từ màn hình hiện tại
"""
import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

FROZEN = getattr(sys, "frozen", False)
HERE = Path(__file__).resolve().parent                              # mã + mẫu ảnh (đóng gói: thư mục _internal)
APP_DIR = Path(sys.executable).parent if FROZEN else HERE          # nơi ghi dữ liệu: config, library, logs, adb
TEMPLATE_DIR = HERE / "templates"
DEBUG_DIR = APP_DIR / "debug"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)                  # không nháy cửa sổ console khi gọi adb

BLUESTACKS_ADB = [r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe", r"C:\Program Files\BlueStacks\HD-Adb.exe",
                  r"C:\Program Files (x86)\BlueStacks_nxt\HD-Adb.exe", r"C:\Program Files (x86)\BlueStacks\HD-Adb.exe"]


def find_adb(configured=None):
    """adb đi kèm tool (adb/adb.exe) -> adb trong PATH -> HD-Adb.exe của BlueStacks -> adb trong Android SDK."""
    cands = [configured, APP_DIR / "adb" / "adb.exe", shutil.which("adb"), *BLUESTACKS_ADB,
             Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe"]
    for c in cands:
        if c and Path(c).exists():
            return str(c)
    raise RuntimeError("không tìm thấy adb (đặt adb.exe vào thư mục adb/ cạnh tool)")

DEFAULT_CONFIG = {
    "serial": "127.0.0.1:5555",
    "adb_path": None,                       # None = tìm trong PATH / Android SDK
    "game_package": "busidol.mobile.eldorado",
    # activity/package chứa 1 trong các chuỗi này => đang ở trong quảng cáo
    "ad_markers": [
        "com.google.android.gms.ads", "AdActivity", "com.applovin", "com.unity3d.ads",
        "com.unity3d.services", "com.ironsource", "com.vungle", "com.facebook.ads",
        "com.mbridge", "com.bytedance.sdk", "com.inmobi", "com.chartboost",
        "com.fyber", "com.adcolony", "com.startapp", "InterstitialActivity",
    ],
    "poll_sec": 0.5,
    "min_watch_sec": 3.0,                   # không bấm đóng trước mốc này
    "after_tap_sec": 1.0,
    "ad_timeout_sec": 90.0,                 # quá lâu chưa đóng được => bấm BACK
    "max_taps_per_spot": 2,                 # 1 điểm bấm >N lần trong 1 quảng cáo mà không đổi => bỏ qua
    "trigger_xy": None,                     # [x, y] nút "xem quảng cáo" trong game (hoặc dùng templates/trigger_*.png)
    "trigger_cooldown_sec": 30.0,           # bấm nút xem QC mà quảng cáo chưa mở thì đợi chừng này rồi bấm lại (bỏ qua khi vừa xong 1 quảng cáo)
    "template_scales": [1.0],               # ảnh adb luôn đúng độ phân giải; thêm 0.85/1.2 nếu mẫu cắt từ ảnh khác
    "post_ad_wait_sec": 2.0,
    "corner_zone": [0.22, 0.28],            # [rộng, cao] vùng góc tìm nút đóng (tỉ lệ màn hình)
    "generic_threshold": 0.70,
    "generic_bottom_threshold": 0.85,       # góc dưới hay dính logo Play/App Store => khắt khe hơn
    "generic_kinds": ["x", "skip"],         # thêm "tri" (▶ trơn) nếu cần, dễ nhận nhầm nút play
    "template_threshold": 0.80,
    "debug": False,
    # giả lập thao tác người: lệch toạ độ bấm và thời gian chờ ngẫu nhiên
    "tap_jitter_px": 6,                     # toạ độ bấm lệch ngẫu nhiên ±N px (0 = tắt)
    "pre_tap_delay": [0.08, 0.35],          # chờ ngẫu nhiên [min, max] giây ngay trước mỗi lần bấm
    "delay_jitter": 0.35,                   # mọi lần chờ sau bấm/giữa lượt lệch ngẫu nhiên ±35%
    "server_url": "http://127.0.0.1:8000",  # server license/telemetry (server/) — đổi khi triển khai thật
}


def pause(cfg, sec):
    """Ngủ `sec` giây lệch ngẫu nhiên ±delay_jitter (tránh nhịp đều như máy)."""
    j = cfg.get("delay_jitter", 0)
    time.sleep(max(0.0, sec * random.uniform(1 - j, 1 + j)))


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    p = APP_DIR / "config.json"
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8-sig")))
    return cfg


# --------------------------------------------------------------------------- adb

class Adb:
    def __init__(self, cfg):
        self.serial = cfg["serial"]
        self.path = find_adb(cfg["adb_path"])
        self.jitter = cfg.get("tap_jitter_px", 0)
        self.pre_delay = cfg.get("pre_tap_delay") or [0, 0]

    def _run(self, *args, timeout=20):
        return subprocess.run([self.path, "-s", self.serial, *args],
                              capture_output=True, timeout=timeout, creationflags=NOWIN).stdout

    def connect(self):
        subprocess.run([self.path, "connect", self.serial], capture_output=True, timeout=20,
                       creationflags=NOWIN)

    def devices(self):
        """Danh sách serial adb đang ở trạng thái `device`."""
        out = subprocess.run([self.path, "devices"], capture_output=True, timeout=20,
                             creationflags=NOWIN).stdout.decode("utf-8", "ignore")
        return [ln.split()[0] for ln in out.splitlines()[1:] if ln.strip().endswith("device")]

    def scan_bluestacks(self, ports=range(5555, 5600, 10)):
        """BlueStacks mỗi phiên bản/instance dùng 1 cổng adb khác nhau: thử connect các cổng hay gặp."""
        for p in ports:
            subprocess.run([self.path, "connect", f"127.0.0.1:{p}"], capture_output=True, timeout=10,
                           creationflags=NOWIN)
        return self.devices()

    def screen(self):
        data = self._run("exec-out", "screencap", "-p")
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("screencap lỗi (adb connect chưa được?)")
        return img

    def focus(self):
        """(package, activity) đang có focus, hoặc (None, None) khi đang chuyển cảnh."""
        out = self._run("shell", "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'").decode(
            "utf-8", "ignore")
        m = re.search(r"mCurrentFocus=Window\{\S+ \S+ ([\w.]+)/([\w.$]+)\}", out) or \
            re.search(r"mFocusedApp=.*? ([\w.]+)/([\w.$]+)", out)
        return (m.group(1), m.group(2)) if m else (None, None)

    def tap(self, x, y):
        """Bấm lệch ngẫu nhiên ±jitter px và chờ ngẫu nhiên ngắn trước khi bấm."""
        time.sleep(random.uniform(*self.pre_delay))
        x = min(max(int(x + random.randint(-self.jitter, self.jitter)), 0), 1599)
        y = min(max(int(y + random.randint(-self.jitter, self.jitter)), 0), 899)
        self._run("shell", f"input tap {x} {y}")

    def back(self):
        self._run("shell", "input keyevent 4")

    def launch(self, package):
        self._run("shell", f"monkey -p {package} -c android.intent.category.LAUNCHER 1")


# ------------------------------------------------------------------- detection

def _canvas(size):
    return np.zeros((size, size), np.uint8)


def _draw_x(size, stroke):
    img, pad = _canvas(size), int(size * 0.22)
    cv2.line(img, (pad, pad), (size - pad, size - pad), 255, stroke, cv2.LINE_AA)
    cv2.line(img, (size - pad, pad), (pad, size - pad), 255, stroke, cv2.LINE_AA)
    return img


def _draw_skip(size):
    """▶| (skip)."""
    img, pad = _canvas(size), int(size * 0.2)
    bar = int(size * 0.74)
    tri = np.array([[pad, pad], [bar - 1, size // 2], [pad, size - pad]], np.int32)
    cv2.fillPoly(img, [tri], 255)
    cv2.rectangle(img, (bar, pad), (bar + max(2, size // 9), size - pad), 255, -1)
    return img


def _draw_tri(size):
    """▶ (tam giác đặc)."""
    img, pad = _canvas(size), int(size * 0.22)
    tri = np.array([[pad, pad], [size - pad, size // 2], [pad, size - pad]], np.int32)
    cv2.fillPoly(img, [tri], 255)
    return img


def _glyph_bank():
    bank = []
    for s in (18, 24, 30, 38, 48, 60):
        shapes = [("x", _draw_x(s, max(2, int(s * 0.09)))), ("x", _draw_x(s, max(3, int(s * 0.16)))),
                  ("skip", _draw_skip(s)), ("tri", _draw_tri(s))]
        for kind, g in shapes:
            bank.append((kind, g))
            bank.append((kind, 255 - g))      # cực tính ngược (glyph tối trên nền sáng)
    return bank


GLYPHS = _glyph_bank()


def load_templates():
    """templates/<prefix>_*.png -> {prefix: [(name, gray)]}. Prefix: close, tap, wait, trigger, popup."""
    out = {}
    for p in sorted(TEMPLATE_DIR.glob("*.png")):
        g = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if g is not None:
            out.setdefault(p.stem.split("_")[0], []).append((p.stem, g))
    return out


def match_library(gray, tpls, thr, scales=(1.0,)):
    """Dò mẫu do người dùng cắt. Trả [(score, cx, cy, name)]."""
    hits = []
    for name, t in tpls:
        for sc in scales:
            tt = cv2.resize(t, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA) if sc != 1.0 else t
            if tt.shape[0] >= gray.shape[0] or tt.shape[1] >= gray.shape[1] or min(tt.shape) < 8:
                continue
            res = cv2.matchTemplate(gray, tt, cv2.TM_CCOEFF_NORMED)
            _, mx, _, loc = cv2.minMaxLoc(res)
            if mx >= thr:
                hits.append((float(mx), loc[0] + tt.shape[1] // 2, loc[1] + tt.shape[0] // 2, name))
    return hits


def _content_box(gray):
    """Khung nội dung không tính viền đen (quảng cáo dọc nằm giữa màn hình ngang)."""
    cols = np.where(gray.mean(axis=0) > 14)[0]
    rows = np.where(gray.mean(axis=1) > 14)[0]
    if len(cols) == 0 or len(rows) == 0:
        return 0, 0, gray.shape[1], gray.shape[0]
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def corner_zones(gray, zone):
    h, w = gray.shape
    boxes = [(0, 0, w, h)]
    cx0, cy0, cx1, cy1 = _content_box(gray)
    if (cx1 - cx0) < 0.9 * w or (cy1 - cy0) < 0.9 * h:
        boxes.append((cx0, cy0, cx1, cy1))
    zones = []
    for x0, y0, x1, y1 in boxes:
        zw, zh = int((x1 - x0) * zone[0]), int((y1 - y0) * zone[1])
        zones += [(x0, y0, x0 + zw, y0 + zh), (x1 - zw, y0, x1, y0 + zh),
                  (x0, y1 - zh, x0 + zw, y1), (x1 - zw, y1 - zh, x1, y1)]
    return zones


def detect_generic(gray, cfg):
    """X / skip / tam giác ở các góc. Trả [(score, cx, cy, kind)] đã lọc trùng, điểm cao trước."""
    hits = []
    mid_y = gray.shape[0] / 2
    for x0, y0, x1, y1 in corner_zones(gray, cfg["corner_zone"]):
        roi = gray[y0:y1, x0:x1]
        thr = cfg["generic_bottom_threshold"] if y0 > mid_y else cfg["generic_threshold"]
        for kind, g in GLYPHS:
            if kind not in cfg["generic_kinds"]:
                continue
            if g.shape[0] >= roi.shape[0] or g.shape[1] >= roi.shape[1]:
                continue
            res = cv2.matchTemplate(roi, g, cv2.TM_CCOEFF_NORMED)
            _, mx, _, loc = cv2.minMaxLoc(res)
            if mx >= thr:
                hits.append((float(mx), x0 + loc[0] + g.shape[1] // 2, y0 + loc[1] + g.shape[0] // 2, kind))
    hits.sort(reverse=True)
    kept = []
    for h in hits:
        if all(abs(h[1] - k[1]) > 28 or abs(h[2] - k[2]) > 28 for k in kept):
            kept.append(h)
    return kept


def find_close(img, tpls, cfg):
    """Danh sách ứng viên nút đóng: mẫu người dùng ưu tiên hơn dò tổng quát."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cands = []
    for prefix in ("close", "tap"):
        for sc, x, y, name in match_library(gray, tpls.get(prefix, []), cfg["template_threshold"],
                                            cfg["template_scales"]):
            cands.append((sc + 1.0, x, y, name))          # +1: luôn xếp trên dò tổng quát
    cands += detect_generic(gray, cfg)
    cands.sort(reverse=True)
    return cands


class CloseTracker:
    """Chỉ cho bấm nút đóng khi nó còn ở NGUYÊN vị trí qua nhiều frame liên tiếp.

    Nút X/skip thật là lớp phủ tĩnh nên giữ chỗ; hình giống X trong video/hình quảng cáo thì
    biến mất, dịch chỗ hoặc đổi nội dung sau vài frame (từng nhận nhầm và mở Play Store)."""

    def __init__(self, frames=3, user_frames=2, move_px=14, patch_thr=25.0):
        self.frames, self.user_frames = frames, user_frames
        self.move_px, self.patch_thr = move_px, patch_thr
        self.tracks = []            # {x, y, name, count, patch}

    @staticmethod
    def _patch(gray, x, y, r=18):
        h, w = gray.shape
        x0, y0 = min(max(x - r, 0), w - 2 * r), min(max(y - r, 0), h - 2 * r)
        return gray[y0:y0 + 2 * r, x0:x0 + 2 * r].astype(np.int16)

    def update(self, img, cands):
        """Nạp 1 frame; trả về các ứng viên đã ổn định (cùng định dạng find_close)."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        new, stable = [], []
        for c in cands:
            sc, x, y, name = c
            patch = self._patch(gray, x, y)
            prev = next((t for t in self.tracks if t["name"] == name
                         and abs(t["x"] - x) <= self.move_px and abs(t["y"] - y) <= self.move_px), None)
            if prev and float(np.abs(patch - prev["patch"]).mean()) <= self.patch_thr:
                count = prev["count"] + 1
            else:
                count = 1
            new.append({"x": x, "y": y, "name": name, "count": count, "patch": patch})
            if count >= (self.user_frames if sc >= 1.0 else self.frames):
                stable.append(c)
        self.tracks = new           # ứng viên không xuất hiện ở frame này bị xoá => đếm lại từ đầu
        return stable


def annotate(img, cands, path):
    out = img.copy()
    for sc, x, y, name in cands:
        cv2.circle(out, (x, y), 26, (0, 255, 0), 2)
        cv2.putText(out, f"{name} {sc:.2f}", (x + 28, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    DEBUG_DIR.mkdir(exist_ok=True)
    cv2.imwrite(str(path), out)


# ------------------------------------------------------------------------ loop

def is_ad(pkg, act, cfg):
    text = f"{pkg}/{act}"
    return any(m in text for m in cfg["ad_markers"])


def tap_first(adb, img, tpls, prefix, cfg):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hits = sorted(match_library(gray, tpls.get(prefix, []), cfg["template_threshold"],
                                cfg["template_scales"]), reverse=True)
    if hits:
        _, x, y, name = hits[0]
        log(f"tap {name} @({x},{y})")
        adb.tap(x, y)
        return True
    return False


def run(cfg, max_ads, duration):
    import library
    lib, ses, last_img = library.AdLibrary(log=log), None, None
    adb = Adb(cfg)
    adb.connect()
    tpls = load_templates()
    game = cfg["game_package"]
    ads_done, start = 0, time.time()
    ad_start, taps, last_trigger, last_back = None, {}, 0.0, 0.0
    log(f"chạy: game={game} mẫu={ {k: len(v) for k, v in tpls.items()} }")

    while True:
        if duration and time.time() - start > duration:
            break
        if max_ads and ads_done >= max_ads:
            break
        try:
            pkg, act = adb.focus()
            now = time.time()

            if pkg and is_ad(pkg, act, cfg):
                if ad_start is None:
                    ad_start, taps, tracker = now, {}, CloseTracker()
                    ses = lib.start(act)
                    log(f"vào quảng cáo: {pkg}/{act}")
                elapsed = now - ad_start
                img = last_img = adb.screen()
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                if match_library(gray, tpls.get("wait", []), cfg["template_threshold"],
                                 cfg["template_scales"]):
                    time.sleep(cfg["poll_sec"])
                    continue
                stable = tracker.update(img, find_close(img, tpls, cfg))
                if elapsed >= cfg["min_watch_sec"]:
                    cands = [c for c in stable
                             if taps.get((c[1] // 40, c[2] // 40), 0) < cfg["max_taps_per_spot"]]
                    if cands:
                        sc, x, y, name = cands[0]
                        taps[(x // 40, y // 40)] = taps.get((x // 40, y // 40), 0) + 1
                        log(f"đóng: {name} {sc:.2f} @({x},{y}) sau {elapsed:.0f}s")
                        if cfg["debug"]:
                            annotate(img, cands, DEBUG_DIR / f"ad_{int(now)}.png")
                        lib.tapped(ses, img, cands[0], elapsed)
                        adb.tap(x, y)
                        pause(cfg, cfg["after_tap_sec"])
                        continue
                if elapsed > cfg["ad_timeout_sec"] and now - last_back > 5:
                    log("quá thời gian, bấm BACK")
                    lib.tapped(ses, img, None, elapsed)
                    last_back = now
                    adb.back()
                time.sleep(cfg["poll_sec"])

            elif pkg == game or pkg is None:
                if ad_start is not None:
                    ads_done += 1
                    log(f"xong quảng cáo #{ads_done} ({now - ad_start:.0f}s)")
                    lib.finish(ses, True)
                    ad_start = None
                    last_trigger = 0.0                   # xong quảng cáo: bỏ cooldown, bấm lượt kế ngay
                    pause(cfg, cfg["post_ad_wait_sec"])
                if max_ads and ads_done >= max_ads:
                    continue
                img = adb.screen()
                if tap_first(adb, img, tpls, "popup", cfg):
                    time.sleep(1.0)
                    continue
                if now - last_trigger >= cfg["trigger_cooldown_sec"]:
                    fired = tap_first(adb, img, tpls, "trigger", cfg)
                    if not fired and cfg["trigger_xy"]:
                        adb.tap(*cfg["trigger_xy"])
                        log(f"tap trigger {cfg['trigger_xy']}")
                        fired = True
                    if fired:
                        last_trigger = now
                time.sleep(cfg["poll_sec"])

            else:                                        # app khác (Play Store, launcher...)
                log(f"đang ở app khác {pkg}/{act}, quay lại game")
                if ad_start is not None:                 # từ quảng cáo nhảy sang app lạ = bấm nhầm/chưa đóng được
                    lib.finish(ses, False, last_img)
                    ad_start = None
                adb.back()
                time.sleep(1.5)
                if adb.focus()[0] != game:
                    adb.launch(game)
                    time.sleep(3)
        except (subprocess.TimeoutExpired, RuntimeError) as e:
            log(f"lỗi adb: {e}; thử connect lại")
            adb.connect()
            time.sleep(3)
    log(f"dừng. Đã xem {ads_done} quảng cáo.")


# ---------------------------------------------------------------------- collect

SAMPLES_DIR = APP_DIR / "samples"
_cdp = {"pid": None}


def game_scene(adb, cfg):
    """cur_scene của game đọc qua WebView DevTools (game phải bật debug); None nếu không đọc được."""
    return cdp_eval(adb, cfg, "g_sceneinfo.cur_scene")


def cdp_eval(adb, cfg, expression):
    """Chạy 1 biểu thức JS trong trang game qua WebView DevTools, trả về value (None nếu lỗi)."""
    try:
        import asyncio
        import urllib.request
        import websockets
        pid = adb._run("shell", f"pidof {cfg['game_package']}").decode().split()[0]
        if (adb.serial, pid) != _cdp["pid"]:
            subprocess.run([adb.path, "-s", adb.serial, "forward", "tcp:9222",
                            f"localabstract:webview_devtools_remote_{pid}"], capture_output=True, timeout=10,
                           creationflags=NOWIN)
            _cdp["pid"] = (adb.serial, pid)
        pages = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=3))
        ws_url = next(p["webSocketDebuggerUrl"] for p in pages if "index_amo" in p["url"])

        async def read():
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
                    "expression": expression, "returnByValue": True}}))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("id") == 1:
                        return m["result"]["result"].get("value")
        return asyncio.run(read())
    except Exception:
        return None


def _dhash(img):
    g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (9, 8), interpolation=cv2.INTER_AREA)
    return (g[:, 1:] > g[:, :-1]).flatten()


def collect(cfg, duration, interval, caps):
    """Lưu mẫu quảng cáo (samples/ads/<activity>/) và màn chơi (samples/screens/<scene>/) + index.jsonl."""
    adb = Adb(cfg)
    adb.connect()
    tpls = load_templates()
    SAMPLES_DIR.mkdir(exist_ok=True)
    seen, start = {}, time.time()
    log(f"collect: lưu vào {SAMPLES_DIR}")
    while not duration or time.time() - start < duration:
        try:
            pkg, act = adb.focus()
            if not pkg:
                time.sleep(interval)
                continue
            ad = is_ad(pkg, act, cfg)
            scene = None if ad else game_scene(adb, cfg)
            name = re.sub(r"[^\w.]+", "_", (act if ad else (scene or f"unknown_{act}")))[-60:]
            key = f"{'ads' if ad else 'screens'}/{name}"
            img = adb.screen()
            h = _dhash(img)
            hist = seen.setdefault(key, [])
            if len(hist) < caps["ads" if ad else "screens"] and all((h != o).sum() > 8 for o in hist):
                hist.append(h)
                d = SAMPLES_DIR / key
                d.mkdir(parents=True, exist_ok=True)
                f = d / f"{int(time.time())}.png"
                cv2.imwrite(str(f), img)
                rec = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": "ad" if ad else "screen", "key": key,
                       "package": pkg, "activity": act, "scene": scene, "file": str(f.relative_to(SAMPLES_DIR))}
                if ad:
                    rec["close_candidates"] = [[round(c[0], 2), c[1], c[2], c[3]]
                                               for c in find_close(img, tpls, cfg)[:3]]
                with open(SAMPLES_DIR / "index.jsonl", "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                log(f"mẫu mới {key} ({len(hist)})")
        except (subprocess.TimeoutExpired, RuntimeError) as e:
            log(f"lỗi adb: {e}")
            adb.connect()
        time.sleep(interval)


# -------------------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("--max-ads", type=int, default=0)
    r.add_argument("--duration", type=float, default=0, help="giây, 0 = chạy mãi")
    r.add_argument("--debug", action="store_true", help="lưu ảnh chú thích mỗi lần bấm đóng")
    c = sub.add_parser("collect", help="lưu mẫu quảng cáo + màn chơi vào samples/ (chạy song song với run)")
    c.add_argument("--duration", type=float, default=0, help="giây, 0 = chạy mãi")
    c.add_argument("--interval", type=float, default=1.5)
    c.add_argument("--max-ads-per-type", type=int, default=40)
    c.add_argument("--max-per-scene", type=int, default=4)
    sub.add_parser("shot")
    f = sub.add_parser("find")
    f.add_argument("--image", help="dò trên file ảnh thay vì màn hình thật")
    l = sub.add_parser("learn")
    l.add_argument("name", help="close_xxx | tap_xxx | wait_xxx | trigger_xxx | popup_xxx")
    l.add_argument("x", type=int)
    l.add_argument("y", type=int)
    l.add_argument("--size", type=int, default=48, help="cạnh ô cắt (px)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    cfg = load_config()
    if args.cmd in (None, "run"):
        cfg["debug"] = cfg["debug"] or getattr(args, "debug", False)
        try:
            run(cfg, getattr(args, "max_ads", 0), getattr(args, "duration", 0))
        except KeyboardInterrupt:
            log("dừng bởi người dùng")
        return

    if args.cmd == "collect":
        try:
            collect(cfg, args.duration, args.interval,
                    {"ads": args.max_ads_per_type, "screens": args.max_per_scene})
        except KeyboardInterrupt:
            log("dừng bởi người dùng")
        return

    adb = Adb(cfg)
    adb.connect()
    DEBUG_DIR.mkdir(exist_ok=True)
    if args.cmd == "shot":
        img = adb.screen()
        cv2.imwrite(str(DEBUG_DIR / "shot.png"), img)
        log(f"{img.shape[1]}x{img.shape[0]} focus={adb.focus()} -> {DEBUG_DIR / 'shot.png'}")
    elif args.cmd == "find":
        img = cv2.imread(args.image) if args.image else adb.screen()
        cands = find_close(img, load_templates(), cfg)
        for c in cands:
            log(f"{c[3]:>10} score={c[0]:.2f} @({c[1]},{c[2]})")
        annotate(img, cands, DEBUG_DIR / "find.png")
        log(f"{len(cands)} ứng viên -> {DEBUG_DIR / 'find.png'}")
    elif args.cmd == "learn":
        img = adb.screen()
        h = args.size // 2
        crop = img[max(0, args.y - h):args.y + h, max(0, args.x - h):args.x + h]
        TEMPLATE_DIR.mkdir(exist_ok=True)
        out = TEMPLATE_DIR / f"{args.name}.png"
        cv2.imwrite(str(out), crop)
        log(f"đã lưu mẫu {out} ({crop.shape[1]}x{crop.shape[0]})")


if __name__ == "__main__":
    sys.exit(main())
