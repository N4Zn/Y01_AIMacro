#!/usr/bin/env python3
"""Xem quảng cáo thưởng ở Shop (tab Quảng cáo) hoặc menu chính, có kiểm soát hạn mức.

Mỗi lượt: kiểm tra cur_scene + hạn mức -> bấm đúng 1 nút -> chờ vào quảng cáo -> đóng -> xác nhận `used` tăng.
Dừng khi: sai màn, hết hạn mức, bấm mà không ra quảng cáo (quá --max-miss lần), `used` không tăng, app khác.
Không bao giờ bấm BACK khi đang ở game.

  python shop_ads.py gold ruby cloud cel_essence       # mỗi mục xem đến hết hạn mức
  python shop_ads.py day_ticket --xy 1000,657          # mục cần toạ độ riêng (sau khi cuộn)
  python shop_ads.py mainmenu --xy 1150,185 --count 5  # quảng cáo ở menu chính
"""
import argparse
import random
import subprocess
import sys
import time

import cv2

import ad_autoplayer as a
import library

if sys.stdout:                                           # exe không console: stdout = None
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SHOP_XY = {"gold": (225, 657), "ruby": (607, 657), "cloud": (988, 657), "cel_essence": (1370, 657)}
SHOP_SCENE = "S_PACKAGE_STORE"
# vị trí quảng cáo đơn (place_cfg[item].used là số) -> màn hình chứa nút, và toạ độ nút mặc định
PLACE_SCENE = {"mainmenu": "S_MAINMENU", "marble": "S_MARBLE", "jackpot": "S_JACKPOT_GACHA"}
PLACE_XY = {"mainmenu": (1150, 187), "marble": (280, 818), "jackpot": (280, 818)}


def used_left(adb, cfg, item):
    """(used, limit) từ REWARD_AD; None nếu không đọc được."""
    if item in PLACE_SCENE:
        js = f"JSON.stringify([REWARD_AD.place_cfg.{item}.used, REWARD_AD.place_cfg.{item}.limit])"
    else:
        js = (f"JSON.stringify([REWARD_AD.place_cfg.shop_ad.used.{item}, "
              f"REWARD_AD.place_cfg.shop_ad.limits.{item}])")
    v = a.cdp_eval(adb, cfg, js)
    return tuple(a.json.loads(v)) if v else None


def watch_ad(adb, cfg, tpls, lib, enter_timeout=15, should_stop=None):
    """Chờ quảng cáo mở, đóng nó, trả về True khi đã về game. False nếu không ra quảng cáo / kẹt.
    `lib` (AdLibrary) ghi lại cách đóng để chia sẻ kinh nghiệm; `should_stop()` -> True để bỏ dở."""
    stopped = should_stop or (lambda: False)
    t0 = time.time()
    while time.time() - t0 < enter_timeout:
        if stopped():
            return False
        pkg, act = adb.focus()
        if pkg and a.is_ad(pkg, act, cfg):
            break
        time.sleep(0.5)
    else:
        return False
    a.log(f"  vào quảng cáo {act}")
    ses, last_img = lib.start(act), None
    ad_start, taps, last_back = time.time(), {}, 0.0
    tracker, lost_since, play_backs = a.CloseTracker(), None, 0
    while True:
        if stopped():
            a.log("  dừng theo yêu cầu (quảng cáo còn mở, hãy tự đóng)")
            return False
        now = time.time()
        pkg, act = adb.focus()
        if pkg is None:                                  # đang chuyển cảnh, hoặc BlueStacks/adb đã mất
            lost_since = lost_since or now
            if now - lost_since > 20:
                raise RuntimeError("mất focus/adb quá 20s (BlueStacks tắt?)")
            time.sleep(0.5)
            continue
        lost_since = None
        if pkg == "com.android.vending" and play_backs < 3:
            # quảng cáo tự mở trang Google Play giữa chừng (đã gặp thật: Amaze GO!). Vẫn là luồng quảng cáo —
            # BACK 1 lần quay về AdActivity gốc (đã có Reward granted), rồi vòng lặp đóng bình thường tiếp.
            play_backs += 1
            a.log(f"  quảng cáo mở Google Play ({act}), BACK về quảng cáo ({play_backs}/3)")
            adb.back()
            time.sleep(1.5)
            continue
        if not a.is_ad(pkg, act, cfg):
            if pkg == cfg["game_package"]:
                a.log(f"  xong quảng cáo ({now - ad_start:.0f}s)")
                lib.finish(ses, True)
                a.pause(cfg, cfg["post_ad_wait_sec"])
                return True
            a.log(f"  app lạ {pkg}/{act}, dừng")        # không BACK bừa: để người dùng xử lý
            lib.finish(ses, False, last_img)
            return False
        img = last_img = adb.screen()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if a.match_library(gray, tpls.get("wait", []), cfg["template_threshold"], cfg["template_scales"]):
            time.sleep(cfg["poll_sec"])
            continue
        stable = tracker.update(img, a.find_close(img, tpls, cfg))
        if now - ad_start >= cfg["min_watch_sec"]:
            cands = [c for c in stable
                     if taps.get((c[1] // 40, c[2] // 40), 0) < cfg["max_taps_per_spot"]]
            if cands:
                sc, x, y, name = cands[0]
                taps[(x // 40, y // 40)] = taps.get((x // 40, y // 40), 0) + 1
                a.log(f"  đóng: {name} {sc:.2f} @({x},{y}) sau {now - ad_start:.0f}s")
                lib.tapped(ses, img, cands[0], now - ad_start)
                adb.tap(x, y)
                a.pause(cfg, cfg["after_tap_sec"])
                continue
        if now - ad_start > cfg["ad_timeout_sec"] and now - last_back > 5:
            a.log("  quảng cáo quá lâu, BACK (đang trong activity quảng cáo)")
            lib.tapped(ses, img, None, now - ad_start)
            last_back = now
            adb.back()
        time.sleep(cfg["poll_sec"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("items", nargs="+", help="gold ruby cloud cel_essence day_ticket ... | mainmenu")
    ap.add_argument("--xy", help="toạ độ nút x,y (áp cho mọi mục; mặc định theo bảng Shop)")
    ap.add_argument("--count", type=int, help="số quảng cáo tối đa mỗi mục (mặc định: tới hết hạn mức)")
    ap.add_argument("--max-miss", type=int, default=3)
    args = ap.parse_args()

    cfg = a.load_config()
    adb = a.Adb(cfg)
    adb.connect()
    tpls = a.load_templates()
    lib = library.AdLibrary(log=a.log)

    for item in args.items:
        want_scene = PLACE_SCENE.get(item, SHOP_SCENE)
        xy = tuple(int(v) for v in args.xy.split(",")) if args.xy else \
            PLACE_XY.get(item) or SHOP_XY.get(item)
        if not xy:
            a.log(f"{item}: chưa có toạ độ, dùng --xy")
            return
        done, miss = 0, 0
        pkg, act = adb.focus()
        if pkg and a.is_ad(pkg, act, cfg):               # còn quảng cáo đang mở: đóng trước khi bấm gì
            a.log(f"đang có quảng cáo mở sẵn ({act}), đóng trước")
            if not watch_ad(adb, cfg, tpls, lib):
                return
        while True:
            scene = a.game_scene(adb, cfg)
            ul = used_left(adb, cfg, item)
            if scene != want_scene or ul is None:
                a.log(f"{item}: sai màn/không đọc được (scene={scene}, quota={ul}), dừng")
                return
            used, limit = ul
            if used >= limit or (args.count and done >= args.count):
                a.log(f"{item}: xong ({used}/{limit}), đã xem {done} lượt")
                break
            a.log(f"{item}: {used}/{limit} -> bấm {xy}")
            if done:                                     # nghỉ ngẫu nhiên 1-4s giữa 2 lượt như người dùng thật
                time.sleep(random.uniform(1.0, 4.0))
            adb.tap(*xy)
            if not watch_ad(adb, cfg, tpls, lib):
                miss += 1
                a.log(f"{item}: không thấy quảng cáo ({miss}/{args.max_miss})")
                if miss >= args.max_miss or adb.focus()[0] != cfg["game_package"]:
                    return
                time.sleep(2)
                continue
            a.pause(cfg, 1.5)
            ul2 = used_left(adb, cfg, item)
            if ul2 and ul2[0] <= used:
                a.log(f"{item}: xem xong nhưng used không tăng ({ul2}), dừng")
                return
            done, miss = done + 1, 0
    a.log("hoàn tất")


if __name__ == "__main__":
    try:
        main()
    except (subprocess.TimeoutExpired, RuntimeError) as e:
        a.log(f"lỗi adb: {e}; dừng (không tự bấm tiếp)")
