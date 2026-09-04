import asyncio
import logging
import aiohttp

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

async def fetch_url(session: aiohttp.ClientSession, url: str) -> str:
    """通用网页及订阅链接抓取"""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception as e:
        logging.warning(f"网页/订阅抓取失败 [{url}]: {e}")
    return ""

async def fetch_tg_channel(session: aiohttp.ClientSession, channel: str) -> str:
    """Telegram 公开频道 WEB 预览页抓取"""
    clean_channel = channel.strip().lstrip("@").replace("https://t.me/s/", "").replace("https://t.me/", "")
    url = f"https://t.me/s/{clean_channel}"
    return await fetch_url(session, url)

async def fetch_all_sources(sub_urls: list[str], tg_channels: list[str]) -> list[str]:
    """并发拉取所有网页与 Telegram 频道源码"""
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        sub_tasks = [fetch_url(session, u) for u in sub_urls]
        tg_tasks = [fetch_tg_channel(session, c) for c in tg_channels]
        results = await asyncio.gather(*sub_tasks, *tg_tasks, return_exceptions=True)

    raw_contents = []
    for res in results:
        if isinstance(res, str) and res.strip():
            raw_contents.append(res)
    return raw_contents
