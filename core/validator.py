import asyncio
import json
import logging
import os
import subprocess
import time
import aiohttp
from aiohttp_socks import ProxyConnector

SPEED_TEST_URL = "https://speed.cloudflare.com/__down?bytes=1000000"  # 1MB 下载测试
LATENCY_TEST_URL = "http://cp.cloudflare.com/generate_204"             # HTTP 204 延迟测试
START_PORT = 20000
BATCH_SIZE = 15  # 每批并发测速节点数

def convert_node_to_singbox_outbound(node_url: str, tag: str) -> dict | None:
    """将常见的节点 URI 转为 sing-box outbound 格式"""
    try:
        if node_url.startswith("vmess://"):
            import base64
            b64_str = node_url.replace("vmess://", "").split("#")[0]
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
        elif node_url.startswith("vless://"):
            from urllib.parse import urlparse, parse_qs
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
        elif node_url.startswith("trojan://"):
            from urllib.parse import urlparse
            u = urlparse(node_url)
            return {
                "type": "trojan",
                "tag": tag,
                "server": u.hostname,
                "server_port": u.port or 443,
                "password": u.username,
                "tls": {"enabled": True, "insecure": True}
            }
        elif node_url.startswith("ss://"):
            from urllib.parse import urlparse
            u = urlparse(node_url)
            return {
                "type": "shadowsocks",
                "tag": tag,
                "server": u.hostname,
                "server_port": u.port,
                "method": u.username,
                "password": u.password
            }
    except Exception:
        pass
    return None

async def test_single_node_speed(port: int, node_url: str) -> dict:
    """通过本地 SOCKS5 代理测算 RTT 延迟与 1MB 下载速度 (KB/s)"""
    result = {"node": node_url, "latency": 9999, "speed": 0.0, "valid": False}
    proxy_uri = f"socks5://127.0.0.1:{port}"
    connector = ProxyConnector.from_url(proxy_uri)
    
    timeout = aiohttp.ClientTimeout(total=8, connect=3)
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # 1. 测试 HTTP 204 延迟
            t0 = time.time()
            async with session.get(LATENCY_TEST_URL) as resp:
                if resp.status == 204 or resp.status == 200:
                    result["latency"] = int((time.time() - t0) * 1000)
                else:
                    return result
            
            # 2. 测量 1MB 文件真实下载速率
            t_start = time.time()
            downloaded = 0
            async with session.get(SPEED_TEST_URL) as resp:
                if resp.status == 200:
                    async for chunk in resp.content.iter_chunked(1024 * 16):
                        downloaded += len(chunk)
                    duration = time.time() - t_start
                    if duration > 0:
                        speed_kb = (downloaded / 1024) / duration
                        result["speed"] = round(speed_kb, 2)
                        result["valid"] = True
    except Exception:
        pass
    return result

async def test_batch_nodes(nodes_batch: list[tuple[int, str, dict]]) -> list[dict]:
    """写出临时 sing-box 配置文件并进行批量并行测试"""
    inbounds = []
    outbounds = []
    
    for port, tag, outbound in nodes_batch:
        inbounds.append({
            "type": "socks",
            "tag": f"in-{tag}",
            "listen": "127.0.0.1",
            "listen_port": port
        })
        outbounds.append(outbound)
        
    # 构建简单的路由映射规则
    route_rules = []
    for port, tag, _ in nodes_batch:
        route_rules.append({
            "inbound": [f"in-{tag}"],
            "outbound": tag
        })

    config_data = {
        "log": {"level": "warn"},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "route": {"rules": route_rules}
    }

    config_file = f"temp_singbox_{nodes_batch[0][0]}.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f)

    # 启动 sing-box 后台进程
    proc = subprocess.Popen(["sing-box", "run", "-c", config_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(1.5) # 等待 sing-box 端口初始化

    tasks = []
    for port, _, node_url in nodes_batch:
        tasks.append(test_single_node_speed(port, node_url))

    results = await asyncio.gather(*tasks)

    # 清理后台进程与文件
    proc.terminate()
    proc.wait()
    if os.path.exists(config_file):
        os.remove(config_file)

    return results

async def batch_validate(nodes: list[str], config: dict) -> list[str]:
    """主逻辑：批量测速并按 (下载速度降序, 延迟升序) 排序导出"""
    logging.info("开始提取节点并准备 sing-box 真实下载测速...")
    
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
            batch_to_run = [(p, t, o) for p, t, o, n in batch_buffer]
            urls = [n for p, t, o, n in batch_buffer]
            
            logging.info(f"正在测速批次: {len(batch_to_run)} 个节点...")
            batch_results = await test_batch_nodes(batch_to_run)
            
            for res in batch_results:
                if res["valid"] and res["speed"] > 50: # 过滤下载速度低于 50 KB/s 的劣质节点
                    valid_items.append(res)
                    
            batch_buffer.clear()

    # 处理剩余不足批次的节点
    if batch_buffer:
        batch_to_run = [(p, t, o) for p, t, o, n in batch_buffer]
        batch_results = await test_batch_nodes(batch_to_run)
        for res in batch_results:
            if res["valid"] and res["speed"] > 50:
                valid_items.append(res)

    # 排序：下载速度优先（降序），延迟其次（升序）
    valid_items.sort(key=lambda x: (-x["speed"], x["latency"]))

    logging.info(f"测速完成！共淘汰劣质/无效节点，剩余优质节点 {len(valid_items)} 个")
    if valid_items:
        logging.info(f"最快节点速率: {valid_items[0]['speed']} KB/s, 延迟: {valid_items[0]['latency']} ms")

    return [item["node"] for item in valid_items]
