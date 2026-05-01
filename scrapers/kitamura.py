"""カメラのキタムラ 中古品スクレイパー — 内部 JSON API 経由。

検索URL: https://shop.kitamura.jp/ec/list?keyword={keyword}&type=u
内部API: /ec/api/cache/vvc/u/v1/list?keyword={keyword}&limit=40&page={page}
"""
import asyncio
from typing import List
from urllib.parse import quote

from core.http import make_client
from core.models import Item

SITE = "キタムラ"
BASE = "https://shop.kitamura.jp"
API_PATH = "/ec/api/cache/vvc/u/v1/list"
PER_PAGE = 40
MAX_PAGES = 20

RANK_MAP = {
    "5": "AA (新品同様)",
    "4": "A (美品)",
    "3": "AB (良品)",
    "2": "B (並品)",
    "1": "C (やや難あり)",
}


async def search(keyword: str) -> List[Item]:
    items: List[Item] = []
    seen = set()
    try:
        async with make_client() as client:
            for page in range(1, MAX_PAGES + 1):
                try:
                    r = await client.get(
                        f"{BASE}{API_PATH}",
                        params={
                            "keyword": keyword,
                            "limit": str(PER_PAGE),
                            "page": str(page),
                        },
                        headers={"Accept": "application/json"},
                    )
                    r.raise_for_status()
                except Exception:
                    break

                try:
                    data = r.json()
                except Exception:
                    break

                page_items = data.get("items", [])
                if not page_items:
                    break

                for rec in page_items:
                    item_id = rec.get("itemid", "")
                    if not item_id or item_id in seen:
                        continue
                    seen.add(item_id)

                    title = rec.get("title") or rec.get("netshop_title") or ""
                    if not title:
                        continue

                    price_raw = rec.get("price")
                    try:
                        price = int(price_raw) if price_raw else None
                    except (ValueError, TypeError):
                        price = None

                    rank = str(rec.get("number1", ""))
                    if rank == "1":  # C (やや難あり) は除外
                        continue
                    condition = RANK_MAP.get(rank, "中古")

                    image_url = rec.get("image")
                    item_url = f"{BASE}/ec/used/{item_id}"

                    description = rec.get("description") or rec.get("keyword1") or ""
                    location = rec.get("narrow3") or None  # 店舗名

                    items.append(Item(
                        site=SITE,
                        title=title,
                        price=price,
                        condition=condition,
                        image_url=image_url,
                        item_url=item_url,
                        in_stock=True,
                        location=location,
                        description=description,
                    ))

                if len(page_items) < PER_PAGE:
                    break
    except Exception as e:
        print(f"[{SITE}] error: {e}")
    return items


if __name__ == "__main__":
    import sys
    kw = sys.argv[1] if len(sys.argv) > 1 else "EOS R6"
    results = asyncio.run(search(kw))
    print(f"取得件数: {len(results)}")
    for it in results[:5]:
        print(f"{it.price} | {it.title[:60]} | {it.condition} | {it.location}")
