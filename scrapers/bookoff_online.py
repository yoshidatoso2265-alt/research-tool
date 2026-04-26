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
    items: List[Item] = []
    seen = set()
    HARD_PAGE_LIMIT = 50
    try:
        async with make_client() as client:
            for page_num in range(1, HARD_PAGE_LIMIT + 1):
                url = f"{BASE}/search/keyword/{quote(keyword)}"
                if page_num > 1:
                    url += f"?page={page_num}"
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                except Exception:
                    break
                soup = BeautifulSoup(r.text, "lxml")

                page_added = 0
                for card in soup.select(".productItem, li.item, .product, article, [class*='ProductCard']"):
                    title_el = card.select_one("a[href*='/product/'], .productTitle a, h3 a, .title a")
                    price_el = card.select_one(".productPrice, .price, [class*='price']")
                    img_el = card.select_one("img")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    href = title_el.get("href", "")
                    item_url = urljoin(BASE, href)
                    if item_url in seen:
                        continue
                    seen.add(item_url)
                    price = _extract_price(price_el.get_text() if price_el else "")
                    image_url = (img_el.get("data-src") or img_el.get("src")) if img_el else None
                    if image_url:
                        image_url = urljoin(BASE, image_url)
                    items.append(Item(
                        site=SITE, title=title, price=price,
                        condition="中古", image_url=image_url,
                        item_url=item_url, in_stock=price is not None,
                    ))
                    page_added += 1
                if page_added == 0:
                    break
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
