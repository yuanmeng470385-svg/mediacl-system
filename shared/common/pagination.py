"""
分页工具
"""

from typing import Optional, List, Any, Dict
from dataclasses import dataclass


@dataclass
class PaginationParams:
    page: int = 1
    page_size: int = 20
    max_page_size: int = 100

    def __post_init__(self):
        if self.page < 1:
            self.page = 1
        if self.page_size < 1:
            self.page_size = 20
        if self.page_size > self.max_page_size:
            self.page_size = self.max_page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def paginate(
    items: List[Any],
    total: int,
    page: int = 1,
    page_size: int = 20
) -> Dict:
    """生成分页响应"""
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }
