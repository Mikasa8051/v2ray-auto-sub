import base64
import os

def export_subscription(valid_nodes: list[dict], output_dir: str = "./dist") -> str:
    valid_nodes.sort(key=lambda x: x.get("speed", 0.0), reverse=True)

    final_uris = [node["raw"] for node in valid_nodes]
    subscription_text = "\n".join(final_uris)
    base64_payload = base64.b64encode(subscription_text.encode("utf-8")).decode("utf-8")

    os.makedirs(output_dir, exist_ok=True)
    out_file = os.path.join(output_dir, "sub.txt")

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(base64_payload)

    return out_file
