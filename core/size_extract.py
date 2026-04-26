"""タイトル/説明文から商品サイズを推定する"""
import re
from typing import Optional, Tuple

# サイズ表記パターン
SIZE_PATTERNS = [
    re.compile(r"(?:サイズ\s*[:：])?\s*(60|80|100|120|140|160|170|180|200|220|240|260)\s*サイズ", re.I),
    re.compile(r"3辺合?計\s*[:：=約]?\s*(\d{2,3})\s*(?:cm|センチ)", re.I),
    re.compile(r"(\d{2,3})\s*(?:cm|センチ)?\s*[x×]\s*(\d{2,3})\s*(?:cm|センチ)?\s*[x×]\s*(\d{2,3})\s*(?:cm|センチ)", re.I),
]

# 商品種別 → 推定3辺合計（家財便ランク用） & サイズ目安
PRODUCT_HINTS = {
    r"冷蔵庫.*?(\d{2,3})\s*L": lambda m: _refrigerator_3sides(int(m.group(1))),
    r"洗濯機.*?(\d{1,2})\s*kg": lambda m: _washer_3sides(int(m.group(1))),
}


def _refrigerator_3sides(liters: int) -> int:
    if liters <= 100:
        return 180
    if liters <= 200:
        return 230
    if liters <= 300:
        return 260
    if liters <= 400:
        return 290
    if liters <= 500:
        return 320
    return 350


def _washer_3sides(kg: int) -> int:
    if kg <= 6:
        return 200
    if kg <= 9:
        return 240
    return 290


def extract_size_info(title: str, description: Optional[str] = None) -> Tuple[Optional[int], Optional[int]]:
    """
    Returns (size_code, sum_3sides_cm)
    size_code: 60, 80, 100, ... (宅急便サイズ)
    sum_3sides_cm: 3辺合計のcm値（家財便ランク判定用）
    """
    blob = " ".join(filter(None, [title, description]))
    if not blob:
        return None, None

    # 1. 「○○サイズ」表記
    m = SIZE_PATTERNS[0].search(blob)
    if m:
        sz = int(m.group(1))
        return sz, sz  # 簡易: サイズコードがそのまま3辺合計目安

    # 2. 「3辺合計○○cm」
    m = SIZE_PATTERNS[1].search(blob)
    if m:
        s3 = int(m.group(1))
        return _3sides_to_size(s3), s3

    # 3. 「縦×横×高さ」
    m = SIZE_PATTERNS[2].search(blob)
    if m:
        s3 = sum(int(g) for g in m.groups())
        return _3sides_to_size(s3), s3

    # 4. 商品種別ヒント
    for pat, fn in PRODUCT_HINTS.items():
        m2 = re.search(pat, blob)
        if m2:
            s3 = fn(m2)
            return _3sides_to_size(s3), s3

    return None, None


def _3sides_to_size(s3: int) -> int:
    """3辺合計cm → 宅急便サイズコード"""
    for s in [60, 80, 100, 120, 140, 160, 170, 180, 200, 220, 240, 260]:
        if s3 <= s:
            return s
    return 260


# 都道府県抽出
PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県",
    "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]

# 略称→正式形マッピング（ジモティーのように「東京」「大阪」と書かれる場合に対応）
SHORT_TO_FULL = {
    "東京": "東京都", "大阪": "大阪府", "京都": "京都府", "北海道": "北海道",
    "青森": "青森県", "岩手": "岩手県", "宮城": "宮城県", "秋田": "秋田県", "山形": "山形県", "福島": "福島県",
    "茨城": "茨城県", "栃木": "栃木県", "群馬": "群馬県", "埼玉": "埼玉県", "千葉": "千葉県", "神奈川": "神奈川県",
    "新潟": "新潟県", "富山": "富山県", "石川": "石川県", "福井": "福井県", "山梨": "山梨県", "長野": "長野県",
    "岐阜": "岐阜県", "静岡": "静岡県", "愛知": "愛知県", "三重": "三重県",
    "滋賀": "滋賀県", "兵庫": "兵庫県", "奈良": "奈良県", "和歌山": "和歌山県",
    "鳥取": "鳥取県", "島根": "島根県", "岡山": "岡山県", "広島": "広島県", "山口": "山口県",
    "徳島": "徳島県", "香川": "香川県", "愛媛": "愛媛県", "高知": "高知県",
    "福岡": "福岡県", "佐賀": "佐賀県", "長崎": "長崎県", "熊本": "熊本県", "大分": "大分県", "宮崎": "宮崎県", "鹿児島": "鹿児島県",
    "沖縄": "沖縄県",
}

# 長い順にソートして部分マッチの誤判定を防ぐ
_SHORT_KEYS = sorted(SHORT_TO_FULL.keys(), key=lambda x: -len(x))
PREF_RE = re.compile("|".join(re.escape(k) for k in PREFECTURES + _SHORT_KEYS))


def extract_prefecture(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    m = PREF_RE.search(text)
    if not m:
        return None
    found = m.group(0)
    return SHORT_TO_FULL.get(found, found)
