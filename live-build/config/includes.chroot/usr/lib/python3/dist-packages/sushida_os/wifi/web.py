"""HTTP setup service layer for the Wi-Fi setup backend.

Owns the loopback HTTP handler, CSRF/Origin/Fetch-Metadata validation,
request parsing and limits, the HTML templates (the connecting-page script
is authorized by exact CSP hash), and the read-only /status.json endpoint.
Existing HTTP statuses and HTML bytes are moved verbatim; the connection
activation still starts only after the response is flushed.

Collaborator names are imported from their defining modules; the
characterization-test loader mirrors monkeypatch writes into every module
namespace that holds the name, so these from-imports stay patchable.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from sushida_os.wifi.coordinator import (
    connect_status,
    consume_failure,
    enqueue_interactive,
    reset_succeeded,
    start_queued_connection,
)
from sushida_os.wifi.nmcli import network_connected, scan_networks
from sushida_os.wifi.storage import csrf_token, persistent_storage_ready
from sushida_os.wifi.types import (
    CONNECT_FAILED,
    CONNECT_SUCCEEDED,
    CONNECT_WORKING,
    validate_credentials,
)

HOST = "127.0.0.1"
PORT = 8787
ORIGIN = f"http://{HOST}:{PORT}"
MAX_REQUEST_BYTES = 8192
REQUEST_READ_TIMEOUT_SECONDS = 5


def render_page(message: str = "", success: bool = False) -> bytes:
    # A successful nmcli activation has already waited for NetworkManager.
    # Return the acknowledgement immediately instead of issuing another
    # forced scan while the route watcher prepares the kiosk transition.
    connected = success or network_connected()
    storage_ready = persistent_storage_ready()
    # The launcher and this request can observe different NetworkManager
    # states while a link is coming up.  A wired or local-only connection also
    # must not prevent the user from provisioning Wi-Fi, so always scan and
    # keep the form interactive.
    networks = [] if success else scan_networks()
    network_choices: list[str] = []
    for ssid, signal, security in networks:
        escaped_ssid = html.escape(ssid, quote=True)
        details = f"電波 {signal}% — {security or 'オープン'}"
        network_choices.append(
            '<label class="network">'
            f'<input type="radio" name="ssid" value="{escaped_ssid}" required>'
            '<span>'
            f'<strong>{html.escape(ssid)}</strong>'
            f'<small>{html.escape(details)}</small>'
            '</span></label>'
        )
    if success:
        network_list = (
            '<p class="success">接続が完了しました。寿司打画面への切り替えを待っています。</p>'
        )
    elif network_choices:
        network_list = "".join(network_choices)
    else:
        network_list = '<p class="empty">Wi-Fiネットワークが見つかりません。再スキャンしてください。</p>'
    status = "有線またはWi-Fiで接続済みです。" if connected else "ネットワーク未接続です。"
    if not storage_ready:
        status += " 設定保存領域を利用できないため、この起動中だけ接続できます。"
    alert = ""
    if message:
        alert_class = "success" if success else "error"
        alert = f'<p class="{alert_class}">{html.escape(message)}</p>'
    submit_disabled = " disabled" if not networks else ""
    submit_label = "接続して保存" if storage_ready else "この起動中だけ接続"
    persistence_note = (
        "設定はこの端末の専用領域に保存されます。"
        if storage_ready
        else "この起動中は接続できますが、設定は再起動後に残りません。"
    )
    csrf = html.escape(csrf_token(), quote=True)
    document = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ネットワーク設定</title>
<style>
html,body{{margin:0;min-height:100%;background:#111;color:#f4f4f4;font-family:sans-serif}}
main{{max-width:720px;margin:0 auto;padding:7vh 6vw}}h1{{font-size:2rem}}
form{{display:grid;gap:1rem}}label{{display:grid;gap:.4rem}}
input,button{{font:inherit;padding:.8rem;border-radius:.4rem;border:1px solid #777}}
button{{background:#fff;color:#111;font-weight:bold}}.error{{color:#ff9b9b}}.success{{color:#9bffb1}}
.networks{{border:0;margin:0;padding:0;display:grid;gap:.65rem}}
.networks legend{{font-weight:bold;margin-bottom:.6rem}}
.network{{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:.8rem;
padding:.85rem;border:1px solid #777;border-radius:.5rem;background:#222;cursor:pointer}}
.network:has(input:checked){{border-color:#fff;background:#3a3a3a}}
.network input{{width:1.35rem;height:1.35rem;margin:0}}
.network span{{display:grid;gap:.2rem}}.network strong{{overflow-wrap:anywhere}}
.network small,.note,.empty{{color:#bbb}}.empty{{margin:.2rem 0}}
.note{{font-size:.9rem}}
</style></head><body><main><h1>ネットワーク設定</h1>
<p>{html.escape(status)}</p>{alert}
<form method="post" action="/connect">
<input type="hidden" name="csrf" value="{csrf}">
<fieldset class="networks"><legend>Wi-Fiネットワークを選択</legend>{network_list}</fieldset>
<label>パスワード<input name="password" type="password" maxlength="64" autocomplete="new-password"></label>
<button type="submit"{submit_disabled}>{submit_label}</button></form>
<form method="get" action="/"><button type="submit">再スキャン</button></form>
<p class="note">有線LANが接続されると自動的に寿司打画面へ移動します。{persistence_note}</p>
</main></body></html>"""
    return document.encode("utf-8")


# Client-side poller for the connecting page.  fetch() failures caused by a
# network interface change are invisible to the user, unlike a navigation:
# the document never leaves the connecting page, so no browser error page can
# appear.  The exact bytes below are hashed into the page's Content-Security-
# Policy header; keep them in sync by always rendering through
# render_connecting_page().
CONNECTING_SCRIPT = """(function () {
  var statusLine = document.getElementById("connect-status");
  var errors = 0;
  var rounds = 0;
  function say(text) {
    if (statusLine) {
      statusLine.textContent = text;
    }
  }
  function poll() {
    rounds += 1;
    if (rounds > 160) {
      location.reload();
      return;
    }
    fetch("/status.json", { cache: "no-store" }).then(function (response) {
      if (!response.ok) {
        throw new Error("status");
      }
      return response.json();
    }).then(function (data) {
      errors = 0;
      if (data.state === "connecting") {
        setTimeout(poll, 1500);
      } else if (data.state === "succeeded") {
        say(data.message || "接続しました。寿司打画面へ切り替えます。");
      } else {
        location.reload();
      }
    }).catch(function () {
      errors += 1;
      if (errors > 40) {
        location.reload();
        return;
      }
      setTimeout(poll, 1500);
    });
  }
  setTimeout(poll, 1200);
}());
"""


def script_csp_hash() -> str:
    digest = hashlib.sha256(CONNECTING_SCRIPT.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def render_connecting_page(busy: bool = False) -> bytes:
    notice = (
        "別の接続処理がすでに実行中です。そのままお待ちください。"
        if busy
        else "Wi-Fi接続処理を実行しています。そのままお待ちください。"
    )
    document = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ネットワーク設定</title>
<style>
html,body{{margin:0;min-height:100%;background:#111;color:#f4f4f4;font-family:sans-serif}}
main{{max-width:720px;margin:0 auto;padding:7vh 6vw}}h1{{font-size:2rem}}
.note{{font-size:.9rem;color:#bbb}}
</style></head><body><main><h1>ネットワーク設定</h1>
<p id="connect-status">{notice}</p>
<p class="note">接続に成功すると自動的に寿司打の画面へ切り替わります。失敗した場合は設定画面へ戻ります。</p>
<noscript><p class="note">しばらく待ってからこの画面を再読み込みしてください。</p></noscript>
<script>{CONNECTING_SCRIPT}</script>
</main></body></html>"""
    return document.encode("utf-8")


class SetupHandler(BaseHTTPRequestHandler):
    server_version = "SushidaSetup/1"
    sys_version = ""

    def setup(self) -> None:
        super().setup()
        # The server is deliberately single-threaded.  Bound partial request
        # reads so one abandoned loopback POST cannot block every rescan.
        self.connection.settimeout(REQUEST_READ_TIMEOUT_SECONDS)

    def _headers(
        self,
        status_code: HTTPStatus,
        length: int,
        script_hash: str | None = None,
    ) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        script_src = f"; script-src 'sha256-{script_hash}'" if script_hash else ""
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'unsafe-inline'; form-action 'self'; "
            "frame-ancestors 'none'; base-uri 'none'" + script_src,
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        # Keep same-origin form navigation metadata available to Chromium so
        # its POST carries the exact loopback Origin checked below.  A
        # no-referrer policy turns that Origin into the literal value "null".
        self.send_header("Referrer-Policy", "same-origin")
        self.end_headers()

    def _reply(self, body: bytes, status_code: HTTPStatus = HTTPStatus.OK) -> None:
        self._headers(status_code, len(body))
        self.wfile.write(body)

    def _reply_connecting(
        self, busy: bool, status_code: HTTPStatus = HTTPStatus.OK
    ) -> None:
        body = render_connecting_page(busy)
        self._headers(status_code, len(body), script_csp_hash())
        self.wfile.write(body)
        self.wfile.flush()

    def _reply_status(self) -> None:
        # Read-only, loopback-only, and free of SSIDs and credentials.
        state, message = connect_status()
        body = json.dumps(
            {"state": state, "message": message}, ensure_ascii=False
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(body)

    def _redirect_home(self) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def _setup_error(self, message: str, status_code: HTTPStatus) -> None:
        self._reply(render_page(message), status_code)

    def _allowed_browser_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if origin == ORIGIN:
            return True
        if origin is not None:
            return False
        # Chromium normally sends Origin on POST.  If it omits Origin, accept
        # only its same-origin Fetch Metadata plus the fixed loopback Host.
        return (
            self.headers.get("Host") == f"{HOST}:{PORT}"
            and self.headers.get("Sec-Fetch-Site") == "same-origin"
        )

    def _log_rejection(self, reason: str) -> None:
        del reason
        print("wifi-setup: stage=http-reject nmcli_exit=0 reason=0", flush=True)

    def do_GET(self) -> None:  # noqa: N802
        target = urlsplit(self.path)
        if target.path == "/status.json":
            self._reply_status()
            return
        if target.path not in ("/", "/rescan"):
            # Never strand a kiosk user on a plain browser error page.
            self._redirect_home()
            return
        state, message = connect_status()
        if state == CONNECT_WORKING:
            # A rescan or manual reload while the worker runs must not issue
            # another nmcli scan or show the form again.
            self._reply_connecting(busy=False)
            return
        if state == CONNECT_FAILED:
            self._reply(render_page(consume_failure() or ""))
            return
        if state == CONNECT_SUCCEEDED:
            if network_connected():
                self._reply(render_page(message, success=True))
                return
            # The network was lost again before the kiosk switched routes;
            # show the normal form instead of a stale success message.
            reset_succeeded()
        self._reply(render_page())

    def do_POST(self) -> None:  # noqa: N802
        target = urlsplit(self.path)
        if target.path != "/connect" or target.query or target.fragment:
            self._redirect_home()
            return
        if not self._allowed_browser_origin():
            self._log_rejection("origin")
            self._setup_error(
                "ブラウザからの接続要求を検証できませんでした。設定画面から再送信してください。",
                HTTPStatus.FORBIDDEN,
            )
            return
        if self.headers.get_content_type() != "application/x-www-form-urlencoded":
            self._log_rejection("content-type")
            self._setup_error(
                "接続要求の形式が不正です。もう一度入力してください。",
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            )
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = -1
        if length < 1 or length > MAX_REQUEST_BYTES:
            self._log_rejection("content-length")
            self._setup_error(
                "接続要求が大きすぎます。もう一度入力してください。",
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return
        try:
            request_body = self.rfile.read(length)
        except OSError:
            self._log_rejection("request-timeout")
            self._setup_error(
                "接続要求の受信がタイムアウトしました。もう一度入力してください。",
                HTTPStatus.BAD_REQUEST,
            )
            return
        if len(request_body) != length:
            self._log_rejection("incomplete-body")
            self._setup_error(
                "接続要求を最後まで受信できませんでした。もう一度入力してください。",
                HTTPStatus.BAD_REQUEST,
            )
            return
        try:
            form = parse_qs(
                request_body.decode("utf-8"),
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=4,
            )
        except (UnicodeError, ValueError):
            self._log_rejection("form-encoding")
            self._setup_error(
                "接続要求を読み取れませんでした。もう一度入力してください。",
                HTTPStatus.BAD_REQUEST,
            )
            return
        token = form.get("csrf", [""])
        ssid = form.get("ssid", [""])
        password = form.get("password", [""])
        if not all(len(item) == 1 for item in (token, ssid, password)):
            self._log_rejection("form-fields")
            self._setup_error(
                "接続要求の項目が不正です。もう一度入力してください。",
                HTTPStatus.BAD_REQUEST,
            )
            return
        if not hmac.compare_digest(token[0], csrf_token()):
            self._log_rejection("csrf")
            self._setup_error(
                "設定画面の有効期限が切れました。画面を再読み込みして再送信してください。",
                HTTPStatus.FORBIDDEN,
            )
            return
        validation_error = validate_credentials(ssid[0], password[0])
        if validation_error:
            self._setup_error(validation_error, HTTPStatus.OK)
            return
        if not enqueue_interactive(ssid[0], password[0]):
            # A restore thread is still running.  The credential has been
            # saved as pending-interactive; the worker will run it as soon
            # as the current attempt finishes.
            self._reply_connecting(busy=True, status_code=HTTPStatus.CONFLICT)
        else:
            self._reply_connecting(busy=False)
        start_queued_connection()

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        del code, size
        print("wifi-setup: stage=http-request nmcli_exit=0 reason=0", flush=True)

    def log_message(self, message_format: str, *args: object) -> None:
        # Never copy request details or credentials into diagnostics.
        del message_format, args
        print("wifi-setup: stage=http-server nmcli_exit=0 reason=0", flush=True)
