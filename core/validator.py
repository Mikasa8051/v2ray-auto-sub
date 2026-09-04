import asyncio
import logging
from urllib.parse import urlparse

async def check_node_tcp(node_url: str, timeout: float = 3.0) -> bool:
    """基础 TCP 端口可达性快速探测"""
    try:
        if node_url.startswith("vmess://"):
            return True # VMess 简单放行交由后续过滤器，或自行解析 Host 验证
            
        parsed = urlparse(node_url)
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            return True
            
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False

async def batch_validate(nodes: list[str], config: dict) -> list[str]:
    """并发握手验证存活"""
    timeout = config["settings"].get("connect_timeout", 3.0)
    concurrency = config["settings"].get("max_concurrency", 20)
    
    semaphore = asyncio.Semaphore(concurrency)
    valid_nodes = []

    async def worker(node):
        async with semaphore:
            if await check_node_tcp(node, timeout):
                valid_nodes.append(node)

    tasks = [worker(node) for node in nodes]
    await asyncio.gather(*tasks)
    logging.info(f"TCP 连通性测试通过: {len(valid_nodes)} / {len(nodes)}")
    return valid_nodes
