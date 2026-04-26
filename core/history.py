"""検索履歴の保存・読込（JSONベース、Excelは作らない）"""
import json
from pathlib import Path
from datetime import datetime
from typing import List
from dataclasses import asdict
from core.models import Item

HISTORY_DIR = Path(__file__).parent.parent / "history"
HISTORY_DIR.mkdir(exist_ok=True)
INDEX_PATH = HISTORY_DIR / "index.jsonl"


def save_history(keyword: str, items: List[Item]) -> Path:
    """検索結果を履歴に保存。1検索 = 1ファイル + indexに1行追記"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_kw = keyword.replace("/", "_").replace(" ", "_")
    fname = f"{safe_kw}_{timestamp}.json"
    path = HISTORY_DIR / fname

    payload = {
        "keyword": keyword,
        "timestamp": timestamp,
        "datetime": datetime.now().isoformat(),
        "count": len(items),
        "items": [asdict(it) for it in items],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    # index 1行追記
    summary = {
        "file": fname,
        "keyword": keyword,
        "datetime": payload["datetime"],
        "count": len(items),
        "min_price": min((i.price for i in items if i.price), default=None),
        "max_price": max((i.price for i in items if i.price), default=None),
        "sites": list({i.site for i in items}),
    }
    with open(INDEX_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")

    return path


def list_history() -> List[dict]:
    """履歴indexを新しい順で返す"""
    if not INDEX_PATH.exists():
        return []
    out = []
    seen_files = set()
    with open(INDEX_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            fn = rec.get("file")
            if fn in seen_files:
                continue
            seen_files.add(fn)
            out.append(rec)
    out.sort(key=lambda x: x.get("datetime", ""), reverse=True)
    return out


def load_history(file_name: str) -> List[Item]:
    path = HISTORY_DIR / file_name
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return [Item(**rec) for rec in payload.get("items", [])]


def import_legacy_excel(results_dir: Path) -> int:
    """既存のresults/*.xlsxを履歴に取り込む（一度きりのマイグレーション）"""
    import pandas as pd
    if not results_dir.exists():
        return 0
    imported = 0
    existing_kws = {(h.get("keyword"), h.get("count")) for h in list_history()}
    for xlsx in sorted(results_dir.glob("*.xlsx")):
        try:
            df = pd.read_excel(xlsx)
        except Exception:
            continue
        items = []
        for _, row in df.iterrows():
            items.append(Item(
                site=str(row.get("サイト", "")),
                title=str(row.get("タイトル", "")),
                price=int(row["価格"]) if "価格" in row and not (row["価格"] is None or (isinstance(row["価格"], float) and row["価格"] != row["価格"])) else None,
                condition=str(row.get("状態", "中古")) if row.get("状態") is not None else None,
                image_url=str(row["画像URL"]) if "画像URL" in row and row["画像URL"] is not None and str(row["画像URL"]) != "nan" else None,
                item_url=str(row.get("商品リンク", "")),
                in_stock=True,
                location=str(row["発送元"]) if "発送元" in row and row["発送元"] is not None and str(row["発送元"]) != "nan" else None,
            ))
        # ファイル名から keyword を逆引き
        stem = xlsx.stem
        # "Panasonic_NR-B18C2_20260426_1525" → "Panasonic NR-B18C2"
        parts = stem.rsplit("_", 2)
        kw = parts[0].replace("_", " ") if len(parts) >= 3 else stem
        if (kw, len(items)) in existing_kws:
            continue
        save_history(kw, items)
        imported += 1
    return imported
