"""
智医 (ZhiYi) — 按患者病历重新生成检查报告（演示数据刷新工具）

将所有已支付/已完成但尚无报告、或旧版静态 seed 报告，按患者病历重新生成为
确定性动态报告（同一患者+检查项目永远相同）。

用法（后端容器内）：
    docker exec -w /app zhiyi-backend python -m app.services.regenerate_dynamic_reports
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.crud import exam_crud
from app.database import async_session_factory
from app.models import AppointmentStatus, ExamAppointment


async def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    async with async_session_factory() as db:
        result = await db.execute(
            select(ExamAppointment).where(
                ExamAppointment.status.in_(
                    [
                        AppointmentStatus.PAID,
                        AppointmentStatus.CONFIRMED,
                        AppointmentStatus.COMPLETED,
                    ]
                )
            )
        )
        appointments = list(result.scalars().all())

        regenerated = 0
        for appointment in appointments:
            old_source = (appointment.report_data or {}).get("source")
            # 跳过已是动态生成的报告（保持确定性结果稳定）
            if old_source == "ai-dynamic":
                continue
            await exam_crud.auto_generate_report(db, appointment, force=True)
            regenerated += 1

        await db.commit()
        print(f"共扫描 {len(appointments)} 条预约，重新生成 {regenerated} 份动态报告")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
