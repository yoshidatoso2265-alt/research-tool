"""メルカリ便の送料計算（らくらく / ゆうゆう / たのメル便）

メルカリ便はすべて全国一律料金。出発地・到着地に依存しない。
"""
import json
from pathlib import Path
from functools import lru_cache
from typing import Optional, List, Dict

DATA_DIR = Path(__file__).parent.parent / "data"


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(DATA_DIR / "mercari_rates.json", encoding="utf-8") as f:
        return json.load(f)


def list_methods() -> List[Dict[str, str]]:
    """配送方法の一覧を [{key, label, group}, ...] 形式で返す（UI 用）"""
    d = _load()
    out = []
    for grp_key, grp_label in [
        ("rakuraku", "らくらくメルカリ便"),
        ("yuyu", "ゆうゆうメルカリ便"),
    ]:
        for sub_key, sub in d[grp_key].items():
            if sub_key.startswith("_"):
                continue
            out.append({
                "key": f"{grp_key}.{sub_key}",
                "label": sub["name"],
                "group": grp_label,
            })
    out.append({
        "key": "tanomeru",
        "label": "梱包・発送たのメル便",
        "group": "梱包・発送たのメル便",
    })
    return out


def _round_up_to_size(value: int, sizes: List[int]) -> Optional[int]:
    """value 以上の最小サイズを返す。最大値超過時は None"""
    for s in sizes:
        if value <= s:
            return s
    return None


def calc_rate(method_key: str, *, sum_3sides_cm: Optional[int] = None,
              long_cm: Optional[int] = None, thickness_cm: Optional[float] = None,
              weight_kg: Optional[float] = None) -> Dict:
    """配送方法と寸法から料金と適合判定を返す。

    Returns:
        {
            "name": str, "price": int|None, "size_label": str,
            "ok": bool, "reasons": [str, ...], "extras": {"box_fee": int}
        }
    """
    d = _load()
    reasons: List[str] = []

    if method_key == "tanomeru":
        spec = d["tanomeru"]
        if sum_3sides_cm is None:
            return {"name": "梱包・発送たのメル便", "price": None, "size_label": "—",
                    "ok": False, "reasons": ["3辺合計を入力してください"], "extras": {}}
        if weight_kg is not None and weight_kg > spec["max_weight_kg"]:
            reasons.append(f"重量{weight_kg}kgが上限{spec['max_weight_kg']}kg超")
        size = _round_up_to_size(sum_3sides_cm, spec["sizes"])
        if size is None:
            return {"name": "梱包・発送たのメル便", "price": None, "size_label": "規格外",
                    "ok": False, "reasons": [f"3辺合計{sum_3sides_cm}cmが上限{spec['sizes'][-1]}cm超"], "extras": {}}
        idx = spec["sizes"].index(size)
        return {"name": "梱包・発送たのメル便", "price": spec["rates"][idx],
                "size_label": f"{size}サイズ", "ok": not reasons,
                "reasons": reasons, "extras": {}}

    grp_key, sub_key = method_key.split(".", 1)
    spec = d[grp_key][sub_key]
    name = spec["name"]
    extras: Dict[str, int] = {}
    if spec.get("box_fee"):
        extras["box_fee"] = spec["box_fee"]

    # サイズ刻み（宅急便・ゆうパック）
    if "sizes" in spec:
        if sum_3sides_cm is None:
            return {"name": name, "price": None, "size_label": "—", "ok": False,
                    "reasons": ["3辺合計を入力してください"], "extras": extras}
        size = _round_up_to_size(sum_3sides_cm, spec["sizes"])
        if size is None:
            return {"name": name, "price": None, "size_label": "規格外",
                    "ok": False, "reasons": [f"3辺合計{sum_3sides_cm}cmが上限{spec['sizes'][-1]}cm超"],
                    "extras": extras}
        idx = spec["sizes"].index(size)
        if "weights" in spec and weight_kg is not None and weight_kg > spec["weights"][idx]:
            # サイズは合うが重量超過 → 上のサイズを試す
            for i in range(idx + 1, len(spec["sizes"])):
                if weight_kg <= spec["weights"][i]:
                    idx = i
                    size = spec["sizes"][i]
                    break
            else:
                return {"name": name, "price": None, "size_label": f"{size}サイズ",
                        "ok": False, "reasons": [f"重量{weight_kg}kgが上限超"], "extras": extras}
        if "max_weight_kg" in spec and spec["max_weight_kg"] and weight_kg is not None \
                and weight_kg > spec["max_weight_kg"]:
            reasons.append(f"重量{weight_kg}kgが上限{spec['max_weight_kg']}kg超")
        return {"name": name, "price": spec["rates"][idx], "size_label": f"{size}サイズ",
                "ok": not reasons, "reasons": reasons, "extras": extras}

    # 定額（ネコポス・ゆうパケット系・コンパクト・プラス）
    if sum_3sides_cm is not None and spec.get("max_3sides_cm") and sum_3sides_cm > spec["max_3sides_cm"]:
        reasons.append(f"3辺合計{sum_3sides_cm}cmが上限{spec['max_3sides_cm']}cm超")
    if long_cm is not None and spec.get("max_long_cm") and long_cm > spec["max_long_cm"]:
        reasons.append(f"長辺{long_cm}cmが上限{spec['max_long_cm']}cm超")
    if thickness_cm is not None and spec.get("max_thickness_cm") and thickness_cm > spec["max_thickness_cm"]:
        reasons.append(f"厚さ{thickness_cm}cmが上限{spec['max_thickness_cm']}cm超")
    if weight_kg is not None and spec.get("max_weight_kg") and weight_kg > spec["max_weight_kg"]:
        reasons.append(f"重量{weight_kg}kgが上限{spec['max_weight_kg']}kg超")

    label_parts = []
    if spec.get("max_3sides_cm"):
        label_parts.append(f"3辺~{spec['max_3sides_cm']}cm")
    if spec.get("max_thickness_cm"):
        label_parts.append(f"厚~{spec['max_thickness_cm']}cm")
    if spec.get("size_box"):
        label_parts.append(spec["size_box"])
    if spec.get("size_envelope"):
        label_parts.append(spec["size_envelope"])
    label = " / ".join(label_parts) if label_parts else "規格内"

    return {"name": name, "price": spec["price"], "size_label": label,
            "ok": not reasons, "reasons": reasons, "extras": extras}


def find_best_options(*, sum_3sides_cm: Optional[int] = None,
                      long_cm: Optional[int] = None,
                      thickness_cm: Optional[float] = None,
                      weight_kg: Optional[float] = None) -> List[Dict]:
    """寸法から「使える配送方法」を安い順に返す（box_fee 込み）"""
    results = []
    for m in list_methods():
        r = calc_rate(m["key"], sum_3sides_cm=sum_3sides_cm, long_cm=long_cm,
                      thickness_cm=thickness_cm, weight_kg=weight_kg)
        if r["ok"] and r["price"] is not None:
            total = r["price"] + (r["extras"].get("box_fee") or 0)
            results.append({**r, "group": m["group"], "key": m["key"], "total": total})
    results.sort(key=lambda x: x["total"])
    return results
