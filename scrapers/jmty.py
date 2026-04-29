import asyncio
import re
from typing import List
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup

from core.http import make_client
from core.models import Item

SITE = "ジモティー"
BASE = "https://jmty.jp"


async def search(keyword: str) -> List[Item]:
    items: List[Item] = []
    try:
        async with make_client() as client:
            # 全ページ走査（最終ページに到達するまで）
            all_lis = []
            HARD_PAGE_LIMIT = 50
            for page_num in range(1, HARD_PAGE_LIMIT + 1):
                page_url = f"{BASE}/all/sale?keyword={quote(keyword)}&page={page_num}"
                try:
                    r = await client.get(page_url)
                    r.raise_for_status()
                    soup = BeautifulSoup(r.text, "lxml")
                    page_lis = soup.select("li.p-articles-list-item")
                    if not page_lis:
                        break
                    all_lis.extend(page_lis)
                    if len(page_lis) < 50:
                        break  # 最終ページに到達
                except Exception:
                    break

            for li in all_lis:
                title_a = li.select_one("div.p-item-title a")
                price_el = li.select_one("div.p-item-most-important")
                img_el = li.select_one("img.p-item-image")
                desc_el = li.select_one("div.p-item-detail")
                if not title_a:
                    continue
                title = title_a.get_text(strip=True)
                href = title_a.get("href", "")
                item_url = urljoin(BASE, href)
                price = _extract_price(price_el.get_text() if price_el else "")
                image_url = img_el.get("src") if img_el else None
                # ALTから完全タイトルが取れる場合も
                if img_el and img_el.get("alt"):
                    title = img_el.get("alt") if len(img_el.get("alt", "")) > len(title) else title
                desc = desc_el.get_text(" ", strip=True) if desc_el else None
                # 「お問い合わせ受付は終了しました」の商品はスキップ
                full_text = li.get_text(" ", strip=True)
                if "お問い合わせ受付は終了" in full_text:
                    continue
                # 都道府県・市区町村
                loc_parts = []
                for sec in li.select("div.p-item-secondary-important a, div.p-item-supplementary-info a"):
                    t = sec.get_text(strip=True)
                    if t and t not in loc_parts and len(t) <= 20:
                        loc_parts.append(t)
                location = " / ".join(loc_parts[:3]) if loc_parts else None
                items.append(Item(
                    site=SITE, title=title, price=price,
                    condition="中古", image_url=image_url,
                    item_url=item_url, in_stock=price is not None,
                    description=desc, location=location,
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
    items = asyncio.run(search(sys.argv[1] if len(sys.argv) > 1 else "Panasonic NR-B18C2"))
    print(f"取得件数: {len(items)}")
    for it in items[:5]:
        print(it)
