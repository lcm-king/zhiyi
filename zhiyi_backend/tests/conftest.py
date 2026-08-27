"""
智医后端测试基础设施

使用 SQLite 内存库 + 依赖覆盖，避免污染开发 MySQL；
测试不触发 FastAPI lifespan，因此不会启动 RabbitMQ / 知识库初始化。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token, hash_password
from app.database import Base, get_db
from app.models import (
    Doctor,
    Drug,
    Gender,
    Hospital,
    HospitalLevel,
    Patient,
    User,
    UserRole,
)

_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = async_sessionmaker(_engine, expire_on_commit=False)


async def _init_db() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(scope="session", autouse=True)
def _prepare_db():
    asyncio.run(_init_db())


async def _override_get_db():
    async with TestSession() as session:
        yield session


@pytest.fixture
def client():
    from app.main import app

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def db_count(model) -> int:
    async def _run() -> int:
        async with TestSession() as session:
            result = await session.execute(select(func.count()).select_from(model))
            return int(result.scalar() or 0)
    return asyncio.run(_run())


def _unique_phone() -> str:
    return "139" + str(uuid.uuid4().int)[-8:]


async def _seed_user(*, role: str) -> dict:
    phone = _unique_phone()
    username = f"{role}_{uuid.uuid4().hex[:8]}"
    async with TestSession() as session:
        hospital = Hospital(
            name="测试医院",
            level=HospitalLevel.TOWNSHIP,
            address="测试地址",
        )
        session.add(hospital)
        await session.flush()

        user = User(
            username=username,
            phone=phone,
            password_hash=hash_password("12345678"),
            role=UserRole(role),
        )
        session.add(user)
        await session.flush()

        result: dict = {"user_id": user.id, "username": username, "phone": phone}
        if role == "doctor":
            doctor = Doctor(
                user_id=user.id,
                name="测试医生",
                department="全科",
                hospital_id=hospital.id,
            )
            session.add(doctor)
            await session.flush()
            result["doctor_id"] = doctor.id
        elif role == "patient":
            patient = Patient(
                user_id=user.id,
                name="测试患者",
                gender=Gender.M,
                birth_date=datetime(1990, 1, 1),
                phone=phone,
            )
            session.add(patient)
            await session.flush()
            result["patient_id"] = patient.id
        await session.commit()
        return result


@pytest.fixture
def seeded_patient() -> dict:
    return asyncio.run(_seed_user(role="patient"))


@pytest.fixture
def seeded_doctor() -> dict:
    return asyncio.run(_seed_user(role="doctor"))


@pytest.fixture
def seeded_drug() -> dict:
    async def _run() -> dict:
        async with TestSession() as session:
            drug = Drug(
                name=f"测试处方药{uuid.uuid4().hex[:6]}",
                specification="10mg",
                price=10.0,
                stock=100,
                need_prescription=True,
                is_active=True,
            )
            session.add(drug)
            await session.commit()
            await session.refresh(drug)
            return {"id": drug.id, "name": drug.name}
    return asyncio.run(_run())


def auth_header(user_id: int, role: str) -> dict[str, str]:
    token = create_access_token(user_id, role)
    return {"Authorization": f"Bearer {token}"}
