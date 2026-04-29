import asyncio
import re
from typing import List
from core.models import Item

from scrapers import (
    surugaya, yahoo_auctions, hardoff_netmall, jmty,
    second_street, bookoff_online,
    mercari, rakuma, paypay_furima,
)

SCRAPERS = [
    ("ヤフオク", yahoo_auctions.search),
    ("ハードオフ", hardoff_netmall.search),
    ("ジモティー", jmty.search),
    ("セカンドストリート", second_street.search),
    ("駿河屋", surugaya.search),
    ("ブックオフ", bookoff_online.search),
    ("メルカリ", mercari.search),
    ("ラクマ", rakuma.search),
    ("PayPayフリマ", paypay_furima.search),
]


def _norm(s: str) -> str:
    return re.sub(r"[\s\-_/\.・]+", "", (s or "").upper())


def _kata_to_hira(s: str) -> str:
    """カタカナをひらがなに変換"""
    return "".join(
        chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c
        for c in s
    )


def _norm_for_exclude(s: str) -> str:
    """除外ワードマッチング用の正規化:
    - 半角カナ→全角カナ（NFKC正規化）
    - カタカナ→ひらがな統一（ジャンク=じゃんく）
    - 大文字小文字を統一
    - スペース・記号除去
    """
    if not s:
        return ""
    import unicodedata
    s = unicodedata.normalize("NFKC", s)  # 半角→全角
    s = _kata_to_hira(s)
    return re.sub(r"[\s\-_/\.・]+", "", s.lower())


def matches_keyword(item: Item, keyword: str) -> bool:
    """型番がタイトル・説明・URLに含まれているか。
    型番らしき部分（英数字+ハイフン混じり）が必ず含まれていることを要求する。
    """
    blob = " ".join(filter(None, [item.title, item.description, item.item_url]))
    if not blob:
        return False
    nt = _norm(blob)
    nk = _norm(keyword)
    if nk in nt:
        return True
    parts = [p for p in re.split(r"\s+", keyword) if p]
    # 型番らしい部分（ハイフン入り or 数字英字混在）を抽出
    model_parts = [p for p in parts if re.search(r"-", p) or (re.search(r"[A-Za-z]", p) and re.search(r"\d", p))]
    if model_parts:
        return all(_norm(p) in nt for p in model_parts)
    # 型番らしいパーツが無いケースは全パーツ一致を要求
    return all(_norm(p) in nt for p in parts)


async def run_one(name, fn, keyword):
    try:
        items = await fn(keyword)
        print(f"[{name}] {len(items)}件 取得")
        return items
    except Exception as e:
        print(f"[{name}] ERROR: {e}")
        return []


def has_excluded_word(item: Item, exclude_words) -> bool:
    """除外ワードがタイトル/説明文に含まれているか。
    カタカナ・ひらがな・大文字小文字を区別せずに判定する。
    例: 除外ワード「ジャンク」→ 商品文中の「じゃんく」「ジャンク品」「ﾌﾞﾗﾝｸ」も検出
    """
    if not exclude_words:
        return False
    blob_norm = _norm_for_exclude(" ".join(filter(None, [item.title, item.description])))
    for w in exclude_words:
        if not w or not w.strip():
            continue
        wn = _norm_for_exclude(w)
        if wn and wn in blob_norm:
            return True
    return False


async def aggregate(keyword: str, exclude_words=None, sites=None) -> List[Item]:
    selected = SCRAPERS if sites is None else [(n, fn) for n, fn in SCRAPERS if n in sites]
    tasks = [run_one(name, fn, keyword) for name, fn in selected]
    results = await asyncio.gather(*tasks)
    all_items: List[Item] = []
    for lst in results:
        all_items.extend(lst)

    # 販売中のみ
    all_items = [i for i in all_items if i.in_stock and i.price is not None]
    # 型番マッチのみ（同サイト内に同型番が複数あれば全て残る）
    matched = [i for i in all_items if matches_keyword(i, keyword)]
    before_exclude = len(matched)
    # 除外ワード
    matched = [i for i in matched if not has_excluded_word(i, exclude_words)]
    excluded = before_exclude - len(matched)
    print(f"\n型番マッチ: {before_exclude}件 / 除外ワードで{excluded}件除外 → 最終{len(matched)}件")
    matched.sort(key=lambda x: x.price if x.price is not None else 1_000_000_000)
    return matched


def filter_items(items, exclude_words=None) -> List[Item]:
    """既存リストに対し除外ワードフィルタを適用（Excel再表示用）"""
    return [i for i in items if not has_excluded_word(i, exclude_words)]
