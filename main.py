import asyncio
import logging
import yaml
from core.fetcher import fetch_all_sources
from core.parser import extract_all_nodes
from core.cleaner import deduplicate_and_clean
from core.validator import batch_validate
from core.exporter import export_subscriptions

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

async def main():
    # 1. 加载配置
    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 2. 抓取网页源与 TG 频道
    logging.info("1. 开始高并发拉取订阅源与 Telegram 频道页面...")
    raw_sources = await fetch_all_sources(
        cfg.get("subscription_urls", []),
        cfg.get("telegram_channels", []),
        cfg["settings"].get("local_proxy_ports", [7890, 10809])
    )

    # 3. DOM 树解析与节点提取
    logging.info("2. 深度解析 HTML 与 Base64 密文块...")
    raw_nodes = extract_all_nodes(raw_sources)
    logging.info(f"初步提取到节点链接: {len(raw_nodes)} 个")

    # 4. 协议去重与格式清洗
    logging.info("3. 提取协议关键 Key 进行高精度去重与格式清洗...")
    clean_nodes = deduplicate_and_clean(raw_nodes)
    logging.info(f"清洗去重后有效节点: {len(clean_nodes)} 个")

    # 5. 快速存活探测
    logging.info("4. 启动并发 TCP 端口握手检测...")
    valid_nodes = await batch_validate(clean_nodes, cfg)

    # 6. 导出最终文件
    logging.info("5. 导出 nodes.txt (明文) 与 sub.txt (Base64)...")
    export_subscriptions(valid_nodes, cfg["settings"]["max_nodes_export"])
    logging.info("🎉 全流程运行完毕！")

if __name__ == "__main__":
    asyncio.run(main())
