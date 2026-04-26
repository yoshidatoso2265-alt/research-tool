from typing import Protocol, List
from core.models import Item


class Scraper(Protocol):
    site_name: str

    async def search(self, keyword: str) -> List[Item]: ...
