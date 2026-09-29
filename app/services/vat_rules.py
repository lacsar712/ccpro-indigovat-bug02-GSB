"""染缸状态业务规则。"""

from decimal import Decimal
from typing import Optional

from app.models import DipLot, Vat


class VatRuleError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def validate_volume(value: Decimal) -> Decimal:
    """缸容必须是有限的正数（升）。拒绝 0、负数、NaN/Infinity。"""
    volume = Decimal(value)
    if volume.is_nan() or volume.is_infinite() or volume <= 0:
        raise VatRuleError("缸容升数必须为正数。")
    return volume


def assert_can_mark_ready(latest: Optional[DipLot]) -> None:
    """不能将染缸标为 ready，除非最新浸染批次 redoxMv 已填且 <= -500。"""
    if latest is None or latest.redoxMv is None or Decimal(latest.redoxMv) > Decimal("-500"):
        raise VatRuleError(
            "无法设为可染色：最新浸染批次的氧化还原电位为空或高于 -500 mV。"
        )


def validate_vat_status_change(vat: Vat, new_status: str, latest: Optional[DipLot]) -> None:
    if new_status == Vat.STATUS_READY:
        assert_can_mark_ready(latest)
