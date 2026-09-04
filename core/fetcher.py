import asyncio
import base64
import logging
import re
import aiohttp

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def safe_b64decode(text: str) -> str:
    """安全 Base64 解码，保留原始换行符结构"""
    text = text.strip()
    if re.search(r"(vmess|vless|ss|trojan|hy2|hysteria2|tuic)://", text, re.IGNORECASE):
        return text

    clean_text = text.replace("\r", "").replace("\n", "")
    missing_padding = len(clean_text) % 4
    if missing_padding:
        clean_text += "=" * (4 - missing_padding)
    try:
        decoded = base64.b64decode(clean_text, validate=False).decode("utf-8", errors="ignore")
        return decoded if decoded.strip() else text
    except Exception:
        return text

async def fetch_single_sub(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                content = await resp.text()
                return safe_b64decode(content)
    except Exception as e:
        logging.warning(f"订阅抓取失败 [{url}]: {e}")
    return ""

async def fetch_single_tg(session: aiohttp.ClientSession, channel: str) -> str:
    url = f"https://t.me/s/{channel}"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception as e:
        logging.warning(f"TG 频道抓取失败 [{channel}]: {e}")
    return ""

async def fetch_all_sources(sub_urls: list[str], tg_channels: list[str]) -> str:
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        sub_tasks = [fetch_single_sub(session, u) for u in sub_urls]
        tg_tasks = [fetch_single_tg(session, c) for c in tg_channels]
        results = await asyncio.gather(*sub_tasks, *tg_tasks, return_exceptions=True)

    combined_raw = []
    for res in results:
        if isinstance(res, str) and res:
            combined_raw.append(res)
    return "\n".join(combined_raw)
