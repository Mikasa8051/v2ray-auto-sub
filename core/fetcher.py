import asyncio
import logging
import socket
import aiohttp

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

def find_working_local_proxy(ports: list[int]) -> str | None:
    """自动检测本地可用代理端口，本地运行能抓 TG，GitHub Actions 自动降级直连"""
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                logging.info(f"检测到本地代理环境: http://127.0.0.1:{port}")
                return f"http://127.0.0.1:{port}"
    return None

async def fetch_url(session: aiohttp.ClientSession, url: str, proxy_url: str | None = None) -> str:
    """通用抓取函数"""
    try:
        async with session.get(url, headers=HEADERS, proxy=proxy_url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception as e:
        logging.warning(f"页面/订阅抓取失败 [{url}]: {e}")
    return ""

async def fetch_tg_channel(session: aiohttp.ClientSession, channel: str, proxy_url: str | None = None) -> str:
    """Telegram 频道 Web 页面抓取"""
    clean_channel = channel.strip().lstrip("@").replace("https://t.me/s/", "").replace("https://t.me/", "")
    url = f"https://t.me/s/{clean_channel}"
    return await fetch_url(session, url, proxy_url)

async def fetch_all_sources(sub_urls: list[str], tg_channels: list[str], proxy_ports: list[int]) -> list[str]:
    """并发拉取所有数据源"""
    proxy_url = find_working_local_proxy(proxy_ports)
    connector = aiohttp.TCPConnector(ssl=False)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        # TG 频道抓取带代理，普通订阅链接尽量直连
        tg_tasks = [fetch_tg_channel(session, ch, proxy_url) for ch in tg_channels]
        sub_tasks = [fetch_url(session, url, None) for url in sub_urls]
        
        results = await asyncio.gather(*sub_tasks, *tg_tasks, return_exceptions=True)

    raw_contents = []
    for res in results:
        if isinstance(res, str) and res.strip():
            raw_contents.append(res)
    return raw_contents
