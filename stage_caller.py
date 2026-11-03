#!/usr/bin/env python3
"""CLI mỏng gọi engine.Engine.auto_play_stage — xem docstring ở đó. Giữ lại cho quen tay dòng lệnh;
gui_app.py gọi thẳng engine.auto_play_stage, không qua file này.

  python stage_caller.py [--keys 12345] [--interval 2.0] [--repeat 2] [--mineral] [--meteor] [--no-missile]
"""
import argparse

import ad_autoplayer as a
import engine


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", default="12345", help="nhân vật gọi mỗi lượt, vd 12345")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--repeat", type=int, default=2, help="số lần bấm liên tiếp cho mỗi nhân vật")
    ap.add_argument("--gap", type=float, default=0.2, help="nghỉ giữa 2 thao tác (giây)")
    ap.add_argument("--no-missile", action="store_true", help="tắt tự bấm tên lửa")
    ap.add_argument("--mineral", action="store_true", help="bật tự thu khoáng (chưa xác nhận phím)")
    ap.add_argument("--meteor", action="store_true", help="bật tự bắn thiên thạch khi có")
    ap.add_argument("--max-sec", type=float, default=3600)
    ap.add_argument("--no-result-ad", action="store_true",
                    help="tắt tự xem QC kết quả sau màn (vd +2000% vàng)")
    args = ap.parse_args()

    cfg = a.load_config()
    eng = engine.Engine(cfg, a.log)
    eng.adb.connect()
    eng.auto_play_stage(chars=args.keys, missile=not args.no_missile, mineral=args.mineral,
                        meteor=args.meteor, interval=args.interval, repeat=args.repeat,
                        gap=args.gap, max_sec=args.max_sec, watch_result_ad=not args.no_result_ad)


if __name__ == "__main__":
    main()
