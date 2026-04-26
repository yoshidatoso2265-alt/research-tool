"""4社（ヤマト宅急便・ゆうパック・佐川・らくらく家財便）の送料計算"""
import json
from pathlib import Path
from functools import lru_cache
from typing import Optional, Dict

DATA_DIR = Path(__file__).parent.parent / "data"


@lru_cache(maxsize=1)
def load_zones() -> Dict[str, str]:
    with open(DATA_DIR / "shipping_zones.json", encoding="utf-8") as f:
        z = json.load(f)
    return {k: v for k, v in z.items() if not k.startswith("_")}


@lru_cache(maxsize=1)
def load_yamato():
    with open(DATA_DIR / "yamato_rates.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_yupack():
    with open(DATA_DIR / "yupack_rates.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_sagawa():
    with open(DATA_DIR / "sagawa_rates.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_kazai():
    with open(DATA_DIR / "karuraku_kazai_rates.json", encoding="utf-8") as f:
        return json.load(f)


def prefecture_to_zone(prefecture: str) -> Optional[str]:
    """都道府県名 → 配送地区名"""
    if not prefecture:
        return None
    zones = load_zones()
    if prefecture in zones:
        return zones[prefecture]
    # 緩い一致
    for k, v in zones.items():
        if k in prefecture or prefecture in k:
            return v
    return None


def yamato_rate(from_zone: str, to_zone: str, size: int) -> Optional[int]:
    data = load_yamato()
    rates = data.get("rates", {}).get(from_zone, {}).get(to_zone)
    if not rates:
        return None
    sizes = data["sizes"]
    return _pick_size_rate(rates, sizes, size)


def yupack_rate(from_zone: str, to_zone: str, size: int) -> Optional[int]:
    data = load_yupack()
    if size > data["max_size"]:
        return None
    rates = data.get("rates", {}).get(from_zone, {}).get(to_zone)
    if not rates:
        return None
    sizes = data["sizes"]
    return _pick_size_rate(rates, sizes, size)


def sagawa_rate(from_zone: str, to_zone: str, size: int) -> Optional[int]:
    data = load_sagawa()
    if size > data["max_size"]:
        return None
    sz = _round_to_size(size, data["sizes"])
    if sz <= 160:
        base = yamato_rate(from_zone, to_zone, sz)
        if base is None:
            return None
        offset = data.get("size_offsets", {}).get(str(sz), 0)
        return max(base + offset, 800)
    # 170超サイズはヤマトには無いので160料金 + サイズ加算
    base = yamato_rate(from_zone, to_zone, 160)
    if base is None:
        return None
    offset = data.get("size_offsets", {}).get(str(sz), 0)
    return base + offset


def kazai_rank_for_3sides(sum_3sides_cm: int) -> Optional[str]:
    if sum_3sides_cm is None:
        return None
    if sum_3sides_cm <= 200:
        return "A"
    if sum_3sides_cm <= 250:
        return "B"
    if sum_3sides_cm <= 300:
        return "C"
    if sum_3sides_cm <= 350:
        return "D"
    return None


def kazai_rate(from_zone: str, to_zone: str, rank: str) -> Optional[int]:
    if rank not in ("A", "B", "C", "D"):
        return None
    data = load_kazai()
    dist = data["zone_distance"].get(from_zone, {}).get(to_zone)
    if not dist:
        return None
    rate_key = data["distance_to_rate_key"][dist]
    return data["rates"][rate_key].get(rank)


def estimate_all_carriers(
    from_prefecture: str,
    to_prefecture: str = "東京都",
    size: Optional[int] = None,
    sum_3sides_cm: Optional[int] = None,
) -> Dict[str, dict]:
    """発地→着地で4社の料金を推定。

    Returns: { carrier_name: {price: int|None, label: str, note: str} }
    """
    fz = prefecture_to_zone(from_prefecture)
    tz = prefecture_to_zone(to_prefecture)
    out: Dict[str, dict] = {}
    if not fz or not tz:
        return out

    # 宅急便系（サイズが指定されている場合）
    if size is not None:
        for name, fn, max_size in [
            ("ヤマト宅急便", yamato_rate, 200),
            ("ゆうパック", yupack_rate, 170),
            ("佐川急便", sagawa_rate, 260),
        ]:
            if size > max_size:
                out[name] = {"price": None, "label": f"{size}サイズ", "note": f"取扱不可（最大{max_size}サイズ）"}
                continue
            price = fn(fz, tz, size)
            out[name] = {
                "price": price,
                "label": f"{_round_to_size(size, [60,80,100,120,140,160,170,180,200,220,240,260])}サイズ",
                "note": "" if price else "料金不明",
            }

    # 家財便（3辺合計が指定されているか、size>200のとき）
    if sum_3sides_cm is None and size is not None and size >= 180:
        sum_3sides_cm = size  # 近似（サイズ≒3辺合計とみなす）
    if sum_3sides_cm is not None:
        rank = kazai_rank_for_3sides(sum_3sides_cm)
        if rank:
            price = kazai_rate(fz, tz, rank)
            out["らくらく家財便"] = {
                "price": price,
                "label": f"{rank}ランク (3辺合計~{[200,250,300,350][ord(rank)-ord('A')]}cm)",
                "note": "",
            }
        else:
            out["らくらく家財便"] = {
                "price": None, "label": "規格外",
                "note": "3辺合計350cm超は取扱不可",
            }

    return out


def _pick_size_rate(rates_array, sizes, requested_size: int) -> Optional[int]:
    """サイズ配列から最も近い（または直上の）サイズの料金を返す"""
    target = _round_to_size(requested_size, sizes)
    if target in sizes:
        return rates_array[sizes.index(target)]
    return None


def _round_to_size(size: int, sizes_list) -> int:
    """指定サイズ以上の最小サイズを返す"""
    for s in sizes_list:
        if size <= s:
            return s
    return sizes_list[-1]
