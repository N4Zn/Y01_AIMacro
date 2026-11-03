"""Client gọi server EduXplore Ad Helper (server/) từ gui_app.py. Dùng urllib có sẵn, không thêm thư viện
vào bản đóng gói exe. Token lưu cục bộ ở APP_DIR/auth.json, mã hoá nhẹ (XOR+base64) — chỉ để tránh mở
bằng notepad, không phải mật mã mạnh (xem SERVER_DESIGN.md mục 6: không chặn được người quyết tâm).
"""
import base64
import hashlib
import json
import platform
import subprocess
import urllib.error
import urllib.request

import ad_autoplayer as a

AUTH_FILE = a.APP_DIR / "auth.json"
LAST_LOGIN_FILE = a.APP_DIR / "last_login.json"     # email luôn nhớ (chữ rõ); mật khẩu kèm theo, mã hoá nhẹ,
_XOR_KEY = b"EduXploreAdHelper-local-token-2026"    # chỉ khi còn tick "Ghi nhớ đăng nhập" — sống sót qua logout


def _xor(data: bytes) -> bytes:
    return bytes(b ^ _XOR_KEY[i % len(_XOR_KEY)] for i, b in enumerate(data))


def save_last_login(server_url, email, password=None):
    """Nhớ email/máy chủ (và mật khẩu nếu password không None) để tự điền lại ô đăng nhập lần sau — sống sót
    qua Đăng xuất (khác với token phiên, vốn bị Đăng xuất xoá có chủ đích). Mật khẩu mã hoá nhẹ (XOR+base64,
    cùng mức với auth.json — không phải mật mã mạnh, xem SERVER_DESIGN.md mục 6); password=None thì xoá
    mật khẩu đã lưu (giữ lại email)."""
    data = {"server_url": server_url, "email": email}
    if password:
        data["password_enc"] = base64.b64encode(_xor(password.encode("utf-8"))).decode("ascii")
    try:
        LAST_LOGIN_FILE.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def load_last_login():
    """{"server_url", "email", "password"} (password rỗng nếu chưa từng lưu / đã bỏ tick Ghi nhớ)."""
    try:
        data = json.loads(LAST_LOGIN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    pw_enc = data.pop("password_enc", None)
    data["password"] = _xor(base64.b64decode(pw_enc)).decode("utf-8") if pw_enc else ""
    return data


def save_tokens(server_url, access_token, refresh_token, entitlements, plan, email=""):
    blob = json.dumps({"server_url": server_url, "access_token": access_token, "refresh_token": refresh_token,
                        "entitlements": entitlements, "plan": plan, "email": email}).encode("utf-8")
    AUTH_FILE.write_bytes(base64.b64encode(_xor(blob)))


def load_tokens():
    if not AUTH_FILE.exists():
        return None
    try:
        return json.loads(_xor(base64.b64decode(AUTH_FILE.read_bytes())))
    except Exception:
        return None


def clear_tokens():
    try:
        AUTH_FILE.unlink()
    except FileNotFoundError:
        pass


def device_fingerprint() -> str:
    """Băm MachineGuid (Windows) + tên máy -> mã ổn định; chỉ gửi mã băm lên server, không gửi thông tin thô.
    Bền hơn MAC (không đổi theo card mạng ảo); chỉ dùng để log/chẩn đoán, KHÔNG dùng để giới hạn số máy
    (khoá thật là theo tài khoản game — SERVER_DESIGN.md mục 4)."""
    raw = platform.node()
    try:
        out = subprocess.run(["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"],
                              capture_output=True, text=True, timeout=5, creationflags=a.NOWIN)
        for line in out.stdout.splitlines():
            if "MachineGuid" in line:
                raw += line.strip().split()[-1]
    except Exception:
        pass
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class ApiError(Exception):
    def __init__(self, status, detail):
        self.status, self.detail = status, detail
        super().__init__(f"{status}: {detail}")


def _request(method, server_url, path, body=None, token=None, timeout=10):
    req = urllib.request.Request(
        server_url.rstrip("/") + path, method=method,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        try:
            detail = json.loads(detail).get("detail", detail)
        except Exception:
            pass
        raise ApiError(e.code, detail)
    except urllib.error.URLError as e:
        raise ApiError(0, f"không kết nối được server ({server_url}): {e.reason}")


def register(server_url, email, password):
    return _request("POST", server_url, "/auth/register", {"email": email, "password": password})


def login(server_url, email, password, remember=True):
    r = _request("POST", server_url, "/auth/login",
                 {"email": email, "password": password, "device_fingerprint": device_fingerprint()})
    # nhớ email luôn; nhớ cả mật khẩu (để bấm Đăng nhập là vào ngay) chỉ khi còn tick "Ghi nhớ đăng nhập"
    save_last_login(server_url, email, password if remember else None)
    if remember:
        save_tokens(server_url, r["access_token"], r["refresh_token"], r["entitlements"], r["plan"], email)
    else:
        clear_tokens()                   # không ghi nhớ: xoá token cũ (nếu có) để lần sau phải đăng nhập lại
    r["email"] = email
    return r


def refresh_access(server_url, refresh_token):
    """Làm mới access token; CŨNG chiếm lại khoá 1-máy-1-lúc (đi qua /auth/refresh thay vì /auth/login khi
    tool tự đăng nhập lại lúc mở app) — máy khác đang đăng nhập thì lỗi 409, đúng như lúc /login."""
    return _request("POST", server_url, "/auth/refresh",
                    {"refresh_token": refresh_token, "device_fingerprint": device_fingerprint()})


def logout(server_url, refresh_token, session_id=None):
    try:
        _request("POST", server_url, "/auth/logout",
                 {"refresh_token": refresh_token, "session_id": session_id})
    except ApiError:
        pass
    clear_tokens()


class Client:
    """1 phiên API đã đăng nhập; tự làm mới access token (401) bằng refresh token khi hết hạn."""

    def __init__(self, server_url, access_token, refresh_token, session_id=None):
        self.server_url, self.access_token, self.refresh_token = server_url, access_token, refresh_token
        self.session_id = session_id

    def _call(self, method, path, body=None):
        try:
            return _request(method, self.server_url, path, body, token=self.access_token)
        except ApiError as e:
            if e.status != 401:
                raise
            r = refresh_access(self.server_url, self.refresh_token)
            self.access_token = r["access_token"]
            return _request(method, self.server_url, path, body, token=self.access_token)

    def heartbeat(self, session_id):
        self._call("POST", "/session/heartbeat", {"session_id": session_id})

    def release(self, session_id):
        self._call("POST", "/session/release", {"session_id": session_id})

    def send_events(self, events):
        if events:
            self._call("POST", "/telemetry/events",
                       {"device_fingerprint": device_fingerprint(), "events": events})

    def send_error(self, message, traceback_str=""):
        self._call("POST", "/telemetry/error",
                   {"message": message, "traceback": traceback_str, "device_fingerprint": device_fingerprint()})

    def latest_release(self, channel="stable"):
        return self._call("GET", f"/releases/latest?channel={channel}")
