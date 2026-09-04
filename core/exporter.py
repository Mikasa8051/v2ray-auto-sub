import base64
import logging

def export_subscriptions(nodes: list[str], max_export: int) -> tuple[str, str]:
    """输出明文与 Base64 格式订阅文件"""
    export_nodes = nodes[:max_export]
    plain_content = "\n".join(export_nodes)
    
    with open("nodes.txt", "w", encoding="utf-8") as f:
        f.write(plain_content)

    b64_content = base64.b64encode(plain_content.encode("utf-8")).decode("utf-8")
    with open("sub.txt", "w", encoding="utf-8") as f:
        f.write(b64_content)

    logging.info(f"订阅导出成功，包含 {len(export_nodes)} 个可用节点。")
    return "nodes.txt", "sub.txt"
