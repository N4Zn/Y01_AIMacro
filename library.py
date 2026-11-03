#!/usr/bin/env python3
"""Thư viện "kinh nghiệm" quảng cáo: tool tự ghi lại cách đóng từng kiểu quảng cáo đã gặp.

Mỗi lần 1 quảng cáo kết thúc thành công, ghi 1 "công thức" khoá theo (activity, loại nút, ô vị trí):
nút nào (x/skip/back/tự hết), ở đâu, sau bao lâu thì đóng được, số lần gặp, kèm ảnh mẫu nhỏ + mẫu cắt của nút.
Quảng cáo kết thúc mà không đóng được bình thường -> lưu vào `unresolved/` để người xem sau.

  python library.py report                    # liệt kê công thức đã biết
  python library.py merge <thư_mục_library>   # gộp thư viện từ máy khác vào máy này

Thư mục `library/` không phụ thuộc tài khoản/máy: copy hoặc commit để chia sẻ.
"""
import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
# đóng gói exe: ghi cạnh file exe, không ghi vào thư mục tạm giải nén
ROOT = (Path(sys.executable).parent if getattr(sys, "frozen", False) else HERE) / "library"
MAX_SAMPLES = 5            # số ảnh mẫu giữ cho mỗi công thức
HASH_NEAR = 8              # 2 ảnh cách nhau <=8/64 bit coi là cùng 1 quảng cáo
GRID = 40                  # ô vị trí để gom các nút gần nhau thành 1 công thức


def dhash(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    s = cv2.resize(g, (9, 8), interpolation=cv2.INTER_AREA)
    bits = "".join("1" if b else "0" for b in (s[:, 1:] > s[:, :-1]).flatten())
    return f"{int(bits, 2):016x}"


def _near(h1, h2):
    return bin(int(h1, 16) ^ int(h2, 16)).count("1") <= HASH_NEAR


def _slug(key):
    return re.sub(r"[^A-Za-z0-9]+", "_", key).strip("_")[-80:]


class AdLibrary:
    def __init__(self, root=ROOT, log=print):
        self.root, self.log = Path(root), log
        p = self.root / "index.json"
        self.idx = json.loads(p.read_text(encoding="utf-8")) if p.exists() else \
            {"version": 1, "recipes": {}, "unresolved": []}

    # ---- vòng đời 1 quảng cáo
    def start(self, activity):
        return {"activity": activity, "t0": time.time(), "pending": None}

    def tapped(self, ses, img, cand, elapsed):
        """Gọi ngay trước khi bấm nút đóng `cand` = (score, x, y, kind); cand=None nghĩa là bấm BACK."""
        ses["pending"] = {"img": img.copy(), "cand": cand, "elapsed": elapsed}

    def finish(self, ses, ok, last_img=None):
        """Quảng cáo kết thúc. ok=True: lượt cuối đóng được -> ghi công thức; False: lưu vào unresolved."""
        try:
            if ok:
                self._commit(ses)
            else:
                self._unresolved(ses, last_img)
            self._save()
        except Exception as e:                       # thư viện không bao giờ làm hỏng vòng xem quảng cáo
            self.log(f"  [thư viện] lỗi bỏ qua: {e}")

    # ---- ghi
    def _commit(self, ses):
        act, pend = ses["activity"], ses["pending"]
        total = time.time() - ses["t0"]
        if pend is None:
            kind, x, y, elapsed, img = "auto", 0, 0, total, None   # quảng cáo tự hết, không bấm gì
        elif pend["cand"] is None:
            kind, x, y, elapsed, img = "back", 0, 0, pend["elapsed"], pend["img"]
        else:
            _, x, y, kind = pend["cand"]
            elapsed, img = pend["elapsed"], pend["img"]
        key = f"{act}|{kind}|{x // GRID}|{y // GRID}"
        new = key not in self.idx["recipes"]
        r = self.idx["recipes"].setdefault(key, {
            "activity": act, "kind": kind, "x": int(x), "y": int(y), "count": 0, "sec_min": None,
            "sec_max": None, "sec_sum": 0.0, "first_seen": time.strftime("%Y-%m-%d"),
            "samples": [], "crop": None})
        r["count"] += 1
        r["sec_sum"] = round(r["sec_sum"] + elapsed, 1)
        r["sec_min"] = round(elapsed if r["sec_min"] is None else min(r["sec_min"], elapsed), 1)
        r["sec_max"] = round(elapsed if r["sec_max"] is None else max(r["sec_max"], elapsed), 1)
        r["last_seen"] = time.strftime("%Y-%m-%d")
        if img is not None:
            self._add_sample(r, key, img)
            if kind in ("x", "skip") and not r["crop"]:
                r["crop"] = self._save_crop(key, img, x, y)
        if new:
            self.log(f"  [thư viện] ★ công thức MỚI: {kind} @({x},{y}) sau {elapsed:.0f}s trong {act.split('.')[-1]}")

    def _add_sample(self, r, key, img):
        h = dhash(img)
        if len(r["samples"]) >= MAX_SAMPLES or any(_near(h, s["hash"]) for s in r["samples"]):
            return
        d = self.root / "ads"
        d.mkdir(parents=True, exist_ok=True)
        name = f"ads/{_slug(key)}_{h[:8]}.jpg"
        scale = 480 / img.shape[1]
        cv2.imwrite(str(self.root / name), cv2.resize(img, None, fx=scale, fy=scale),
                    [cv2.IMWRITE_JPEG_QUALITY, 70])
        r["samples"].append({"file": name, "hash": h})

    def _save_crop(self, key, img, x, y, r=32):
        h, w = img.shape[:2]
        x0, y0 = min(max(int(x) - r, 0), w - 2 * r), min(max(int(y) - r, 0), h - 2 * r)
        d = self.root / "crops"
        d.mkdir(parents=True, exist_ok=True)
        name = f"crops/{_slug(key)}.png"
        cv2.imwrite(str(self.root / name), img[y0:y0 + 2 * r, x0:x0 + 2 * r])
        return name

    def _unresolved(self, ses, last_img):
        img = last_img if last_img is not None else (ses["pending"] or {}).get("img")
        if img is None:
            return
        h = dhash(img)
        if any(_near(h, u["hash"]) for u in self.idx["unresolved"]):
            return
        d = self.root / "unresolved"
        d.mkdir(parents=True, exist_ok=True)
        name = f"unresolved/{time.strftime('%Y%m%d_%H%M%S')}_{h[:8]}.jpg"
        cv2.imwrite(str(self.root / name), cv2.resize(img, None, fx=480 / img.shape[1], fy=480 / img.shape[1]),
                    [cv2.IMWRITE_JPEG_QUALITY, 70])
        self.idx["unresolved"].append({"file": name, "hash": h, "activity": ses["activity"]})
        self.log(f"  [thư viện] quảng cáo chưa đóng được -> {name}")

    def _save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "index.json").write_text(
            json.dumps(self.idx, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    # ---- gộp thư viện máy khác
    def merge(self, other_root):
        other_root = Path(other_root)
        other = json.loads((other_root / "index.json").read_text(encoding="utf-8"))
        added = 0
        for key, o in other["recipes"].items():
            r = self.idx["recipes"].get(key)
            if r is None:
                self.idx["recipes"][key] = r = dict(o, samples=[])
                added += 1
            else:
                r["count"] += o["count"]
                r["sec_sum"] = round(r["sec_sum"] + o["sec_sum"], 1)
                r["sec_min"] = min(r["sec_min"], o["sec_min"])
                r["sec_max"] = max(r["sec_max"], o["sec_max"])
                r["first_seen"] = min(r["first_seen"], o["first_seen"])
                r["last_seen"] = max(r.get("last_seen", ""), o.get("last_seen", ""))
            for s in o["samples"]:
                if len(r["samples"]) < MAX_SAMPLES and not any(_near(s["hash"], t["hash"]) for t in r["samples"]):
                    self._copy(other_root, s["file"])
                    r["samples"].append(s)
            if o.get("crop") and not r.get("crop"):
                self._copy(other_root, o["crop"])
                r["crop"] = o["crop"]
        for u in other["unresolved"]:
            if not any(_near(u["hash"], v["hash"]) for v in self.idx["unresolved"]):
                self._copy(other_root, u["file"])
                self.idx["unresolved"].append(u)
        self._save()
        return added

    def _copy(self, other_root, rel):
        dst = self.root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if (other_root / rel).exists() and not dst.exists():
            shutil.copy2(other_root / rel, dst)

    def report(self):
        rows = sorted(self.idx["recipes"].values(), key=lambda r: (r["activity"], -r["count"]))
        print(f"{len(rows)} công thức, {len(self.idx['unresolved'])} quảng cáo chưa đóng được")
        for r in rows:
            avg = r["sec_sum"] / r["count"]
            print(f"  {r['activity'].split('.')[-1]:<32} {r['kind']:<5} @({r['x']:>4},{r['y']:>3}) "
                  f"x{r['count']:<3} {r['sec_min']:.0f}-{r['sec_max']:.0f}s (tb {avg:.0f}s)")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("report")
    m = sub.add_parser("merge")
    m.add_argument("other")
    args = ap.parse_args()
    lib = AdLibrary()
    if args.cmd == "report":
        lib.report()
    else:
        print(f"gộp xong, thêm {lib.merge(args.other)} công thức mới")


if __name__ == "__main__":
    main()
