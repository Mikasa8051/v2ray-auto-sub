import asyncio
import logging
import yaml
from core.fetcher import fetch_all_sources
from core.parser import extract_nodes
from core.cleaner import deduplicate_and_clean
from core.validator import batch_validate
from core.exporter import export_subscription

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

async def main():
    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    logging.info("1. 高并发抓取订阅源与 Telegram 频道...")
    raw_data = await fetch_all_sources(cfg["subscription_urls"], cfg["telegram_channels"])

    logging.info("2. 正则提取节点 URI...")
    extracted_nodes = extract_nodes(raw_data)
    logging.info(f"提取到原始节点: {len(extracted_nodes)} 个")

    logging.info("3. 异步节点去重与内网 IP 拦截...")
    clean_nodes = await deduplicate_and_clean(extracted_nodes)
    logging.info(f"清洗后有效节点: {len(clean_nodes)} 个")

    logging.info("4. 启动 sing-box 进行 204 校验与 3 秒下载测速...")
    tested_nodes = await batch_validate(clean_nodes, cfg)
    logging.info(f"测速合格节点: {len(tested_nodes)} 个")

    logging.info("5. 降序排序并导出 Base64 订阅文本...")
    top_nodes = tested_nodes[:cfg["settings"]["max_nodes_export"]]
    out_path = export_subscription(top_nodes)
    logging.info(f"全流程顺利完成！输出订阅文件保存至: {out_path}")

if __name__ == "__main__":
    asyncio.run(main())
