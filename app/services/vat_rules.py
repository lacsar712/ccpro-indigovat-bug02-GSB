"""染缸状态业务规则。"""

from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import DipLot, Vat


class VatRuleError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class VatConcurrentUpdateError(Exception):
    """条件更新未命中任何行：缸容已被他人先改。"""


VOLUME_QUANTUM = Decimal("0.01")
VOLUME_MAX = Decimal("99999999.99")


def parse_volume_liters(raw: str) -> Decimal:
    """解析并校验缸容：有限正数（单位：升），按列精度保留两位小数。"""
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        raise VatRuleError("缸容无效：请填写数字升数。")
    # NaN / Infinity 与 0、负数一律拒绝
    if not value.is_finite() or value <= 0:
        raise VatRuleError("缸容必须为正数（升），不能为 0、负数或非数字。")
    # 列类型 Numeric(10,2)：量化后若变 0（如 0.001）或超上限，提前拒绝，避免落库成 0 / 500
    try:
        value = value.quantize(VOLUME_QUANTUM)
    except InvalidOperation:
        raise VatRuleError("缸容超出允许范围（最大 99,999,999.99 升）。")
    if value <= 0:
        raise VatRuleError("缸容过小：至少需要 0.01 升。")
    if value > VOLUME_MAX:
        raise VatRuleError("缸容超出允许范围（最大 99,999,999.99 升）。")
    return value


def update_vat_volume(db: Session, vat_id: int, expected_version: int, volume: Decimal) -> None:
    """带乐观锁的缸容改写：版本戳不匹配则抛 VatConcurrentUpdateError，至多一笔并发提交生效。"""
    result = db.execute(
        update(Vat)
        .where(Vat.id == vat_id, Vat.lock_version == expected_version)
        .values(volumeL=volume, lock_version=Vat.lock_version + 1)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        # 行已被并发事务先改（或缸已不存在）；条件 UPDATE 不覆盖他人结果
        db.rollback()
        raise VatConcurrentUpdateError(vat_id)
    db.commit()


def assert_can_mark_ready(latest: Optional[DipLot]) -> None:
    """不能将染缸标为 ready，除非最新浸染批次 redoxMv 已填且 <= -500。"""
    if latest is None or latest.redoxMv is None or Decimal(latest.redoxMv) > Decimal("-500"):
        raise VatRuleError(
            "无法设为可染色：最新浸染批次的氧化还原电位为空或高于 -500 mV。"
        )


def validate_vat_status_change(vat: Vat, new_status: str, latest: Optional[DipLot]) -> None:
    if new_status == Vat.STATUS_READY:
        assert_can_mark_ready(latest)
