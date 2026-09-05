import base64
import html
import json
import re
from bs4 import BeautifulSoup

# 匹配所有 15 种协议 Scheme
NODE_REGEX = re.compile(
    r'(?:vmess|vless|ssr|ss|trojan|hysteria2|hy2|hysteria|hy|tuic|socks5|socks|wireguard|wg|juicity)://[^\s<>"\']+',
    re.IGNORECASE
)

PROTOCOL_MAP = {
    "vless": "VLESS", "vmess": "VMess", "hysteria2": "Hysteria2", "hy2": "Hysteria2",
    "hysteria": "Hysteria", "hy": "Hysteria", "trojan": "Trojan", "ss": "Shadowsocks",
    "ssr": "ShadowsocksR", "tuic": "TUIC", "socks5": "Socks5", "socks": "Socks5",
    "wireguard": "WireGuard", "wg": "WireGuard", "juicity": "Juicity"
}

def parse_html_page(raw_html: str) -> list[str]:
    text_blocks = []
    decoded_html = html.unescape(raw_html)
    
    try:
        soup = BeautifulSoup(decoded_html, 'html.parser')
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].strip()
            if NODE_REGEX.search(href):
                text_blocks.append(href)
                
        for elem in soup.find_all(['code', 'pre', 'div', 'span']):
            text_blocks.append(elem.get_text(strip=True))
            
        text_blocks.append(soup.get_text(separator='\n'))
    except Exception:
        text_blocks.append(decoded_html)
        
    return text_blocks

def extract_nodes_from_text(text: str) -> list[str]:
    nodes = []
    text = text.strip()
    
    matches = NODE_REGEX.findall(text)
    for m in matches:
        clean = m.strip().rstrip('.,;)]}')
        if len(clean) > 10:
            nodes.append(clean)
            
    try:
        clean_text = re.sub(r'\s+', '', text)
        missing_padding = len(clean_text) % 4
        if missing_padding:
            clean_text += "=" * (4 - missing_padding)
        decoded = base64.b64decode(clean_text, validate=False).decode('utf-8', errors='ignore')
        if NODE_REGEX.search(decoded):
            for m in NODE_REGEX.findall(decoded):
                clean = m.strip().rstrip('.,;)]}')
                if len(clean) > 10:
                    nodes.append(clean)
    except Exception:
        pass

    return nodes

def extract_all_nodes(raw_sources: list[str]) -> list[str]:
    extracted = []
    for content in raw_sources:
        if any(tag in content.lower() for tag in ["<html", "<div", "<a ", "<span", "<body"]):
            blocks = parse_html_page(content)
            for b in blocks:
                extracted.extend(extract_nodes_from_text(b))
        else:
            extracted.extend(extract_nodes_from_text(content))
    return extracted
