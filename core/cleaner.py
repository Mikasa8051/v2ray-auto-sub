import asyncio
import hashlib
import ipaddress
from core.parser import parse_node_to_singbox_outbound

BOGON_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("0.0.0.0/32"),
    ipaddress.ip_network("100.64.0.0/10"),
]

async def async_is_public_ip(server: str) -> bool:
    """非阻塞异步 DNS 解析与内网黑名单校验"""
    try:
        ip_obj = ipaddress.ip_address(server)
        return not any(ip_obj in bogon for bogon in BOGON_NETS)
    except ValueError:
        pass

    try:
        loop = asyncio.get_event_loop()
        info = await loop.getaddrinfo(server, None)
        if not info:
            return False
        ip_str = info[0][4][0]
        ip_obj = ipaddress.ip_address(ip_str)
        return not any(ip_obj in bogon for bogon in BOGON_NETS)
    except Exception:
        return False

async def deduplicate_and_clean(raw_nodes: list[str]) -> list[dict]:
    seen_hashes = set()
    clean_nodes = []

    for raw in raw_nodes:
        outbound = parse_node_to_singbox_outbound(raw)
        if not outbound or not outbound.get("server") or outbound.get("server_port") == 0:
            continue

        server = outbound["server"]
        port = outbound["server_port"]
        node_type = outbound["type"]

        fingerprint = f"{node_type}://{server}:{port}"
        node_hash = hashlib.md5(fingerprint.encode()).hexdigest()

        if node_hash in seen_hashes:
            continue

        if not await async_is_public_ip(server):
            continue

        seen_hashes.add(node_hash)
        clean_nodes.append({
            "raw": raw,
            "outbound": outbound
        })

    return clean_nodes
