import asyncio
import re
from typing import List
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup

from core.http import make_client
from core.models import Item

SITE = "ヤフオク"
BASE = "https://auctions.yahoo.co.jp"
PAGE_SIZE = 50
HARD_PAGE_LIMIT = 50  # 安全装置


async def search(keyword: str) -> List[Item]:
    items: List[Item] = []
    seen = set()
    try:
        async with make_client() as client:
            for page_num in range(HARD_PAGE_LIMIT):
                offset = page_num * PAGE_SIZE + 1  # b パラメータは 1, 51, 101, ...
                url = f"{BASE}/search/search?p={quote(keyword)}&exflg=1&n={PAGE_SIZE}"
                if page_num > 0:
                    url += f"&b={offset}"
                r = await client.get(url)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "lxml")

                page_added = 0
                for li in soup.select("li.Product, .Products li, [class*='Product__inner']"):
                    title_el = li.select_one("a.Product__titleLink, h3 a, [class*='Product__title'] a")
                    price_el = li.select_one(".Product__priceValue, [class*='Product__price']")
                    img_el = li.select_one("img")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    href = title_el.get("href", "")
                    item_url = urljoin(BASE, href)
                    if item_url in seen:
                        continue
                    seen.add(item_url)
                    price = _extract_price(price_el.get_text() if price_el else "")
                    image_url = img_el.get("src") if img_el else None
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
    m = re.search(r"([\d,]+)", text)
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
