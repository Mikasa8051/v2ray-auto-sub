import base64
import json
import re
import urllib.parse

PROTOCOL_PATTERN = re.compile(
    r'((?:vmess|vless|ss|trojan|hy2|hysteria2|tuic)://[^\s<>"\'`]+)',
    re.IGNORECASE
)

def extract_nodes(raw_text: str) -> list[str]:
    matches = PROTOCOL_PATTERN.findall(raw_text)
    return [m.strip() for m in matches if len(m.strip()) > 10]

def parse_node_to_singbox_outbound(uri: str) -> dict | None:
    """精准解析 URI 字符串并转换为 sing-box 1.8+ 标准 outbound 配置"""
    try:
        uri = uri.strip()
        scheme = uri.split("://")[0].lower()

        if scheme == "vmess":
            b64_part = uri[8:].split("#")[0]
            decoded = safe_b64decode_str(b64_part)
            data = json.loads(decoded)
            outbound = {
                "type": "vmess",
                "tag": "proxy",
                "server": str(data.get("add", "")).strip(),
                "server_port": int(data.get("port", 0)),
                "uuid": str(data.get("id", "")).strip(),
                "security": "auto",
                "alter_id": int(data.get("aid", 0))
            }
            if data.get("net") in ["ws", "grpc"]:
                outbound["transport"] = {
                    "type": data.get("net"),
                    "path": data.get("path", "")
                }
            return outbound

        parsed = urllib.parse.urlparse(uri)
        if not parsed.hostname or not parsed.port:
            return None

        params = urllib.parse.parse_qs(parsed.query)

        if scheme in ["vless", "trojan"]:
            outbound = {
                "type": scheme,
                "tag": "proxy",
                "server": parsed.hostname,
                "server_port": parsed.port,
                "uuid" if scheme == "vless" else "password": parsed.username or "",
            }
            if params.get("security", [""])[0] in ["tls", "reality"]:
                outbound["tls"] = {
                    "enabled": True,
                    "server_name": params.get("sni", [parsed.hostname])[0],
                    "insecure": True
                }
            return outbound

        elif scheme == "ss":
            user_info = parsed.username or ""
            if ":" in user_info:
                method, password = user_info.split(":", 1)
            else:
                decoded_user = safe_b64decode_str(user_info)
                if ":" in decoded_user:
                    method, password = decoded_user.split(":", 1)
                else:
                    return None
            return {
                "type": "shadowsocks",
                "tag": "proxy",
                "server": parsed.hostname,
                "server_port": parsed.port,
                "method": method,
                "password": password
            }

        elif scheme in ["hy2", "hysteria2"]:
            return {
                "type": "hysteria2",
                "tag": "proxy",
                "server": parsed.hostname,
                "server_port": parsed.port,
                "password": parsed.username or "",
                "tls": {
                    "enabled": True,
                    "server_name": params.get("sni", [parsed.hostname])[0],
                    "insecure": True
                }
            }
    except Exception:
        return None
    return None

def safe_b64decode_str(s: str) -> str:
    s = s.strip().replace("\r", "").replace("\n", "")
    missing = len(s) % 4
    if missing:
        s += "=" * (4 - missing)
    try:
        return base64.b64decode(s, validate=False).decode("utf-8", errors="ignore")
    except Exception:
        return ""
