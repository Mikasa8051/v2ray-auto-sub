import base64
import html
import json
import re
import urllib.parse
from bs4 import BeautifulSoup

# 支持全套 12 种代理协议的正则表达式
NODE_REGEX = re.compile(
    r'(?:vmess|vless|ssr|ss|trojan|hysteria2|hy2|hysteria|hy|tuic|socks5|socks|wireguard|wg|juicity)://[^\s<>"\']+',
    re.IGNORECASE
)

def parse_html_page(raw_html: str) -> list[str]:
    """深度解析 HTML 页面，提取 href 属性、代码块、TG 消息体及解码文本"""
    extracted_blocks = []
    
    # 1. HTML 转义字符还原（如 &amp; -> &）
    decoded_html = html.unescape(raw_html)
    
    try:
        soup = BeautifulSoup(decoded_html, 'html.parser')
        
        # 2. 提取 <a> 标签超链接 (针对把 vless:// 嵌入 href 的网页)
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].strip()
            if NODE_REGEX.search(href):
                extracted_blocks.append(href)
                
        # 3. 针对 Telegram Web (tgme_widget_message_text) 与 <code>/<pre> 深度提取
        for elem in soup.find_all(['code', 'pre', 'div', 'span']):
            text = elem.get_text(strip=True)
            if text:
                extracted_blocks.append(text)
                
        # 4. 兜底整页纯文本提取
        extracted_blocks.append(soup.get_text(separator='\n'))
    except Exception:
        extracted_blocks.append(decoded_html)
        
    return extracted_blocks

def extract_nodes_from_block(text_block: str) -> list[str]:
    """从单段文本中提取节点，支持正则提取与 Base64 解码块二次提取"""
    nodes = []
    text_block = text_block.strip()
    
    # 直接正则提取
    nodes.extend(NODE_REGEX.findall(text_block))
    
    # 处理网页或 TG 消息中整段粘贴的 Base64 密文块
    try:
        clean_text = re.sub(r'\s+', '', text_block)
        missing_padding = len(clean_text) % 4
        if missing_padding:
            clean_text += "=" * (4 - missing_padding)
        decoded = base64.b64decode(clean_text, validate=False).decode('utf-8', errors='ignore')
        if NODE_REGEX.search(decoded):
            nodes.extend(NODE_REGEX.findall(decoded))
    except Exception:
        pass

    return nodes

def extract_nodes(raw_sources: list[str]) -> list[str]:
    """主提取入口：自动识别网页/TG 与普通订阅文本并完成解析"""
    all_nodes = []
    
    for content in raw_sources:
        # 判断是否为 HTML 网页/Telegram 预览页
        if any(tag in content.lower() for tag in ["<html", "<div", "<a ", "<span", "<body"]):
            blocks = parse_html_page(content)
            for block in blocks:
                all_nodes.extend(extract_nodes_from_block(block))
        else:
            all_nodes.extend(extract_nodes_from_block(content))
            
    # 去重与清洗末尾异常标点
    seen = set()
    unique_nodes = []
    for node in all_nodes:
        clean_node = node.strip().rstrip('.,;)]}')
        if clean_node and clean_node not in seen and len(clean_node) > 10:
            seen.add(clean_node)
            unique_nodes.append(clean_node)
            
    return unique_nodes

def safe_b64decode_str(s: str) -> str:
    s = s.strip().replace("\r", "").replace("\n", "")
    missing = len(s) % 4
    if missing:
        s += "=" * (4 - missing)
    try:
        return base64.b64decode(s, validate=False).decode("utf-8", errors="ignore")
    except Exception:
        return ""

def parse_node_to_singbox_outbound(uri: str) -> dict | None:
    """将 URI 解析为 sing-box 可识别的出站配置节点"""
    try:
        uri = uri.strip()
        scheme = uri.split("://")[0].lower()

        if scheme == "vmess":
            b64_part = uri[8:].split("#")[0]
            decoded = safe_b64decode_str(b64_part)
            if not decoded:
                return None
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

        elif scheme in ["socks", "socks5"]:
            return {
                "type": "socks",
                "tag": "proxy",
                "server": parsed.hostname,
                "server_port": parsed.port,
                "username": parsed.username or "",
                "password": parsed.password or ""
            }
            
        elif scheme == "tuic":
            return {
                "type": "tuic",
                "tag": "proxy",
                "server": parsed.hostname,
                "server_port": parsed.port,
                "uuid": parsed.username or "",
                "password": parsed.password or "",
                "congestion_control": "bbr",
                "tls": {
                    "enabled": True,
                    "server_name": params.get("sni", [parsed.hostname])[0],
                    "insecure": True
                }
            }
    except Exception:
        return None
    return None
