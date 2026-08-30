"""SRM 实时数据适配层（v2 扩展点）。

v1 不接 SRM 真实接口；此处仅定义接口与桩实现，IntentRouter 预留 tool_call 分支，
后续接入订单/资质/对账等实时查询时实现具体 Connector 即可，无需改动业务代码。
"""
from __future__ import annotations

from typing import Optional


class SRMConnector:
    name = "base"

    async def query_order(self, order_no: str) -> Optional[dict]:
        raise NotImplementedError

    async def query_qualification(self, supplier: str) -> Optional[dict]:
        raise NotImplementedError

    async def query_statement(self, supplier: str) -> Optional[dict]:
        raise NotImplementedError
