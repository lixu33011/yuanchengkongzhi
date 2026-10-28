import os, subprocess, logging
from http.server import HTTPServer, BaseHTTPRequestHandler

# ---------- 配置区 ----------
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 2211
TOKEN = "your_token_here"  # 建议改强密码，访问需 ?token=xxx

LOG_FILE = "/var/log/fn_http_ctrl.log"
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s %(message)s')
log = logging.info

# 关机/重启时优先优雅停止
CONTAINERS_CTRL = ["moontv-core", "moontv-kvrocks"]

# 动态路由白名单（全量加入当前7个容器）
ALLOWED_DYN_CONTAINERS = {
    "moontv-core", "moontv-kvrocks", "omnibox", "lxserver",
    "iptv", "iptv-api", "migu1"
}

# ---------- Docker 操作 ----------
def docker_op(action, cname):
    cmd = ["docker", action, cname]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=30).decode("utf-8", "ignore").strip()
        return True, out
    except subprocess.CalledProcessError as e:
        msg = e.output.decode("utf-8", "ignore").strip()
        if "already running" in msg or "is already" in msg:
            return True, msg
        return False, msg
    except Exception as e:
        return False, str(e)

def ensure_running(cname):
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", cname], capture_output=True, text=True)
    if r.returncode != 0:
        return False, f"容器 {cname} 不存在"
    status = r.stdout.strip()
    if status in ("running", "restarting"):
        return True, f"{cname} 已在运行"
    return docker_op("start", cname)

def graceful_stop_ctrl():
    for c in CONTAINERS_CTRL:
        ok, msg = docker_op("stop", c)
        log(f"CTRL-STOP {c} ok={ok} msg={msg}")

# ---------- 路由判断 ----------
def check_token(path_query):
    if not TOKEN: return True
    q = path_query.split("?", 1)[-1] if "?" in path_query else ""
    return f"token={TOKEN}" in q

def is_dyn_route(path_only):
    if path_only in ("/", "/gj", "/cq"): return False
    name = path_only.lstrip("/")
    if name.endswith("-stop"): return False
    return name in ALLOWED_DYN_CONTAINERS

# ---------- HTML 首页 ----------
def render_home():
    buttons = []
    for x in sorted(ALLOWED_DYN_CONTAINERS):
        buttons.append(f'<button onclick="act(\'/{x}\')">▶ {x}</button>')
        buttons.append(f'<button onclick="act(\'/{x}-stop\')">■ {x}-stop</button>')
    btns_html = "<br>".join(buttons)

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>FnOS Ctrl</title>
<style>
  body{{font-family:system-ui,sans-serif;margin:20px;background:#f5f5f5}}
  .box{{background:#fff;padding:15px;border-radius:8px;margin-bottom:15px;box-shadow:0 2px 4px #0001}}
  button{{margin:4px;padding:6px 10px;cursor:pointer;border:1px solid #aaa;background:#eee;border-radius:4px}}
  button:hover{{background:#ddd}}
  #log{{height:160px;overflow-y:scroll;background:#111;color:#0f0;padding:10px;font-size:13px;font-family:monospace;border-radius:6px}}
  .danger button{{background:#fee}}
</style></head>
<body>
<div class="box danger">
  <b>系统控制：</b><br>
  <button onclick="act('/cq')">🔄 重启</button>
  <button onclick="act('/gj')">⏻ 关机</button>
</div>
<div class="box">
  <b>容器控制（点击测试，自动扩展）：</b><br>{btns_html}
</div>
<div class="box">
  <b>信息回显：</b>
  <div id="log"></div>
</div>
<script>
function act(url){{
  fetch(url).then(r=>r.text()).then(t=>{{
    var d=new Date().toLocaleTimeString();
    document.getElementById('log').innerHTML += d+' > '+url+'\\n'+t+'\\n\\n';
    document.getElementById('log').scrollTop=99999;
  }});
}}
</script></body></html>"""

# ---------- HTTP Handler ----------
class Handler(BaseHTTPRequestHandler):
    def _resp(self, code, txt, html=False):
        self.send_response(code)
        ct = "text/html; charset=utf-8" if html else "text/plain; charset=utf-8"
        self.send_header("Content-Type", ct)
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(f"{txt}\n".encode())

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/":
            self._resp(200, render_home(), html=True)
            return

        if not check_token(self.path):
            self._resp(403, "403 Forbidden: bad token")
            log(f"REJECT {self.client_address[0]} {self.path}")
            return

        if path == "/gj":
            log(f"SHUTDOWN by {self.client_address[0]}")
            graceful_stop_ctrl()
            subprocess.Popen(["/sbin/shutdown", "-h", "now"])
            self._resp(200, "shutting down in 3s...")
            return

        if path == "/cq":
            log(f"REBOOT by {self.client_address[0]}")
            graceful_stop_ctrl()
            subprocess.Popen(["/sbin/reboot"])
            self._resp(200, "rebooting in 3s...")
            return

        if path.endswith("-stop"):
            raw_name = path.lstrip("/").replace("-stop", "")
            if raw_name not in ALLOWED_DYN_CONTAINERS:
                self._resp(404, f"未知容器路由: {raw_name}")
                return
            ok, msg = docker_op("stop", raw_name)
            self._resp(200, f"{raw_name}-stop: {msg}")
            log(f"STOP {raw_name} ok={ok}")
            return

        if is_dyn_route(path):
            cname = path.lstrip("/")
            ok, msg = ensure_running(cname)
            self._resp(200, f"{cname}: {msg}")
            log(f"DYN-START {cname} by {self.client_address[0]} ok={ok}")
            return

        self._resp(404, "404: unknown route. 访问 / 看帮助")

    def log_message(self, fmt, *args):
        log(f"ACCESS {args[0]}")

# ---------- Main ----------
if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    log(f"FnOS HTTP Ctrl listening on :{LISTEN_PORT}")
    srv = HTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("server stopped")
