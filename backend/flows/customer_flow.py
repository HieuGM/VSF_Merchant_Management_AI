"""Customer Agent Flow stub (Track A)."""
from typing import Any, Dict, List

class CustomerFlowStub:
    def search_restaurants(
        self,
        query: str | None = None,
        cuisine: str | None = None,
        city: str | None = None,
        budget: str | None = None,
        lat: float | None = None,
        lng: float | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        return {
            "trace_id": "tr_stub_customer_001",
            "merchants": [],
            "total": 0,
            "filters_applied": {
                "query": query,
                "cuisine": cuisine,
                "city": city,
                "budget": budget,
            },
        }

customer_flow = CustomerFlowStub()
