from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Item:
    site: str
    title: str
    price: Optional[int]
    condition: Optional[str]
    image_url: Optional[str]
    item_url: str
    in_stock: bool = True
    raw_status: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    shipping_method: Optional[str] = None  # 例: らくらくメルカリ便、ゆうパック
    shipping_size: Optional[str] = None  # 例: 100サイズ、3辺合計230cm

    def to_row(self) -> dict:
        return asdict(self)
