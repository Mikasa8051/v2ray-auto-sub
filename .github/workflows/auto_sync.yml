import asyncio
import base64
import html
import json
import re
import socket
from urllib.parse import unquote
import aiohttp
from bs4 import BeautifulSoup

TARGET_CHANNELS = [
    "v2rayfree",
    "v2ray_free_conf",
    "SSRList",
    "NodeFree",
    "v2ray_vpn_sub"
]

COMMON_PROXY_PORTS = [7890, 10809, 20809, 2080, 10808, 1080]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

NODE_REGEX = re.compile(
    r'(?:vmess|vless|ssr|ss|trojan|hysteria2|hy2|hysteria|hy|tuic|socks5|socks|wireguard|wg|juicity)://[^\s<>"\']+',
    re.IGNORECASE
)

PROTOCOL_MAP = {
    "vless": "VLESS",
    "vmess": "VMess",
    "hysteria2": "Hysteria2",
    "hy2": "Hysteria2",
    "hysteria": "Hysteria",
    "hy": "Hysteria",
    "trojan": "Trojan",
    "ss": "Shadowsocks",
    "ssr": "ShadowsocksR",
    "tuic": "TUIC",
    "socks5": "Socks5",
    "socks": "Socks5",
    "wireguard": "WireGuard",
    "wg": "WireGuard",
    "juicity": "Juicity"
}

def find_working_local_proxy() -> str | None:
    for port in COMMON_PROXY_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.3)
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                return f"http://127.0.0.1:{port}"
    return None

async def fetch_channel_nodes(session: aiohttp.ClientSession, channel: str, proxy_url: str | None) -> list[str]:
    url = f"https://t.me/s/{channel}"
    try:
        async with session.get(url, headers=HEADERS, proxy=proxy_url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                return []

            raw_html = await resp.text()
            soup = BeautifulSoup(html.unescape(raw_html), 'html.parser')

            text_blocks = []
            for a_tag in soup.find_all('a', href=True):
                if NODE_REGEX.search(a_tag['href']):
                    text_blocks.append(a_tag['href'])

            for elem in soup.find_all(['code', 'pre', 'div', 'span']):
                text_blocks.append(elem.get_text(strip=True))

            text_blocks.append(soup.get_text(separator='\n'))

            found_nodes = []
            for block in text_blocks:
                matches = NODE_REGEX.findall(block)
                for node in matches:
                    clean_node = node.strip().rstrip('.,;)]}')
                    if len(clean_node) > 10:
                        found_nodes.append(clean_node)
            return found_nodes
    except Exception:
        return []

def validate_and_extract_key(node_url: str) -> tuple[str, str, str] | None:
    node_url = node_url.strip().rstrip('.,;)]}')
    if "://" not in node_url:
        return None

    scheme, _, rest = node_url.partition("://")
    scheme = scheme.lower()
    if scheme not in PROTOCOL_MAP:
        return None

    protocol_name = PROTOCOL_MAP[scheme]

    if scheme == "vmess":
        try:
            b64_str = rest.split("#")[0]
            b64_str += "=" * (-len(b64_str) % 4)
            decoded_bytes = base64.b64decode(b64_str)
            config = json.loads(decoded_bytes.decode('utf-8', errors='ignore'))
            
            server = config.get("add") or config.get("host")
            port = config.get("port")
            uuid = config.get("id")
            
            if not server or not port or not uuid:
                return None
            
            dedup_key = f"vmess://{server}:{port}/{uuid}"
            return protocol_name, dedup_key, node_url
        except Exception:
            return None

    try:
        main_part = rest.split("#")[0]
        if not main_part or len(main_part) < 6:
            return None
            
        dedup_key = f"{protocol_name}://{unquote(main_part).lower()}"
        return protocol_name, dedup_key, node_url
    except Exception:
        return None

def process_and_deduplicate(raw_nodes: list[str]) -> list[str]:
    seen_keys = set()
    unique_nodes = []

    for raw in raw_nodes:
        res = validate_and_extract_key(raw)
        if not res:
            continue

        _, dedup_key, clean_url = res
        if dedup_key in seen_keys:
            continue

        seen_keys.add(dedup_key)
        unique_nodes.append(clean_url)

    return unique_nodes

def export_subscriptions(nodes: list[str]):
    plain_content = "\n".join(nodes)
    
    with open("nodes.txt", "w", encoding="utf-8") as f:
        f.write(plain_content)

    b64_content = base64.b64encode(plain_content.encode("utf-8")).decode("utf-8")
    with open("sub.txt", "w", encoding="utf-8") as f:
        f.write(b64_content)

async def main():
    proxy_url = find_working_local_proxy()
    
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_channel_nodes(session, ch, proxy_url) for ch in TARGET_CHANNELS]
        results = await asyncio.gather(*tasks)

    all_raw_nodes = []
    for nodes in results:
        all_raw_nodes.extend(nodes)

    unique_nodes = process_and_deduplicate(all_raw_nodes)

    if unique_nodes:
        export_subscriptions(unique_nodes)
        print(f"🎉 成功抓取并清洗节点，共计 {len(unique_nodes)} 个，已写入 sub.txt 和 nodes.txt")

if __name__ == "__main__":
    asyncio.run(main())
