# -*- coding: utf-8 -*-
# 智医 (ZhiYi) — 刷新存量动态报告的 AI 解读文本
#
# 早期版本把整段 summary 拼进 ai_interpretation 导致文字重复；本脚本用当前
# report_generator.generate_interpretation 对所有 source=ai-dynamic 的报告重算解读。
# report_data 本身（确定性种子生成）保持不变。
#
# 用法（后端容器内）：
#     docker exec -w /app zhiyi-backend python -m app.services.refresh_report_interpretations

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.crud import exam_crud
from app.database import async_session_factory
from app.models import AppointmentStatus, ExamAppointment
from app.services.report_generator import generate_interpretation


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

        refreshed = 0
        for appointment in appointments:
            report_data = appointment.report_data or {}
            if report_data.get("source") != "ai-dynamic":
                continue
            item = await exam_crud.get_exam_item_by_id(db, appointment.exam_item_id)
            exam_name = item.name if item else "检查"
            new_interp = generate_interpretation(exam_name, report_data)
            if new_interp != (appointment.ai_interpretation or ""):
                appointment.ai_interpretation = new_interp
                refreshed += 1

        await db.commit()
        print(f"共扫描 {len(appointments)} 条预约，刷新 {refreshed} 条 AI 解读")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
