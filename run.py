import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.aggregator import aggregate
from core.history import save_history


def main():
    if len(sys.argv) < 2:
        print("使い方: python run.py \"型番\"")
        sys.exit(1)
    keyword = " ".join(sys.argv[1:])
    print(f"=== 検索開始: {keyword} ===\n")

    items = asyncio.run(aggregate(keyword))

    if not items:
        print("\n販売中の該当商品が見つかりませんでした。")
        return

    print(f"\n=== ランキング（安い順 上位10件） ===")
    for rank, it in enumerate(items[:10], start=1):
        title = (it.title or "")[:50]
        print(f"{rank:>2}. [{it.site}] ¥{it.price:,} | {title}")

    path = save_history(keyword, items)
    print(f"\n履歴JSON保存: {path}")
    print(f"総件数: {len(items)}件")


if __name__ == "__main__":
    main()
