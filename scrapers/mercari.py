"""メルカリ scraper — Apify Actor 経由。

Mercari は Akamai/独自 bot 検知が強く、無料の playwright-stealth では
クライアント側 fetch がサイレントブロックされ取得不可。
Apify Store の成熟した Mercari Japan Actor を呼び出す方式に変更。

採用 Actor: https://apify.com/fatihtahta/mercari-japan-scraper
料金: $3.99 / 1,000 results（pay-per-result）
Free tier: 月 $5 = 約1,250件まで毎月無料
"""
import asyncio
from typing import List, Optional

from core.models import Item
from core.secrets import get_apify_token

SITE = "メルカリ"
ACTOR_ID = "fatihtahta/mercari-japan-scraper"
DEFAULT_LIMIT = 500  # 1検索あたり最大件数（コスト天井 $2 ≈ ¥300 を固定）

# Mercari の condition_id → 表示名
CONDITION_MAP = {
    1: "新品、未使用",
    2: "未使用に近い",
    3: "目立った傷や汚れなし",
    4: "やや傷や汚れあり",
    5: "傷や汚れあり",
    6: "全体的に状態が悪い",
}


async def search(keyword: str) -> List[Item]:
    token = get_apify_token()
    if not token:
        print(f"[{SITE}] APIFY_TOKEN 未設定のためスキップ")
        return []

    try:
        from apify_client import ApifyClientAsync
    except ImportError:
        print(f"[{SITE}] apify-client がインストールされていません")
        return []

    client = ApifyClientAsync(token)
    try:
        # 検索URLベースで投入（keywordフィールドより確実）
        from urllib.parse import quote as urlquote
        search_url = f"https://jp.mercari.com/search?keyword={urlquote(keyword)}&status=on_sale&sort=price&order=asc"
        run = await client.actor(ACTOR_ID).call(
            run_input={
                "startUrls": [{"url": search_url}],
                "limit": DEFAULT_LIMIT,
            },
            timeout_secs=180,
        )
    except Exception as e:
        print(f"[{SITE}] Apify run error: {e}")
        return []

    if not run or not run.get("defaultDatasetId"):
        print(f"[{SITE}] Apify run に dataset がありません")
        return []

    items: List[Item] = []
    try:
        async for rec in client.dataset(run["defaultDatasetId"]).iterate_items():
            # type フィールドがある場合は listing 以外をスキップ
            t = rec.get("type")
            if t and t != "listing":
                continue
            it = _to_item(rec)
            if it:
                items.append(it)
    except Exception as e:
        print(f"[{SITE}] dataset iterate error: {e}")

    print(f"[{SITE}] Apify から {len(items)} 件取得")
    return items


def _to_item(rec: dict) -> Optional[Item]:
    title = rec.get("title") or rec.get("name") or ""
    if not title:
        return None

    # URL: scrape_context.source.item_url が正規パス
    url = (rec.get("scrape_context") or {}).get("source", {}).get("item_url") or rec.get("url")
    if not url:
        lid = rec.get("listing_id") or rec.get("id")
        if lid:
            url = f"https://jp.mercari.com/item/{lid}"
    if not url:
        return None

    # 画像: media.thumbnail_urls[0] → media.photo_urls[0] の順
    image = None
    media = rec.get("media") or {}
    for key in ("thumbnail_urls", "photo_urls"):
        urls = media.get(key) or []
        if urls and isinstance(urls[0], str):
            image = urls[0]
            break
    if not image:
        image = rec.get("thumbnail") or rec.get("thumbnail_url")

    # 価格: 文字列で来るので int 変換
    price = rec.get("price")
    if isinstance(price, str):
        try:
            price = int(price)
        except (ValueError, TypeError):
            price = None

    # 状態: condition_id は文字列 "1"〜"6"
    cond_raw = rec.get("condition_id") or rec.get("itemCondition") or rec.get("item_condition_id")
    try:
        cond_id = int(cond_raw) if cond_raw is not None else None
    except (ValueError, TypeError):
        cond_id = None

    # 在庫判定: listing_status は "ITEM_STATUS_ON_SALE" 形式
    listing_status = (rec.get("listing_status") or rec.get("status") or "").upper()
    in_stock = "ON_SALE" in listing_status or not listing_status

    return Item(
        site=SITE,
        title=title,
        price=price,
        condition=CONDITION_MAP.get(cond_id) or "中古",
        image_url=image,
        item_url=url,
        in_stock=in_stock,
        location=None,  # Apify Actor はリストページのみ取得、地域情報は無い
        shipping_method=None,
        description=rec.get("description"),
    )


if __name__ == "__main__":
    import sys
    items = asyncio.run(search(sys.argv[1] if len(sys.argv) > 1 else "PSP-3000"))
    print(f"取得件数: {len(items)}")
    for it in items[:5]:
        print(f"{it.price} | {it.title[:60]} | {it.location} | {it.condition}")
