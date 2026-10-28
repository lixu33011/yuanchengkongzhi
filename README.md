# 远程控制工具
## 可以远程控制服务器的关机/重启/启动/停止工具
## 也可控制docker容器的启停
首页现包含一键控制按钮（关机/重启/启动/停止）及底部实时信息回显框。

核心改动说明

动态按钮生成：根目录 / 自动渲染 moontv-core、iptv、migu1 等 7 个容器的启动/停止按钮。

信息回显框：点击按钮后通过 JS fetch 调用原 API（如 /iptv、/migu1-stop），结果实时打印在底部 <div id="log">。

易扩展：只需修改 ALLOWED_DYN_CONTAINERS，页面按钮自动增减。

API 兼容：保留纯文本接口（curl 调用不变），仅首页返回 HTML。
#部署命令：
# 赋权
chmod +x /vol1/1000/scripts/fn_http_ctrl.py

# 杀旧进程
pkill -f fn_http_ctrl.py
sleep 2

# 启动
nohup python3 /vol1/1000/scripts/fn_http_ctrl.py >> /var/log/fn_http_ctrl.log 2>&1 &

# 验证
ss -lntp | grep 2211
curl http://127.0.0.1:2211/
