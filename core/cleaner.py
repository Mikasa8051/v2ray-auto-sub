import base64
import json
from urllib.parse import unquote
from core.parser import PROTOCOL_MAP

def validate_and_extract_key(node_url: str) -> tuple[str, str] | None:
    node_url = node_url.strip().rstrip('.,;)]}')
    if "://" not in node_url:
        return None

    scheme, _, rest = node_url.partition("://")
    scheme = scheme.lower()
    if scheme not in PROTOCOL_MAP:
        return None

    protocol_name = PROTOCOL_MAP[scheme]

    # VMess 解包 JSON 比对 server:port/id
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
            return dedup_key, node_url
        except Exception:
            return None

    # 其余协议去除 # 后的节点名称后比对
    try:
        main_part = rest.split("#")[0]
        if not main_part or len(main_part) < 6:
            return None
            
        dedup_key = f"{protocol_name}://{unquote(main_part).lower()}"
        return dedup_key, node_url
    except Exception:
        return None

def deduplicate_and_clean(raw_nodes: list[str]) -> list[str]:
    seen_keys = set()
    unique_nodes = []
    invalid_keywords = ["127.0.0.1", "localhost", "0.0.0.0"]

    for raw in raw_nodes:
        if any(kw in raw for kw in invalid_keywords):
            continue
            
        res = validate_and_extract_key(raw)
        if not res:
            continue

        dedup_key, clean_url = res
        if dedup_key in seen_keys:
            continue

        seen_keys.add(dedup_key)
        unique_nodes.append(clean_url)

    return unique_nodes
