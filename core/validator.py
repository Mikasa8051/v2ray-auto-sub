import asyncio
import json
import logging
import os
import subprocess
import time
import base64
from urllib.parse import urlparse, parse_qs, unquote
import aiohttp
from aiohttp_socks import ProxyConnector

SPEED_TEST_URL = "https://speed.cloudflare.com/__down?bytes=1000000"
LATENCY_TEST_URL = "http://cp.cloudflare.com/generate_204"
START_PORT = 20000
BATCH_SIZE = 15

def convert_node_to_singbox_outbound(node_url: str, tag: str) -> dict | None:
    """全面解析 15 种协议 URI 并转为 sing-box outbound 格式"""
    try:
        scheme, _, rest = node_url.partition("://")
        scheme = scheme.lower()

        # 1. VMess
        if scheme == "vmess":
            b64_str = rest.split("#")[0]
            b64_str += "=" * (-len(b64_str) % 4)
            cfg = json.loads(base64.b64decode(b64_str).decode('utf-8', errors='ignore'))
            return {
                "type": "vmess",
                "tag": tag,
                "server": cfg.get("add"),
                "server_port": int(cfg.get("port", 443)),
                "uuid": cfg.get("id"),
                "security": cfg.get("scy", "auto"),
                "alter_id": int(cfg.get("aid", 0)),
                "transport": {"type": cfg.get("net")} if cfg.get("net") and cfg.get("net") != "tcp" else None
            }

        # 2. VLESS
        elif scheme == "vless":
            u = urlparse(node_url)
            q = parse_qs(u.query)
            return {
                "type": "vless",
                "tag": tag,
                "server": u.hostname,
                "server_port": u.port or 443,
                "uuid": u.username,
                "flow": q.get("flow", [""])[0] or None,
                "tls": {"enabled": True, "insecure": True} if q.get("security", [""])[0] in ["tls", "reality"] else None
            }

        # 3. Trojan
        elif scheme == "trojan":
            u = urlparse(node_url)
            return {
                "type": "trojan",
                "tag": tag,
                "server": u.hostname,
                "server_port": u.port or 443,
                "password": u.username,
                "tls": {"enabled": True, "insecure": True}
            }

        # 4. Shadowsocks (SS)
        elif scheme == "ss":
            u = urlparse(node_url)
            if u.username and u.password:
                method, password = u.username, u.password
            else:
                raw_user = rest.split("@")[0]
                raw_user += "=" * (-len(raw_user) % 4)
                decoded = base64.b64decode(raw_user).decode('utf-8', errors='ignore')
                method, password = decoded.split(":", 1)
            return {
                "type": "shadowsocks",
                "tag": tag,
                "server": u.hostname,
                "server_port": u.port,
                "method": method,
                "password": password
            }

        # 5. Hysteria2 / Hy2
        elif scheme in ["hysteria2", "hy2"]:
            u = urlparse(node_url)
            q = parse_qs(u.query)
            return {
                "type": "hysteria2",
                "tag": tag,
                "server": u.hostname,
                "server_port": u.port or 443,
                "password": u.username or "",
                "tls": {
                    "enabled": True,
                    "server_name": q.get("sni", [""])[0] or u.hostname,
                    "insecure": q.get("insecure", ["0"])[0] == "1"
                }
            }

        # 6. Hysteria / Hy
        elif scheme in ["hysteria", "hy"]:
            u = urlparse(node_url)
            q = parse_qs(u.query)
            return {
                "type": "hysteria",
                "tag": tag,
                "server": u.hostname,
                "server_port": u.port or 443,
                "auth_str": q.get("auth", [""])[0] or u.username,
                "tls": {
                    "enabled": True,
                    "server_name": q.get("peer", [""])[0] or u.hostname,
                    "insecure": q.get("insecure", ["0"])[0] == "1"
                }
            }

        # 7. TUIC
        elif scheme == "tuic":
            u = urlparse(node_url)
            q = parse_qs(u.query)
            return {
                "type": "tuic",
                "tag": tag,
                "server": u.hostname,
                "server_port": u.port or 8443,
                "uuid": u.username,
                "password": u.password or "",
                "congestion_control": q.get("congestion_control", ["bbr"])[0],
                "tls": {
                    "enabled": True,
                    "server_name": q.get("sni", [""])[0] or u.hostname,
                    "insecure": q.get("insecure", ["0"])[0] == "1"
                }
            }

        # 8. Socks5 / Socks
        elif scheme in ["socks5", "socks"]:
            u = urlparse(node_url)
            return {
                "type": "socks",
                "tag": tag,
                "server": u.hostname,
                "server_port": u.port or 1080,
                "username": u.username or None,
                "password": u.password or None
            }

        # 9. Juicity
        elif scheme == "juicity":
            u = urlparse(node_url)
            q = parse_qs(u.query)
            return {
                "type": "juicity",
                "tag": tag,
                "server": u.hostname,
                "server_port": u.port or 443,
                "uuid": u.username,
                "password": u.password or "",
                "pinned_certchain_sha256": q.get("pinned_certchain_sha256", [""])[0] or None
            }

        # 10. WireGuard / WG
        elif scheme in ["wireguard", "wg"]:
            u = urlparse(node_url)
            q = parse_qs(u.query)
            return {
                "type": "wireguard",
                "tag": tag,
                "server": u.hostname,
                "server_port": u.port or 51820,
                "secret_key": u.username,
                "public_key": q.get("public_key", [""])[0],
                "local_address": q.get("ip", ["10.0.0.2/32"])
            }

    except Exception:
        pass
    return None

async def test_single_node_speed(port: int, node_url: str) -> dict:
    result = {"node": node_url, "latency": 9999, "speed": 0.0, "valid": False}
    proxy_uri = f"socks5://127.0.0.1:{port}"
    connector = ProxyConnector.from_url(proxy_uri)
    
    timeout = aiohttp.ClientTimeout(total=8, connect=3)
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            t0 = time.time()
            async with session.get(LATENCY_TEST_URL) as resp:
                if resp.status in [200, 204]:
                    result["latency"] = int((time.time() - t0) * 1000)
                else:
                    return result
            
            t_start = time.time()
            downloaded = 0
            async with session.get(SPEED_TEST_URL) as resp:
                if resp.status == 200:
                    async for chunk in resp.content.iter_chunked(1024 * 16):
                        downloaded += len(chunk)
                    duration = time.time() - t_start
                    if duration > 0:
                        result["speed"] = round((downloaded / 1024) / duration, 2)
                        result["valid"] = True
    except Exception:
        pass
    return result

async def test_batch_nodes(nodes_batch: list[tuple[int, str, dict, str]]) -> list[dict]:
    inbounds = []
    outbounds = []
    route_rules = []
    
    for port, tag, outbound, _ in nodes_batch:
        inbounds.append({"type": "socks", "tag": f"in-{tag}", "listen": "127.0.0.1", "listen_port": port})
        outbounds.append(outbound)
        route_rules.append({"inbound": [f"in-{tag}"], "outbound": tag})

    config_data = {
        "log": {"level": "warn"},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "route": {"rules": route_rules}
    }

    config_file = f"temp_singbox_{nodes_batch[0][0]}.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f)

    proc = subprocess.Popen(["sing-box", "run", "-c", config_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(1.5)

    tasks = [test_single_node_speed(port, node_url) for port, _, _, node_url in nodes_batch]
    results = await asyncio.gather(*tasks)

    proc.terminate()
    proc.wait()
    if os.path.exists(config_file):
        os.remove(config_file)

    return results

async def batch_validate(nodes: list[str], config: dict) -> list[str]:
    logging.info("开始多协议 sing-box 真实下载测速...")
    valid_items = []
    current_port = START_PORT
    batch_buffer = []

    for idx, node in enumerate(nodes):
        outbound = convert_node_to_singbox_outbound(node, f"node_{idx}")
        if not outbound:
            continue
            
        batch_buffer.append((current_port, f"node_{idx}", outbound, node))
        current_port += 1

        if len(batch_buffer) >= BATCH_SIZE:
            logging.info(f"正在测速批次: {len(batch_buffer)} 个节点...")
            batch_results = await test_batch_nodes(batch_buffer)
            for res in batch_results:
                if res["valid"] and res["speed"] > 50:
                    valid_items.append(res)
            batch_buffer.clear()

    if batch_buffer:
        batch_results = await test_batch_nodes(batch_buffer)
        for res in batch_results:
            if res["valid"] and res["speed"] > 50:
                valid_items.append(res)

    valid_items.sort(key=lambda x: (-x["speed"], x["latency"]))

    logging.info(f"测速完成，共筛选出 {len(valid_items)} 个可用高速节点")
    return [item["node"] for item in valid_items]
