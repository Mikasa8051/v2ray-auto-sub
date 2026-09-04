import asyncio
import json
import os
import subprocess
import time
import aiohttp

class PortManager:
    """动态安全端口池管理，防止高并发下端口冲突"""
    def __init__(self, start_port=20000, max_ports=100):
        self.queue = asyncio.Queue()
        for p in range(start_port, start_port + max_ports):
            self.queue.put_nowait(p)

    async def get_port(self):
        return await self.queue.get()

    def release_port(self, port):
        self.queue.put_nowait(port)

port_mgr = PortManager()

def build_singbox_config(outbound_config: dict, listen_port: int) -> dict:
    return {
        "log": {"level": "panic"},
        "inbounds": [{
            "type": "mixed",
            "tag": "mixed-in",
            "listen": "127.0.0.1",
            "listen_port": listen_port
        }],
        "outbounds": [outbound_config]
    }

async def test_node_performance(node_data: dict, cfg: dict) -> tuple[bool, float]:
    port = await port_mgr.get_port()
    config_path = f"/tmp/sb_{port}.json"
    singbox_cfg = build_singbox_config(node_data["outbound"], port)

    with open(config_path, "w") as f:
        json.dump(singbox_cfg, f)

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "sing-box", "run", "-c", config_path,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await asyncio.sleep(0.5)

        proxy_url = f"http://127.0.0.1:{port}"

        # 阶段 1：HTTP 204 连通性校验
        timeout_204 = aiohttp.ClientTimeout(total=cfg["settings"]["stage1_timeout"])
        async with aiohttp.ClientSession(timeout=timeout_204) as session:
            async with session.get(cfg["settings"]["test_204_url"], proxy=proxy_url) as resp:
                if resp.status != 204 or "Content-Length" in resp.headers:
                    return False, 0.0

        # 阶段 2：3 秒限时下载测速
        start = time.time()
        downloaded = 0
        timeout_dl = aiohttp.ClientTimeout(total=cfg["settings"]["stage2_duration"] + 1)

        async with aiohttp.ClientSession(timeout=timeout_dl) as session:
            async with session.get(cfg["settings"]["test_speed_url"], proxy=proxy_url) as resp:
                if resp.status == 200:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        downloaded += len(chunk)
                        if time.time() - start >= cfg["settings"]["stage2_duration"]:
                            break

        elapsed = time.time() - start
        speed_mbps = (downloaded / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0

        if speed_mbps >= cfg["settings"]["min_speed_mbps"]:
            return True, round(speed_mbps, 2)

    except Exception:
        pass
    finally:
        if proc:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
        if os.path.exists(config_path):
            os.remove(config_path)
        port_mgr.release_port(port)

    return False, 0.0

async def batch_validate(nodes: list[dict], cfg: dict) -> list[dict]:
    semaphore = asyncio.Semaphore(10)
    valid_results = []

    async def worker(node: dict):
        async with semaphore:
            ok, speed = await test_node_performance(node, cfg)
            if ok:
                node["speed"] = speed
                valid_results.append(node)

    tasks = [worker(n) for n in nodes]
    await asyncio.gather(*tasks, return_exceptions=True)
    return valid_results
