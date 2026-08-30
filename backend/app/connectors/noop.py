"""未对接桩：返回统一提示，避免调用方崩溃。"""
from __future__ import annotations

from app.connectors.base import SRMConnector


class NoopSRMConnector(SRMConnector):
    name = "noop"

    async def query_order(self, order_no: str):
        return {
            "connected": False,
            "message": "当前为独立演示版，尚未接入 SRM 实时业务数据（订单/资质/对账）。"
            "该功能将在 v2 通过 SRMConnector 适配层实现。",
        }

    async def query_qualification(self, supplier: str):
        return {
            "connected": False,
            "message": "当前为独立演示版，尚未接入 SRM 实时资质数据。",
        }

    async def query_statement(self, supplier: str):
        return {
            "connected": False,
            "message": "当前为独立演示版，尚未接入 SRM 实时对账数据。",
        }


def get_connector() -> SRMConnector:
    return NoopSRMConnector()
