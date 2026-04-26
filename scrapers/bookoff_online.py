import asyncio
import re
from typing import List
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup

from core.http import make_client
from core.models import Item

SITE = "ブックオフ"
BASE = "https://shopping.bookoff.co.jp"


async def search(keyword: str) -> List[Item]:
    url = f"{BASE}/search/keyword/{quote(keyword)}"
    items: List[Item] = []
    try:
        async with make_client() as client:
            r = await client.get(url)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")

            for card in soup.select(".productItem, li.item, .product, article, [class*='ProductCard']"):
                title_el = card.select_one("a[href*='/product/'], .productTitle a, h3 a, .title a")
                price_el = card.select_one(".productPrice, .price, [class*='price']")
                img_el = card.select_one("img")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                item_url = urljoin(BASE, href)
                price = _extract_price(price_el.get_text() if price_el else "")
                image_url = (img_el.get("data-src") or img_el.get("src")) if img_el else None
                if image_url:
                    image_url = urljoin(BASE, image_url)
                items.append(Item(
                    site=SITE, title=title, price=price,
                    condition="中古", image_url=image_url,
                    item_url=item_url, in_stock=price is not None,
                ))
    except Exception as e:
        print(f"[{SITE}] error: {e}")
    return items


def _extract_price(text: str):
    if not text:
        return None
    m = re.search(r"([\d,]+)\s*円", text) or re.search(r"¥\s*([\d,]+)", text)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


if __name__ == "__main__":
    import sys
    items = asyncio.run(search(sys.argv[1] if len(sys.argv) > 1 else "PSP-3000"))
    print(f"取得件数: {len(items)}")
    for it in items[:5]:
        print(it)
