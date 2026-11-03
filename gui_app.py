#!/usr/bin/env python3
"""EduXplore Ad Helper — giao diện tự xem quảng cáo thưởng El Dorado trên BlueStacks (không cần AI/agent).

Chọn hạng mục + số lượt, bấm Bắt đầu. Tool tự: kết nối adb, đọc hạn mức trong game, mở đúng màn hình,
cuộn tìm nút, xem và đóng quảng cáo, ghi log.
"""
import json
import os
import queue
import threading
import time
import tkinter as tk
import traceback
from tkinter import simpledialog, ttk, messagebox
from tkinter.scrolledtext import ScrolledText

import ad_autoplayer as a

LOG_DIR = a.APP_DIR / "logs"
PRESETS_FILE = a.APP_DIR / "presets.json"
HEARTBEAT_SEC = 25
STAGE_CHOICE_FILE = a.APP_DIR / "last_stage_choice.json"     # nhớ lựa chọn lần trước của form "Tự chơi màn"


def load_stage_choice():
    try:
        return json.loads(STAGE_CHOICE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_stage_choice(step):
    try:
        keep = {k: v for k, v in step.items() if k != "kind"}
        STAGE_CHOICE_FILE.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


class LoginDialog(tk.Toplevel):
    """Màn đăng nhập/đăng ký (chặn), đóng với self.result = kết quả /auth/login hoặc None nếu huỷ."""

    def __init__(self, parent, server_url):
        super().__init__(parent)
        self.title("Đăng nhập — EduXplore Ad Helper")
        self.geometry("420x370")
        self.resizable(False, False)
        self.configure(bg="SystemButtonFace")
        self.result = None
        import server_client
        last = server_client.load_last_login() or {}      # email nhớ được kể cả sau khi đăng xuất (không mật khẩu)
        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Máy chủ:").pack(anchor="w")
        self.server = tk.StringVar(value=last.get("server_url") or server_url)
        ttk.Entry(frm, textvariable=self.server).pack(fill="x", pady=(0, 10))
        ttk.Label(frm, text="Email:").pack(anchor="w")
        self.email = tk.StringVar(value=last.get("email", ""))
        email_entry = ttk.Entry(frm, textvariable=self.email)
        email_entry.pack(fill="x", pady=(0, 10))
        ttk.Label(frm, text="Mật khẩu:").pack(anchor="w")
        self.pw = tk.StringVar(value=last.get("password", ""))
        e = ttk.Entry(frm, textvariable=self.pw, show="•")
        e.pack(fill="x", pady=(0, 6))
        e.bind("<Return>", lambda _ev: self._login())
        self.remember = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm, text="Ghi nhớ đăng nhập (tự vào lần sau, không cần nhập lại)",
                        variable=self.remember).pack(anchor="w", pady=(0, 6))
        self.status = ttk.Label(frm, text="", foreground="#a00", wraplength=340)
        self.status.pack(fill="x", pady=(4, 10))
        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        self.btn_login = ttk.Button(btns, text="Đăng nhập", command=self._login)
        self.btn_login.pack(side="left")
        self.btn_register = ttk.Button(btns, text="Đăng ký", command=self._do_register)
        self.btn_register.pack(side="left", padx=6)
        ttk.Button(btns, text="Thoát", command=self._quit).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self._quit)
        self.transient(parent)
        self.update_idletasks()            # vẽ xong nội dung trước khi hiện + chiếm focus (tránh cửa sổ trắng
        self.deiconify()                   # khi gói bằng PyInstaller --windowed, cửa sổ con bật quá sớm)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except tk.TclError:
            self.after(100, self._try_grab)
        (e if self.email.get() else email_entry).focus_set()   # có email sẵn -> focus thẳng ô mật khẩu

    def _try_grab(self):
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _busy(self, busy):
        state = "disabled" if busy else "normal"
        self.btn_login.config(state=state)
        self.btn_register.config(state=state)

    def _login(self):
        if not self.email.get().strip() or not self.pw.get():
            self.status.config(text="Nhập đủ email và mật khẩu", foreground="#a00")
            return
        self.status.config(text="Đang kết nối…", foreground="#555")
        self._busy(True)
        self.update_idletasks()
        try:
            import server_client
            self.result = server_client.login(self.server.get().strip(), self.email.get().strip(),
                                              self.pw.get(), remember=self.remember.get())
            self.destroy()
        except Exception as e:
            self.status.config(text=str(e), foreground="#a00")
            self._busy(False)

    def _do_register(self):
        # tên khác "_register": trùng với Misc._register nội bộ của tkinter (dùng để đăng ký callback Tcl) sẽ
        # phá vỡ việc dựng widget ngay giữa chừng -> cửa sổ hiện trắng dở dang (đã gặp thật, không phải đoán)
        if not self.email.get().strip() or len(self.pw.get()) < 6:
            self.status.config(text="Email hợp lệ + mật khẩu tối thiểu 6 ký tự", foreground="#a00")
            return
        self.status.config(text="Đang đăng ký…", foreground="#555")
        self._busy(True)
        self.update_idletasks()
        try:
            import server_client
            server_client.register(self.server.get().strip(), self.email.get().strip(), self.pw.get())
        except Exception as e:
            self.status.config(text=str(e), foreground="#a00")
            self._busy(False)
            return
        self._login()

    def _quit(self):
        self.result = None
        self.destroy()


class StageStepDialog(tk.Toplevel):
    """Cấu hình 1 bước 'tự chơi màn' trong hàng đợi. self.result = dict bước, None nếu huỷ."""

    def __init__(self, parent, prefill=None):
        super().__init__(parent)
        self.title("Bước: Tự chơi màn")
        self.geometry("460x720")          # nội dung dài hơn khung cố định cũ (420) -> nút bị khuất, không
        self.minsize(420, 560)            # kéo được vì resizable=False -> cho kéo + tăng cao hẳn lên
        self.resizable(True, True)
        self.result = None
        p = {**load_stage_choice(), **(prefill or {})}
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Chọn cách chơi:", font=("", 10, "bold")).pack(anchor="w")
        self.mode = tk.StringVar(value=p.get("mode", "watch"))
        mode_box = ttk.Frame(frm)
        mode_box.pack(fill="x", pady=(2, 0))
        # 1) chơi liên tục theo thời gian — tool không tự vào/chuyển màn, bạn tự vào màn nào cũng được
        r1 = ttk.Frame(mode_box)
        r1.pack(fill="x")
        ttk.Radiobutton(r1, text="Chơi liên tục trong", variable=self.mode, value="watch",
                        command=self._sync_mode).pack(side="left")
        self.duration = tk.IntVar(value=p.get("duration", 3600))
        self.sp_duration = ttk.Spinbox(r1, from_=10, to=999999, increment=60, textvariable=self.duration, width=8)
        self.sp_duration.pack(side="left", padx=4)
        ttk.Label(r1, text="giây").pack(side="left")
        ttk.Label(mode_box, text="    Bạn tự vào màn nào cũng được; hết màn thì tool chờ bạn vào màn tiếp.",
                  foreground="#777", wraplength=400).pack(anchor="w")
        # 2) lặp lại đúng 1 màn cố định — tool tự vào lại đúng màn đó sau mỗi lượt
        ttk.Radiobutton(mode_box, text="Chơi lặp lại 1 màn cụ thể (tool tự vào lại đúng màn đó)",
                        variable=self.mode, value="fixed", command=self._sync_mode).pack(anchor="w", pady=(6, 0))
        r2 = ttk.Frame(mode_box)
        r2.pack(fill="x", padx=(22, 0))
        self.hard = tk.StringVar(value="Khó" if p.get("hard") else "Thường")
        self.cb_hard = ttk.Combobox(r2, textvariable=self.hard, values=["Thường", "Khó"], state="readonly", width=8)
        self.cb_hard.pack(side="left")
        ttk.Label(r2, text="Màn số:").pack(side="left", padx=(8, 2))
        self.stage_num = tk.StringVar(value=str(p.get("stage_num", "")))
        self.en_stage = ttk.Entry(r2, textvariable=self.stage_num, width=7)
        self.en_stage.pack(side="left")
        ttk.Label(r2, text="Số lần:").pack(side="left", padx=(8, 2))
        self.times = tk.IntVar(value=p.get("times", 5))
        self.sp_times = ttk.Spinbox(r2, from_=1, to=999, textvariable=self.times, width=5)
        self.sp_times.pack(side="left")
        # 3) chơi đúng 1 màn do bạn tự vào (hành vi cũ)
        ttk.Radiobutton(mode_box, text="Chơi 1 màn do bạn tự vào (chỉ 1 lượt)", variable=self.mode,
                        value="single", command=self._sync_mode).pack(anchor="w", pady=(6, 0))
        ttk.Separator(frm).pack(fill="x", pady=(10, 8))
        self.missile = tk.BooleanVar(value=p.get("missile", True))
        self.mineral = tk.BooleanVar(value=p.get("mineral", False))
        self.meteor = tk.BooleanVar(value=p.get("meteor", False))
        # ttk.Checkbutton không nhận wraplength lúc khởi tạo trên 1 số bản Tk (TclError) -> làm hỏng việc
        # dựng cửa sổ giữa chừng, các widget phía sau (kể cả nút "Thêm vào hàng đợi") không bao giờ được
        # tạo ra — y hệt lỗi _register trước đây. Giữ chữ ngắn gọn 1 dòng, chú thích dài để riêng ở Label.
        ttk.Checkbutton(frm, text="Tên lửa (Missile)", variable=self.missile).pack(anchor="w")
        ttk.Checkbutton(frm, text="Khoáng (Mineral)", variable=self.mineral).pack(anchor="w")
        ttk.Checkbutton(frm, text="Thiên thạch (Meteor, tự bắn khi có sẵn)", variable=self.meteor
                        ).pack(anchor="w")
        self.watch_result_ad = tk.BooleanVar(value=p.get("watch_result_ad", True))
        ttk.Checkbutton(frm, text="Xem QC kết quả sau khi hết màn", variable=self.watch_result_ad
                        ).pack(anchor="w")
        ttk.Label(frm, text="   (vd +2000% vàng, nếu có)", foreground="#777",
                 wraplength=340).pack(anchor="w")
        ttk.Label(frm, text="Nhân vật gọi mỗi lượt (vd 12345):").pack(anchor="w", pady=(10, 0))
        self.chars = tk.StringVar(value=p.get("chars", "12345"))
        ttk.Entry(frm, textvariable=self.chars, width=14).pack(anchor="w")
        grid = ttk.Frame(frm)
        grid.pack(fill="x", pady=(12, 0))
        self.interval = tk.DoubleVar(value=p.get("interval", 1.0))
        self.repeat = tk.IntVar(value=p.get("repeat", 1))
        self.gap = tk.DoubleVar(value=p.get("gap", 0.05))
        self.max_sec = tk.IntVar(value=p.get("max_sec", 600))
        self.wait_entry_sec = tk.IntVar(value=p.get("wait_entry_sec", 60))
        rows = [("Chu kỳ gọi lại (giây):", self.interval), ("Số lần bấm / nhân vật:", self.repeat),
                ("Nghỉ giữa thao tác (giây):", self.gap), ("Tối đa 1 màn (giây):", self.max_sec),
                ("Chờ bạn vào màn (giây):", self.wait_entry_sec)]
        for r, (label, var) in enumerate(rows):
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky="w", pady=2)
            sp = ttk.Spinbox(grid, from_=0, to=99999,
                             increment=0.05 if isinstance(var, tk.DoubleVar) else 1,
                             textvariable=var, width=8)
            sp.grid(row=r, column=1, sticky="w", padx=6)
            if var is self.wait_entry_sec:
                self.sp_wait = sp          # chỉ dùng cho chế độ "1 màn do bạn tự vào"
        self._sync_mode()
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(18, 0))
        ttk.Button(btns, text="Thêm vào hàng đợi", command=self._ok).pack(side="left")
        ttk.Button(btns, text="Huỷ", command=self.destroy).pack(side="left", padx=6)
        self.transient(parent)
        self.update_idletasks()
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _sync_mode(self):
        """Chỉ cho sửa ô thuộc chế độ đang chọn (các ô còn lại mờ đi)."""
        m = self.mode.get()
        on = lambda w, ok: w.config(state="normal" if ok else "disabled")
        on(self.sp_duration, m == "watch")
        self.cb_hard.config(state="readonly" if m == "fixed" else "disabled")
        on(self.en_stage, m == "fixed")
        on(self.sp_times, m == "fixed")
        on(self.sp_wait, m == "single")

    def _ok(self):
        if not (self.missile.get() or self.mineral.get() or self.meteor.get() or self.chars.get().strip()):
            messagebox.showinfo("Chưa chọn", "Hãy chọn ít nhất 1 thao tác (tên lửa/khoáng/thiên thạch/nhân vật).")
            return
        mode = self.mode.get()
        stage_txt = self.stage_num.get().strip()
        if mode == "fixed" and not (stage_txt.isdigit() and int(stage_txt) >= 1):
            messagebox.showinfo("Thiếu số màn", "Gõ số màn muốn lặp lại (vd 38, 115).")
            return
        self.result = {
            "kind": "stage", "mode": mode, "missile": self.missile.get(), "mineral": self.mineral.get(),
            "meteor": self.meteor.get(), "chars": self.chars.get().strip(),
            "interval": self.interval.get(), "repeat": self.repeat.get(), "gap": self.gap.get(),
            "max_sec": self.max_sec.get() or 3600, "wait_entry_sec": self.wait_entry_sec.get() or 60,
            "watch_result_ad": self.watch_result_ad.get(),
            "duration": self.duration.get() or 3600,
            "hard": self.hard.get() == "Khó", "stage_num": int(stage_txt) if stage_txt.isdigit() else 0,
            "times": self.times.get() or 1,
        }
        save_stage_choice(self.result)
        self.destroy()


class App:
    def __init__(self, root):
        self.root = root
        root.title("EduXplore Ad Helper — El Dorado")
        root.geometry("980x720")
        root.minsize(860, 560)
        self.q = queue.Queue()
        self.stop_evt = threading.Event()
        self.busy = False
        self.vars = {}                  # (cid, key) -> (BooleanVar, IntVar)
        self.cfg = a.load_config()
        a.log = self.log                # mọi log của lõi đi vào khung log
        LOG_DIR.mkdir(exist_ok=True)
        self.logfile = LOG_DIR / f"{time.strftime('%Y%m%d')}.log"
        self.client = None               # server_client.Client sau khi đăng nhập
        self.account_email = None
        self.entitlements = []           # danh sách cid được phép chạy (hoặc ["all"])
        self.plan = "free"
        self._session_id = None          # phiên server đang khoá (None = không có)
        self._hb_stop = None
        self.step_queue = []             # [{"kind":"ads",...} | {"kind":"stage",...}]
        self.item_labels = {}            # (cid,key) -> (nhãn hạng mục, nhãn mục), đổ đầy khi populate()
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.pump)
        self.log("Sẵn sàng. Bật ADB trong BlueStacks (Cài đặt → Nâng cao), mở game, rồi bấm 'Kết nối'.")
        root.after(50, self._ensure_auth)
        self.connect()

    # ---------------------------------------------------------------- giao diện
    def _build(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Thiết bị adb:").pack(side="left")
        self.dev = ttk.Combobox(top, width=24, values=[self.cfg["serial"]])
        self.dev.set(self.cfg["serial"])
        self.dev.pack(side="left", padx=4)
        ttk.Button(top, text="Kết nối / Tìm", command=self.connect).pack(side="left", padx=2)
        self.btn_refresh = ttk.Button(top, text="Làm mới hạn mức", command=self.refresh)
        self.btn_refresh.pack(side="left", padx=2)
        self.status = ttk.Label(top, text="Chưa kết nối", foreground="#a00")
        self.status.pack(side="left", padx=10)
        ttk.Button(top, text="Mở thư mục log", command=lambda: os.startfile(str(a.APP_DIR))).pack(side="right")
        ttk.Button(top, text="Đăng xuất", command=self.logout).pack(side="right", padx=(0, 8))
        self.account_label = ttk.Label(top, text="chưa đăng nhập", foreground="#777")
        self.account_label.pack(side="right", padx=(0, 8))

        mid = ttk.LabelFrame(self.root, text="Hạng mục quảng cáo (tick mục cần xem, chỉnh số lượt)", padding=4)
        mid.pack(fill="both", expand=False, padx=8)
        canvas = tk.Canvas(mid, height=270, highlightthickness=0)
        sb = ttk.Scrollbar(mid, orient="vertical", command=canvas.yview)
        self.items_frame = ttk.Frame(canvas)
        self.items_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.items_frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        ttk.Label(self.items_frame, text="Bấm 'Kết nối / Tìm' để đọc danh sách từ game…").pack(padx=10, pady=10)

        bar = ttk.Frame(self.root, padding=(8, 6))
        bar.pack(fill="x")
        self.btn_start = ttk.Button(bar, text="▶ Bắt đầu", command=self.start)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(bar, text="■ Dừng", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=6)
        ttk.Button(bar, text="Chọn hết", command=lambda: self.tick_all(True)).pack(side="left", padx=(16, 2))
        ttk.Button(bar, text="Bỏ chọn", command=lambda: self.tick_all(False)).pack(side="left")
        self.rand = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Ngẫu nhiên hoá chạm/thời gian (giống người dùng)", variable=self.rand
                        ).pack(side="right")

        qf = ttk.LabelFrame(self.root, text="Hàng đợi bước chạy (xem QC + tự chơi màn, chạy tuần tự)",
                            padding=4)
        qf.pack(fill="x", padx=8, pady=(0, 4))
        self.queue_list = tk.Listbox(qf, height=5)
        self.queue_list.pack(side="left", fill="both", expand=True, padx=(2, 4), pady=2)
        qbtns = ttk.Frame(qf)
        qbtns.pack(side="left", padx=2)
        ttk.Button(qbtns, text="+ QC (theo lựa chọn ở trên)", command=self.queue_add_ads
                  ).pack(fill="x", pady=1)
        ttk.Button(qbtns, text="+ Tự chơi màn…", command=self.queue_add_stage).pack(fill="x", pady=1)
        ttk.Button(qbtns, text="+ Tứ thần", command=self.queue_add_four_gods).pack(fill="x", pady=1)
        ttk.Button(qbtns, text="↑ Lên", command=lambda: self.queue_move(-1)).pack(fill="x", pady=1)
        ttk.Button(qbtns, text="↓ Xuống", command=lambda: self.queue_move(1)).pack(fill="x", pady=1)
        ttk.Button(qbtns, text="Xoá bước", command=self.queue_remove).pack(fill="x", pady=1)
        ttk.Button(qbtns, text="Xoá hết", command=self.queue_clear).pack(fill="x", pady=1)
        self.btn_run_queue = ttk.Button(qbtns, text="▶ Chạy hàng đợi", command=self.run_queue)
        self.btn_run_queue.pack(fill="x", pady=(6, 1))

        pf = ttk.Frame(self.root, padding=(8, 0))
        pf.pack(fill="x", padx=0, pady=(0, 6))
        ttk.Label(pf, text="Cấu hình đã lưu:").pack(side="left")
        self.preset_combo = ttk.Combobox(pf, width=22, state="readonly")
        self.preset_combo.pack(side="left", padx=4)
        ttk.Button(pf, text="Nạp", command=self.preset_load).pack(side="left", padx=2)
        ttk.Button(pf, text="Lưu…", command=self.preset_save).pack(side="left", padx=2)
        ttk.Button(pf, text="Xoá", command=self.preset_delete).pack(side="left", padx=2)
        self._refresh_preset_list()

        lf = ttk.LabelFrame(self.root, text="Nhật ký", padding=4)
        lf.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.logbox = ScrolledText(lf, height=12, state="disabled", font=("Consolas", 9), wrap="word")
        self.logbox.pack(fill="both", expand=True)
        self.logbox.tag_config("warn", foreground="#b35a00")
        self.logbox.tag_config("head", foreground="#0b4fa8", font=("Consolas", 9, "bold"))
        self.logbox.tag_config("ok", foreground="#1a7f37")

    def populate(self, scene, cats, extra):
        for w in self.items_frame.winfo_children():
            w.destroy()
        old = {k: (v[0].get(), v[1].get()) for k, v in self.vars.items()}
        self.vars = {}
        self.item_labels = {}            # (cid,key) -> (nhãn hạng mục, nhãn mục) để ghi vào hàng đợi
        for cid, label, items in cats:
            allowed = "all" in self.entitlements or cid in self.entitlements
            title = label if allowed else f"{label}  🔒 cần gói Pro"
            lf = ttk.LabelFrame(self.items_frame, text=title, padding=(8, 4))
            lf.pack(fill="x", padx=4, pady=3)
            for key, (name, used, limit) in items.items():
                self.item_labels[(cid, key)] = (label, name)
                left = max(limit - used, 0) if allowed else 0
                chk, cnt = old.get((cid, key), (left > 0, left))
                v, c = tk.BooleanVar(value=chk and left > 0), tk.IntVar(value=min(cnt, left) if cnt else left)
                self.vars[(cid, key)] = (v, c)
                row = ttk.Frame(lf)
                row.pack(fill="x")
                ttk.Checkbutton(row, text=name, variable=v, width=34,
                                state="normal" if left > 0 else "disabled").pack(side="left")
                ttk.Label(row, text=f"đã xem {used}/{limit}", width=16).pack(side="left")
                ttk.Label(row, text="số lượt:").pack(side="left")
                ttk.Spinbox(row, from_=0, to=max(left, 1), width=4, textvariable=c,
                            state="normal" if left > 0 else "disabled").pack(side="left", padx=4)
                if not allowed:
                    ttk.Label(row, text="(cần nâng cấp Pro)", foreground="#b35a00").pack(side="left")
                elif left == 0:
                    ttk.Label(row, text="(đã đủ hạn mức)", foreground="#777").pack(side="left")
        if extra:
            lf = ttk.LabelFrame(self.items_frame, text="Có trong game nhưng tool chưa hỗ trợ điều hướng "
                                "(sẽ bổ sung)", padding=(8, 4))
            lf.pack(fill="x", padx=4, pady=3)
            ttk.Label(lf, foreground="#777", text="   ".join(f"{n} {u}/{l}" for n, u, l in extra),
                      wraplength=820).pack(anchor="w")
        self.status.config(text=f"Màn hiện tại: {scene}", foreground="#1a7f37")

    def tick_all(self, on):
        for v, c in self.vars.values():
            if c.get() > 0:
                v.set(on)

    # ---------------------------------------------------------------- hàng đợi bước chạy
    @staticmethod
    def _step_label(step):
        if step["kind"] == "ads":
            return f"QC: {step['cat_label']} › {step['item_label']} ×{step['count']}"
        if step["kind"] == "four_gods":
            return "Tứ thần: xem hết các vị thần đã mở khoá"
        bits = []
        if step["missile"]:
            bits.append("tên lửa")
        if step["mineral"]:
            bits.append("khoáng")
        if step["meteor"]:
            bits.append("thiên thạch")
        if step["chars"]:
            bits.append(f"nv {step['chars']}")
        what = ', '.join(bits) or '(trống)'
        mode = step.get("mode") or ("farm" if step.get("farm") else "single")     # preset cũ không có "mode"
        if mode == "watch":
            return f"Chơi liên tục {step['duration']}s: {what} mỗi {step['interval']:.1f}s"
        if mode == "fixed":
            return (f"Lặp màn {step['stage_num']} ({'Khó' if step.get('hard') else 'Thường'}) "
                    f"×{step['times']}: {what}")
        if mode == "farm":
            return f"Tự cày {step['times']} màn liên tiếp: {what}"
        return f"Tự chơi 1 màn: {what} mỗi {step['interval']:.1f}s"

    def _refresh_queue_list(self):
        self.queue_list.delete(0, "end")
        for i, step in enumerate(self.step_queue, 1):
            self.queue_list.insert("end", f"{i}. {self._step_label(step)}")

    def queue_add_ads(self):
        added = 0
        for (cid, key), (v, c) in self.vars.items():
            if v.get() and c.get() > 0:
                cat_label, item_label = self.item_labels.get((cid, key), (cid, key))
                self.step_queue.append({"kind": "ads", "cid": cid, "key": key, "count": c.get(),
                                        "cat_label": cat_label, "item_label": item_label})
                added += 1
        if not added:
            messagebox.showinfo("Chưa chọn", "Hãy tick ít nhất 1 mục ở khung 'Hạng mục quảng cáo' phía trên.")
            return
        self._refresh_queue_list()
        self.log(f"Đã thêm {added} bước QC vào hàng đợi.")

    def queue_add_stage(self):
        dlg = StageStepDialog(self.root)
        self.root.wait_window(dlg)
        if dlg.result:
            self.step_queue.append(dlg.result)
            self._refresh_queue_list()

    def queue_add_four_gods(self):
        self.step_queue.append({"kind": "four_gods"})
        self._refresh_queue_list()
        self.log("Đã thêm bước Tứ thần vào hàng đợi.")

    def queue_move(self, delta):
        sel = self.queue_list.curselection()
        if not sel:
            return
        i = sel[0]
        j = i + delta
        if 0 <= j < len(self.step_queue):
            self.step_queue[i], self.step_queue[j] = self.step_queue[j], self.step_queue[i]
            self._refresh_queue_list()
            self.queue_list.selection_set(j)

    def queue_remove(self):
        sel = self.queue_list.curselection()
        if sel:
            del self.step_queue[sel[0]]
            self._refresh_queue_list()

    def queue_clear(self):
        self.step_queue = []
        self._refresh_queue_list()

    # ---------------------------------------------------------------- cấu hình đã lưu (preset theo tên)
    @staticmethod
    def _load_presets():
        if PRESETS_FILE.exists():
            try:
                return json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    @staticmethod
    def _save_presets(data):
        PRESETS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def _refresh_preset_list(self):
        names = sorted(self._load_presets().keys())
        self.preset_combo["values"] = names
        if names and not self.preset_combo.get():
            self.preset_combo.set(names[0])

    def preset_save(self):
        if not self.step_queue:
            messagebox.showinfo("Hàng đợi trống", "Thêm ít nhất 1 bước trước khi lưu.")
            return
        name = simpledialog.askstring("Lưu cấu hình", "Đặt tên cho cấu hình này:",
                                      initialvalue=self.preset_combo.get() or "",
                                      parent=self.root)
        name = (name or "").strip()
        if not name:
            return
        data = self._load_presets()
        data[name] = {"steps": self.step_queue, "rand": self.rand.get()}
        self._save_presets(data)
        self._refresh_preset_list()
        self.preset_combo.set(name)
        self.log(f"✓ Đã lưu cấu hình '{name}' ({len(self.step_queue)} bước).")

    def preset_load(self):
        name = self.preset_combo.get()
        data = self._load_presets()
        if not name or name not in data:
            messagebox.showinfo("Chưa chọn", "Chọn 1 cấu hình đã lưu ở ô bên cạnh.")
            return
        self.step_queue = list(data[name]["steps"])
        self.rand.set(data[name].get("rand", True))
        self._refresh_queue_list()
        self.log(f"✓ Đã nạp cấu hình '{name}' ({len(self.step_queue)} bước).")

    def preset_delete(self):
        name = self.preset_combo.get()
        data = self._load_presets()
        if not name or name not in data:
            return
        if not messagebox.askyesno("Xoá cấu hình", f"Xoá cấu hình '{name}'?"):
            return
        del data[name]
        self._save_presets(data)
        self.preset_combo.set("")
        self._refresh_preset_list()
        self.log(f"Đã xoá cấu hình '{name}'.")

    def run_queue(self):
        if not self.client:
            messagebox.showinfo("Chưa đăng nhập", "Hãy đăng nhập trước khi chạy.")
            return
        if not self.step_queue:
            messagebox.showinfo("Hàng đợi trống", "Thêm ít nhất 1 bước trước khi chạy.")
            return
        not_allowed = [s for s in self.step_queue if s["kind"] == "ads"
                       and not ("all" in self.entitlements or s["cid"] in self.entitlements)]
        if not_allowed:
            messagebox.showinfo("Cần gói Pro", "Hàng đợi có bước QC thuộc hạng mục ngoài gói hiện tại.")
            return
        r = self.rand.get()
        self.cfg.update(tap_jitter_px=6 if r else 0, pre_tap_delay=[0.08, 0.35] if r else [0, 0],
                        delay_jitter=0.35 if r else 0)
        self.stop_evt.clear()
        steps = list(self.step_queue)

        def job():
            import engine
            eng = engine.Engine(self.cfg, self.log, should_stop=self.stop_evt.is_set)
            events = []
            for n, step in enumerate(steps, 1):
                if self.stop_evt.is_set():
                    self.log("Đã dừng, bỏ qua các bước còn lại.")
                    break
                self.log(f"──────── Bước {n}/{len(steps)}: {self._step_label(step)} ────────")
                if step["kind"] == "ads":
                    total, results = eng.run([(step["cid"], step["key"], step["count"])])
                    events += [{"type": "category_run", "payload": r2} for r2 in results]
                elif step["kind"] == "four_gods":
                    done = eng.run_four_gods()
                    events.append({"type": "category_run", "payload": {"category": "four_gods", "done": done}})
                elif step.get("mode") == "watch":
                    done = eng.watch_and_play(
                        duration_sec=step["duration"], chars=step["chars"], missile=step["missile"],
                        mineral=step["mineral"], meteor=step["meteor"], interval=step["interval"],
                        repeat=step["repeat"], gap=step["gap"], stage_max_sec=step["max_sec"],
                        watch_result_ad=step.get("watch_result_ad", True))
                    events.append({"type": "stage_watch", "payload": {"rounds": done, **step}})
                elif step.get("mode") == "fixed":
                    done = eng.run_fixed_stage(
                        step["stage_num"], hard=step.get("hard", False), times=step["times"],
                        watch_ads=step.get("watch_result_ad", True), chars=step["chars"],
                        missile=step["missile"], mineral=step["mineral"], meteor=step["meteor"],
                        interval=step["interval"], repeat=step["repeat"], gap=step["gap"],
                        stage_max_sec=step["max_sec"])
                    events.append({"type": "stage_fixed", "payload": {"done": done, **step}})
                elif step.get("farm"):             # preset cũ (checkbox "tự cày" đã bỏ khỏi form)
                    done = eng.farm_stages(
                        times=step["times"], watch_ads=step.get("watch_result_ad", True),
                        chars=step["chars"], missile=step["missile"], mineral=step["mineral"],
                        meteor=step["meteor"], interval=step["interval"], repeat=step["repeat"],
                        gap=step["gap"], stage_max_sec=step["max_sec"],
                        wait_entry_sec=step.get("wait_entry_sec", 60))
                    events.append({"type": "farm_stages", "payload": {"done": done, **step}})
                else:
                    rounds = eng.auto_play_stage(
                        chars=step["chars"], missile=step["missile"], mineral=step["mineral"],
                        meteor=step["meteor"], interval=step["interval"], repeat=step["repeat"],
                        gap=step["gap"], max_sec=step["max_sec"],
                        wait_entry_sec=step.get("wait_entry_sec", 60),
                        watch_result_ad=step.get("watch_result_ad", True))
                    events.append({"type": "stage_autoplay", "payload": {"rounds": rounds, **step}})
            try:
                events.append({"type": "app_stop", "payload": {"queue_len": len(steps)}})
                self.client.send_events(events)
            except Exception:
                pass
            self._load_items()
        self.log("════════ Chạy hàng đợi ════════")
        self._thread(job)

    # ---------------------------------------------------------------- log / hàng đợi
    def log(self, msg):
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        self.q.put(("log", line))
        try:
            with open(self.logfile, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def ui(self, fn, *args):
        self.q.put(("ui", (fn, args)))

    def pump(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "log":
                    tag = ("warn" if "⚠" in data else "head" if "▶" in data else "ok" if "✓" in data else "")
                    self.logbox.config(state="normal")
                    self.logbox.insert("end", data + "\n", tag)
                    self.logbox.see("end")
                    self.logbox.config(state="disabled")
                else:
                    fn, args = data
                    fn(*args)
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def set_busy(self, busy):
        self.busy = busy
        self.btn_start.config(state="disabled" if busy else "normal")
        self.btn_run_queue.config(state="disabled" if busy else "normal")
        self.btn_refresh.config(state="disabled" if busy else "normal")
        self.btn_stop.config(state="normal" if busy else "disabled")

    # ---------------------------------------------------------------- hành động
    def _thread(self, fn):
        def run():
            try:
                fn()
            except Exception as e:                      # lỗi bất ngờ: báo trên log, không treo giao diện
                self.log(f"⚠ Lỗi: {e}")
                tb = traceback.format_exc(limit=3).strip()
                self.log(tb)
                if self.client:
                    try:
                        self.client.send_error(str(e), tb)
                    except Exception:
                        pass
            finally:
                self.ui(self.set_busy, False)
        self.set_busy(True)
        threading.Thread(target=run, daemon=True).start()

    # ---------------------------------------------------------------- tài khoản / server
    def _ensure_auth(self):
        try:
            self._ensure_auth_impl()
        except Exception as e:                           # app --windowed không có console: đừng để lỗi biến mất
            self.log(f"⚠ Lỗi màn đăng nhập: {e}")
            self.log(traceback.format_exc(limit=4).strip())

    def _ensure_auth_impl(self):
        import server_client
        tok = server_client.load_tokens()
        if tok:
            try:
                r = server_client.refresh_access(tok["server_url"], tok["refresh_token"])
                server_client.save_tokens(tok["server_url"], r["access_token"], tok["refresh_token"],
                                          r["entitlements"], r["plan"], tok.get("email", ""))
                self._set_account(tok["server_url"], r["access_token"], tok["refresh_token"],
                                  r["entitlements"], r["plan"], tok.get("email", "?"), r["session_id"])
                self.log(f"✓ Đã đăng nhập lại tự động (gói {r['plan']})")
                return
            except server_client.ApiError as e:
                if e.status == 409:
                    self.log(f"⚠ {e.detail} — tự đăng nhập lại bị chặn, mở màn đăng nhập để bạn quyết định.")
                else:
                    self.log(f"(phiên đăng nhập cũ hết hạn hoặc lỗi: {e.detail} — đăng nhập lại)")
                server_client.clear_tokens()
        dlg = LoginDialog(self.root, self.cfg.get("server_url", "http://127.0.0.1:8000"))
        self.root.wait_window(dlg)
        if not dlg.result:
            self.log("⚠ Chưa đăng nhập — đóng ứng dụng.")
            self.root.destroy()
            return
        r = dlg.result
        self._set_account(dlg.server.get().strip(), r["access_token"], r["refresh_token"],
                          r["entitlements"], r["plan"], r.get("email", dlg.email.get().strip()),
                          r["session_id"])
        self.log(f"✓ Đăng nhập thành công: {self.account_email} (gói {r['plan']})")

    def _set_account(self, server_url, access, refresh, entitlements, plan, email, session_id):
        import server_client
        self.client = server_client.Client(server_url, access, refresh, session_id)
        self.entitlements, self.plan, self.account_email = entitlements, plan, email
        self.cfg["server_url"] = server_url
        self.account_label.config(text=f"{email} · {plan.upper()}", foreground="#1a7f37")
        self._session_id = session_id
        self._hb_stop = threading.Event()
        self._start_heartbeat(session_id, self._hb_stop)     # 1 máy đăng nhập tại 1 thời điểm: giữ phiên
        if self.vars:                                         # sống suốt lúc mở app, không chỉ lúc Bắt đầu
            self.refresh()

    def logout(self):
        import server_client
        if not self.client:
            return
        if self.busy:
            messagebox.showinfo("Đang chạy", "Dừng tool trước khi đăng xuất.")
            return
        if self._hb_stop:
            self._hb_stop.set()
        try:
            server_client.logout(self.client.server_url, self.client.refresh_token, self._session_id)
        except Exception:
            pass
        self.client, self.entitlements, self.plan, self.account_email = None, [], "free", None
        self._session_id = None
        self.account_label.config(text="chưa đăng nhập", foreground="#777")
        self.log("Đã đăng xuất.")
        self._ensure_auth()

    def connect(self):
        self.cfg["serial"] = self.dev.get().strip() or self.cfg["serial"]

        def job():
            adb = a.Adb(self.cfg)
            self.log(f"adb: {adb.path}")
            adb.connect()
            devs = adb.devices()
            if self.cfg["serial"] not in devs:
                self.log("Quét các cổng BlueStacks thường gặp…")
                devs = adb.scan_bluestacks()
            if not devs:
                self.ui(lambda: self.status.config(text="Không thấy thiết bị adb", foreground="#a00"))
                self.log("⚠ Không thấy thiết bị. Kiểm tra BlueStacks đã bật ADB (Cài đặt → Nâng cao) và đang chạy.")
                return
            if self.cfg["serial"] not in devs:
                self.cfg["serial"] = devs[0]
            self.ui(lambda: self.dev.config(values=devs))
            self.ui(self.dev.set, self.cfg["serial"])
            self.log(f"✓ Thiết bị: {self.cfg['serial']}")
            self._load_items()
        self._thread(job)

    def refresh(self):
        self._thread(self._load_items)

    def _load_items(self):
        import engine
        eng = engine.Engine(self.cfg, self.log)
        res = eng.list_items()
        if not res:
            self.ui(lambda: self.status.config(text="Không đọc được game", foreground="#a00"))
            self.log("⚠ Không đọc được trạng thái game. Hãy mở game El Dorado (tới màn hình chính) rồi bấm 'Làm mới'.")
            return
        scene, cats, extra = res
        self.ui(self.populate, scene, cats, extra)
        self.log(f"✓ Đã đọc hạn mức từ game (màn: {scene})")

    def start(self):
        if not self.client:
            messagebox.showinfo("Chưa đăng nhập", "Hãy đăng nhập trước khi chạy.")
            return
        plan = [(cid, key, c.get()) for (cid, key), (v, c) in self.vars.items() if v.get() and c.get() > 0
                and ("all" in self.entitlements or cid in self.entitlements)]
        if not plan:
            messagebox.showinfo("Chưa chọn", "Hãy tick ít nhất 1 mục (được gói hiện tại cho phép) và đặt số lượt > 0.")
            return
        r = self.rand.get()
        self.cfg.update(tap_jitter_px=6 if r else 0, pre_tap_delay=[0.08, 0.35] if r else [0, 0],
                        delay_jitter=0.35 if r else 0)
        self.stop_evt.clear()

        def job():
            import engine
            eng = engine.Engine(self.cfg, self.log, should_stop=self.stop_evt.is_set)
            total, results = eng.run(plan)
            try:
                events = [{"type": "category_run", "payload": r2} for r2 in results]
                events.append({"type": "app_stop", "payload": {"total_ads": total}})
                self.client.send_events(events)
            except Exception:
                pass
            self._load_items()
        self.log("──────── Bắt đầu ────────")
        self._thread(job)

    def _start_heartbeat(self, session_id, stop_evt):
        def loop():
            while not stop_evt.is_set():
                try:
                    self.client.heartbeat(session_id)
                except Exception as e:
                    self.log(f"(nhịp tim lỗi, bỏ qua: {e})")
                stop_evt.wait(HEARTBEAT_SEC)
        threading.Thread(target=loop, daemon=True).start()

    def stop(self):
        self.stop_evt.set()
        self.log("Đang dừng… (sau thao tác hiện tại)")
        self.btn_stop.config(state="disabled")

    def on_close(self):
        if self.busy and not messagebox.askyesno("Đang chạy", "Tool đang chạy. Dừng và thoát?"):
            return
        self.stop_evt.set()
        if self._hb_stop:
            self._hb_stop.set()
        if self.client and self._session_id:                 # cố gắng trả phiên trước khi thoát (best-effort)
            try:
                self.client.release(self._session_id)
            except Exception:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

