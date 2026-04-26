import asyncio
import re
from typing import List
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup

from core.http import make_client
from core.models import Item

SITE = "駿河屋"
BASE = "https://www.suruga-ya.jp"


async def search(keyword: str) -> List[Item]:
    url = f"{BASE}/search?category=&search_word={quote(keyword)}"
    items: List[Item] = []
    try:
        async with make_client() as client:
            r = await client.get(url)
            if r.status_code == 404:
                return []
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")

            for box in soup.select("div.item, div.item_box, div.search_result_box"):
                title_el = box.select_one("p.title a, .item_name a, h3 a")
                price_el = box.select_one(".price, .item_price, p.price")
                img_el = box.select_one("img")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                item_url = urljoin(BASE, href)
                price = _extract_price(price_el.get_text() if price_el else "")
                image_url = (img_el.get("data-src") or img_el.get("src")) if img_el else None
                if image_url:
                    image_url = urljoin(BASE, image_url)
                in_stock = price is not None and "品切" not in (price_el.get_text() if price_el else "")
                items.append(Item(
                    site=SITE, title=title, price=price,
                    condition="中古", image_url=image_url,
                    item_url=item_url, in_stock=in_stock,
                ))
    except Exception as e:
        print(f"[{SITE}] error: {e}")
    return items


def _extract_price(text: str):
    if not text:
        return None
    m = re.search(r"([\d,]+)\s*円", text)
    if not m:
        m = re.search(r"¥\s*([\d,]+)", text)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


if __name__ == "__main__":
    import sys
    items = asyncio.run(search(sys.argv[1] if len(sys.argv) > 1 else "PSP-3000"))
    print(f"取得件数: {len(items)}")
    for it in items[:5]:
        print(it)
