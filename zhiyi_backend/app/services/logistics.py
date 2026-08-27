"""
智医 (ZhiYi) — 物流追踪服务
基层医疗AI辅助诊疗平台

核心功能：
  - 调用高德地图路径规划 API 生成配送路线
  - 生成模拟 GPS 坐标点（高德 API 不可用时降级）
  - Redis 缓存路线和实时位置
  - WebSocket 定时推送位置更新
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import re
from typing import Any, Optional

import httpx
import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger("zhiyi.logistics")
settings = get_settings()

# Redis Key 前缀
ROUTE_KEY_PREFIX = "logistics:route"
POSITION_KEY_PREFIX = "logistics:position"
TEMP_KEY_PREFIX = "logistics:temp"
HUB_KEY_PREFIX = "logistics:hub"
ROUTE_TTL = 7 * 24 * 3600  # 路线/温度缓存 7 天，避免旧订单丢失模拟数据

# 模拟起点（药房仓库）和终点（患者地址）的坐标池：支持上海/长沙双城
MOCK_WAREHOUSES = [
    {"lng": 121.23, "lat": 31.05, "name": "上海青浦中心药房"},
    {"lng": 121.42, "lat": 31.22, "name": "上海浦东分拨中心"},
    {"lng": 112.935, "lat": 28.190, "name": "长沙岳麓中心药房"},
    {"lng": 113.040, "lat": 28.135, "name": "长沙雨花分拨中心"},
]

MOCK_DESTINATIONS = [
    {"lng": 121.15, "lat": 31.12, "name": "青浦区朱家角镇"},
    {"lng": 121.38, "lat": 31.28, "name": "浦东新区张江镇"},
    {"lng": 121.08, "lat": 31.02, "name": "松江区佘山镇"},
    {"lng": 112.978, "lat": 28.198, "name": "长沙市五一广场"},
    {"lng": 112.935, "lat": 28.190, "name": "长沙市岳麓区"},
    {"lng": 113.033, "lat": 28.185, "name": "长沙市芙蓉区"},
]


MOCK_HUBS = [
    {"lng": 121.335, "lat": 31.175, "name": "上海虹桥分拨中心"},
    {"lng": 121.47, "lat": 31.19, "name": "上海外高桥分拨中心"},
    {"lng": 121.20, "lat": 31.07, "name": "上海松江分拨中心"},
    {"lng": 113.081, "lat": 28.246, "name": "长沙星沙分拨中心"},
    {"lng": 112.819, "lat": 28.353, "name": "长沙望城分拨中心"},
    {"lng": 112.986, "lat": 28.118, "name": "长沙天心分拨中心"},
]

# 上海主要区域/地标坐标（GCJ-02 近似），用于把收货地址文本解析成地图终点。
# 顺序即优先级：更具体的地标在前，宽泛区名在后，最后才是兜底关键词。
SHANGHAI_PLACES: list[tuple[tuple[str, ...], float, float, str]] = [
    (("张江",), 121.604, 31.205, "浦东新区张江镇"),
    (("金桥",), 121.625, 31.260, "浦东新区金桥"),
    (("外高桥",), 121.595, 31.350, "浦东新区外高桥"),
    (("陆家嘴",), 121.505, 31.240, "浦东新区陆家嘴"),
    (("川沙",), 121.695, 31.190, "浦东新区川沙"),
    (("惠南",), 121.745, 31.050, "浦东新区惠南"),
    (("浦东",), 121.580, 31.220, "浦东新区"),
    (("朱家角",), 121.050, 31.110, "青浦区朱家角"),
    (("徐泾",), 121.265, 31.170, "青浦区徐泾"),
    (("赵巷",), 121.180, 31.120, "青浦区赵巷"),
    (("青浦",), 121.125, 31.150, "青浦区"),
    (("佐山",), 121.190, 31.095, "松江区佐山"),
    (("九亭",), 121.320, 31.130, "松江区九亭"),
    (("泗泾",), 121.250, 31.115, "松江区泗泾"),
    (("松江",), 121.225, 31.030, "松江区"),
    (("辛庄",), 121.380, 31.110, "闵行区辛庄"),
    (("七宝",), 121.350, 31.160, "闵行区七宝"),
    (("虹桥枢纽", "虹桥火车站", "虹桥机场"), 121.330, 31.200, "闵行区虹桥枢纽"),
    (("闵行",), 121.380, 31.080, "闵行区"),
    (("漕河泾",), 121.405, 31.175, "徐汇区漕河泾"),
    (("徐汇",), 121.440, 31.190, "徐汇区"),
    (("静安寺",), 121.450, 31.225, "静安区静安寺"),
    (("静安",), 121.455, 31.230, "静安区"),
    (("人民广场",), 121.475, 31.235, "黄浦区人民广场"),
    (("外滩",), 121.490, 31.240, "黄浦区外滩"),
    (("黄浦",), 121.485, 31.235, "黄浦区"),
    (("五角场",), 121.520, 31.300, "杨浦区五角场"),
    (("杨浦",), 121.520, 31.270, "杨浦区"),
    (("顾村",), 121.400, 31.350, "宝山区顾村"),
    (("大场",), 121.400, 31.315, "宝山区大场"),
    (("宝山",), 121.420, 31.400, "宝山区"),
    (("安亭",), 121.160, 31.300, "嘉定区安亭"),
    (("南翔",), 121.320, 31.290, "嘉定区南翔"),
    (("江桥",), 121.330, 31.240, "嘉定区江桥"),
    (("嘉定",), 121.240, 31.380, "嘉定区"),
    (("长风",), 121.390, 31.230, "普陀区长风"),
    (("普陀",), 121.395, 31.250, "普陀区"),
    (("中山公园",), 121.420, 31.220, "长宁区中山公园"),
    (("长宁",), 121.410, 31.220, "长宁区"),
    (("四川北路",), 121.485, 31.265, "虹口区四川北路"),
    (("虹口",), 121.490, 31.270, "虹口区"),
    (("南桥",), 121.465, 30.920, "奉贤区南桥"),
    (("奉贤",), 121.470, 30.920, "奉贤区"),
    (("朱泾",), 121.160, 30.890, "金山区朱泾"),
    (("金山",), 121.340, 30.750, "金山区"),
    (("城桥",), 121.400, 31.620, "崇明区城桥"),
    (("崇明",), 121.400, 31.620, "崇明区"),
    (("上海",), 121.470, 31.230, "上海市区"),
]

# 长沙主要区域/地标坐标（GCJ-02 近似），用于把收货地址文本解析成地图终点。
# 顺序即优先级：更具体的地标在前，宽泛区名在后，最后才是兜底关键词。
CHANGSHA_PLACES: list[tuple[tuple[str, ...], float, float, str]] = [
    (("黄花机场",), 113.220, 28.190, "长沙县黄花机场"),
    (("高铁南站", "火车南站"), 113.068, 28.150, "雨花区高铁南站"),
    (("长沙火车站", "火车站"), 113.016, 28.195, "芙蓉区长沙火车站"),
    (("五一广场",), 112.978, 28.198, "芙蓉区五一广场"),
    (("橘子洲",), 112.957, 28.175, "岳麓区橘子洲"),
    (("岳麓山",), 112.935, 28.190, "岳麓区岳麓山"),
    (("梅溪湖",), 112.899, 28.200, "岳麓区梅溪湖"),
    (("洋湖",), 112.945, 28.140, "岳麓区洋湖"),
    (("麓谷",), 112.870, 28.220, "岳麓区麓谷"),
    (("月亮岛",), 112.910, 28.305, "望城区月亮岛"),
    (("世界之窗",), 113.080, 28.250, "开福区世界之窗"),
    (("松雅湖",), 113.110, 28.260, "长沙县松雅湖"),
    (("星沙",), 113.081, 28.246, "长沙县星沙"),
    (("马王堆",), 113.030, 28.210, "芙蓉区马王堆"),
    (("红星",), 113.020, 28.110, "雨花区红星"),
    (("岳麓",), 112.935, 28.190, "岳麓区"),
    (("天心",), 112.986, 28.118, "天心区"),
    (("开福",), 112.986, 28.256, "开福区"),
    (("雨花",), 113.040, 28.135, "雨花区"),
    (("芙蓉",), 113.033, 28.185, "芙蓉区"),
    (("望城",), 112.819, 28.353, "望城区"),
    (("长沙县",), 113.081, 28.246, "长沙县"),
    (("宁乡",), 112.551, 28.277, "宁乡市"),
    (("浏阳",), 113.643, 28.141, "浏阳市"),
    (("湘江",), 112.960, 28.200, "长沙湘江沿岸"),
    (("长沙",), 112.940, 28.230, "长沙市"),
]

# 各城市默认解析范围（兜底用）：长沙 / 上海
CITY_RANGES: dict[str, tuple[float, float, float, float]] = {
    "changsha": (112.80, 113.30, 28.05, 28.45),
    "shanghai": (120.98, 121.88, 30.90, 31.45),
}


def _stable_jitter(addr: str) -> tuple[float, float]:
    """根据地址哈希生成 ±0.008 度（约数百米）的稳定偏移，同一地址永远落在同一点。"""
    h = sum(ord(c) * (i + 3) for i, c in enumerate(addr)) if addr else 0
    return ((h % 17) - 8) * 0.001, (((h // 17) % 17) - 8) * 0.001


def _detect_city(addr: str) -> Optional[str]:
    """根据地址关键词判断城市：长沙 / 上海，无法识别时返回 None。"""
    if any(kw in addr for kw in ("长沙", "湖南", "湘", "星沙", "浏阳", "宁乡")):
        return "changsha"
    if any(kw in addr for kw in ("上海", "沪", "青浦", "浦东", "虹桥", "闵行")):
        return "shanghai"
    return None


def resolve_address_coordinates(address: str) -> tuple[float, float, str]:
    """把收货地址文本解析为地图坐标（确定性，非随机）。

    优先按城市关键词（长沙/上海）匹配对应地标库；无城市关键词时使用
    settings.default_logistics_city 指定的默认城市。
    """
    addr = address or ""
    # 实时定位地址：LOC:经度,纬度 ...（由前端浏览器定位生成），直接使用精确坐标
    loc_match = re.search(r"LOC:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", addr, re.IGNORECASE)
    if loc_match:
        lng = float(loc_match.group(1))
        lat = float(loc_match.group(2))
        if 70 <= lng <= 140 and 10 <= lat <= 55:
            return round(lng, 6), round(lat, 6), "当前位置（实时定位）"
    city = _detect_city(addr) or get_settings().default_logistics_city or "changsha"
    places = CHANGSHA_PLACES if city == "changsha" else SHANGHAI_PLACES
    for keywords, lng, lat, name in places:
        for kw in keywords:
            if kw in addr:
                jl, jt = _stable_jitter(addr)
                return round(lng + jl, 6), round(lat + jt, 6), name
    # 兜底：地址哈希决定默认城市范围内一个稳定点
    lng_min, lng_max, lat_min, lat_max = CITY_RANGES.get(
        city, CITY_RANGES["changsha"]
    )
    h = sum(ord(c) for c in addr) if addr else 42
    lng = lng_min + (h % 500) / 1000.0
    lat = lat_min + ((h * 7) % 400) / 1000.0
    city_label = "长沙" if city == "changsha" else "上海"
    return round(lng, 6), round(lat, 6), f"{city_label}（地址解析兜底）"


def _pick_warehouse(dest_lng: float, dest_lat: float) -> dict[str, float]:
    """选择距离收货地址最近的药房仓库作为发货点。"""
    return min(
        MOCK_WAREHOUSES,
        key=lambda w: _geo_distance(dest_lng, dest_lat, w["lng"], w["lat"]),
    )




async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


# =============================================================================
# 路径生成
# =============================================================================

async def generate_route(
    order_id: int,
    from_lng: Optional[float] = None,
    from_lat: Optional[float] = None,
    to_lng: Optional[float] = None,
    to_lat: Optional[float] = None,
    dest_address: Optional[str] = None,
    *,
    need_cold_chain: bool = False,
) -> list[dict[str, float]]:
    """生成配送路径坐标点列表。

    优先调用高德 API 获取真实路径，不可用时生成模拟路径。
    结果缓存到 Redis：logistics:route:{order_id}

    冷链订单（need_cold_chain=True）额外生成 2-8℃ 温度曲线并缓存，
    供 WebSocket 推送与状态查询使用。
    """
    # ── 终点：优先用订单真实收货地址解析坐标，其次显式传入，最后随机兜底 ──
    dest_lng = to_lng
    dest_lat = to_lat
    if dest_lng is None or dest_lat is None:
        if dest_address:
            d_lng, d_lat, _ = resolve_address_coordinates(dest_address)
            dest_lng = d_lng if dest_lng is None else dest_lng
            dest_lat = d_lat if dest_lat is None else dest_lat
        else:
            pick = random.choice(MOCK_DESTINATIONS)
            dest_lng = dest_lng if dest_lng is not None else pick["lng"]
            dest_lat = dest_lat if dest_lat is not None else pick["lat"]

    # ── 起点：选择距离收货地址最近的药房仓库（就近发货） ──
    warehouse = _pick_warehouse(dest_lng, dest_lat)
    origin_lng = from_lng if from_lng is not None else warehouse["lng"]
    origin_lat = from_lat if from_lat is not None else warehouse["lat"]

    positions: list[dict[str, float]] = []

    # 尝试高德 API
    if settings.amap_server_api_key:
        try:
            positions = await _call_amap_direction(
                origin_lng, origin_lat, dest_lng, dest_lat
            )
            if positions:
                logger.info("高德 API 路径生成成功：order_id=%d, 坐标点数=%d", order_id, len(positions))
        except Exception as exc:
            logger.warning("高德 API 调用失败，使用模拟路径：%s", exc)

    if not positions:
        # 降级：生成模拟路径（贝塞尔插值 + 随机抖动）
        hub = _pick_hub(origin_lng, origin_lat, dest_lng, dest_lat)
        positions = _generate_mock_route(origin_lng, origin_lat, dest_lng, dest_lat, hub=hub)
        logger.info("模拟路径生成：order_id=%d, 坐标点数=%d", order_id, len(positions))

    else:
        hub = None  # 高德真实路线，无需模拟中转站

    await _cache_route(order_id, positions)
    await _cache_route_meta(order_id, hub)

    # 冷链：生成并缓存 2-8℃ 温度曲线
    if need_cold_chain:
        temps = _generate_temperature_series(len(positions))
        await _cache_temperatures(order_id, temps)
        logger.info("冷链温度曲线已生成：order_id=%d, 点数=%d, 范围 %.1f~%.1f℃",
                    order_id, len(temps), min(temps), max(temps))

    return positions


async def _call_amap_direction(
    from_lng: float,
    from_lat: float,
    to_lng: float,
    to_lat: float,
) -> Optional[list[dict[str, float]]]:
    """调用高德驾车路径规划 API。"""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{settings.amap_base_url}/direction/driving",
            params={
                "origin": f"{from_lng},{from_lat}",
                "destination": f"{to_lng},{to_lat}",
                "extensions": "all",
                "key": settings.amap_server_api_key,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "1":
            raise RuntimeError(f"高德 API 返回错误：{data.get('info', 'unknown')}")

        # 提取路径节点坐标
        route = data["route"]["paths"][0]
        positions: list[dict[str, float]] = []
        for step in route["steps"]:
            polyline = step.get("polyline", "")
            if polyline:
                for point in polyline.split(";"):
                    parts = point.split(",")
                    if len(parts) == 2:
                        positions.append({"lng": float(parts[0]), "lat": float(parts[1])})

        return positions if positions else None


def _project_to_segment(
    lng1: float, lat1: float, lng2: float, lat2: float, px: float, py: float
) -> tuple[float, float, float]:
    """返回点 (px,py) 在线段 (lng1,lat1)-(lng2,lat2) 上的投影 (lng, lat, t)。"""
    dx, dy = lng2 - lng1, lat2 - lat1
    if dx == 0 and dy == 0:
        return lng1, lat1, 0.0
    t = ((px - lng1) * dx + (py - lat1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return lng1 + t * dx, lat1 + t * dy, t


def _pick_hub(from_lng: float, from_lat: float, to_lng: float, to_lat: float) -> dict[str, float]:
    """选择中转分拨站，保证顺序为 发货点→中转站→收货点。

    优先选投影落在起终点线段中段、且离线最近的真实分拨站；
    若没有合适的中转站正好在路径上（例如发货点离收货点很近），
    则取路径中段点作为“同城中转点”返回，确保中转站永远出现在
    发货点与收货点之间，货车会实际经过该点。
    """
    direct = _geo_distance(from_lng, from_lat, to_lng, to_lat)
    best: Optional[dict[str, float]] = None
    best_score = float("inf")
    best_t = 0.0
    for h in MOCK_HUBS:
        plng, plat, t = _project_to_segment(from_lng, from_lat, to_lng, to_lat, h["lng"], h["lat"])
        off = _geo_distance(plng, plat, h["lng"], h["lat"])  # 站到直线的垂直距离（米）
        # 偏好投影点位于路径中段（t≈0.5）且离线近的站
        score = off + abs(t - 0.5) * max(direct, 3000.0)
        if score < best_score:
            best_score = score
            best = h
            best_t = t
    assert best is not None
    if 0.2 <= best_t <= 0.8 and direct > 2000:
        return best  # 真实中转站就在路径中段附近，直接使用
    # 否则生成同城中转点：取路径中段，保证 发货点→中转站→收货点 顺序
    mid_lng = from_lng + (to_lng - from_lng) * 0.45
    mid_lat = from_lat + (to_lat - from_lat) * 0.45
    return {"lng": round(mid_lng, 6), "lat": round(mid_lat, 6), "name": best["name"] + "（同城中转）"}


def _geo_distance(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """计算两点间距离（米），用于按比例分配各段路线点数。"""
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def _generate_mock_route(
    from_lng: float,
    from_lat: float,
    to_lng: float,
    to_lat: float,
    num_points: int = 30,
    hub: Optional[dict[str, float]] = None,
) -> list[dict[str, float]]:
    """生成平滑配送路线：发货点 → 中转站 → 收货点。

    二次贝塞尔曲线（发货点→中转站、中转站→收货点），
    全程确定性生成（无随机抖动），并通过单调过滤
    保证距离收货地只减不增（越来越近），避免车辆乱跑。
    """
    if hub is None:
        hub = _pick_hub(from_lng, from_lat, to_lng, to_lat)
    hub_lng, hub_lat = hub["lng"], hub["lat"]

    # 固定控制点（确定性，不随机）
    c1_lng = (from_lng + hub_lng) / 2 + 0.004
    c1_lat = (from_lat + hub_lat) / 2 + 0.003
    c2_lng = (hub_lng + to_lng) / 2 - 0.004
    c2_lat = (hub_lat + to_lat) / 2 + 0.003

    # 按距离比例分配两段点数
    d1 = _geo_distance(from_lng, from_lat, hub_lng, hub_lat)
    d2 = _geo_distance(hub_lng, hub_lat, to_lng, to_lat)
    total_d = d1 + d2
    n1 = max(4, round(num_points * d1 / total_d)) if total_d > 0 else num_points // 2
    n2 = max(4, num_points - n1)

    raw: list[tuple[float, float]] = []
    # 第一段：发货点 → 中转站
    for i in range(n1 + 1):
        t = i / n1
        raw.append((
            (1 - t) ** 2 * from_lng + 2 * (1 - t) * t * c1_lng + t ** 2 * hub_lng,
            (1 - t) ** 2 * from_lat + 2 * (1 - t) * t * c1_lat + t ** 2 * hub_lat,
        ))
    # 第二段：中转站 → 收货点（跳过重复的中转站点）
    for i in range(1, n2 + 1):
        t = i / n2
        raw.append((
            (1 - t) ** 2 * hub_lng + 2 * (1 - t) * t * c2_lng + t ** 2 * to_lng,
            (1 - t) ** 2 * hub_lat + 2 * (1 - t) * t * c2_lat + t ** 2 * to_lat,
        ))

    # 单调过滤：只保留距离收货地不增加的点，确保越来越近
    positions: list[dict[str, float]] = []
    last_d = float("inf")
    for lng, lat in raw:
        d = _geo_distance(lng, lat, to_lng, to_lat)
        if d <= last_d:
            positions.append({"lng": round(lng, 6), "lat": round(lat, 6)})
            last_d = d

    # 终点精确落在收货地址
    if positions and (positions[-1]["lng"], positions[-1]["lat"]) != (round(to_lng, 6), round(to_lat, 6)):
        positions.append({"lng": round(to_lng, 6), "lat": round(to_lat, 6)})

    # 兜底：过滤后点太少则用直线插值
    if len(positions) < 3:
        positions = [
            {
                "lng": round(from_lng + (to_lng - from_lng) * (i / num_points), 6),
                "lat": round(from_lat + (to_lat - from_lat) * (i / num_points), 6),
            }
            for i in range(num_points + 1)
        ]

    return positions


async def _cache_route(order_id: int, positions: list[dict[str, float]], ttl: int = ROUTE_TTL) -> None:
    r = await _get_redis()
    try:
        await r.setex(f"{ROUTE_KEY_PREFIX}:{order_id}", ttl, json.dumps(positions))
    finally:
        await r.aclose()


async def _cache_position(order_id: int, position: dict[str, float], ttl: int = ROUTE_TTL) -> None:
    r = await _get_redis()
    try:
        await r.setex(f"{POSITION_KEY_PREFIX}:{order_id}", ttl, json.dumps(position))
    finally:
        await r.aclose()


def _generate_temperature_series(num_points: int, target: float = 5.0) -> list[float]:
    """生成 2-8℃ 冷链温度曲线：目标温度 5℃ + 缓慢波动 + 随机噪声。

    全程保持在 2-8℃ 范围内（模拟合格冷链车），用于前端温度曲线与超温判定。
    """
    temps: list[float] = []
    for i in range(num_points + 1):
        wave = math.sin(i / 4.0) * 0.4  # 缓慢波动
        noise = random.uniform(-0.2, 0.2)
        t = target + wave + noise
        temps.append(round(max(2.0, min(8.0, t)), 1))
    return temps


async def _cache_temperatures(order_id: int, temps: list[float], ttl: int = ROUTE_TTL) -> None:
    r = await _get_redis()
    try:
        await r.setex(f"{TEMP_KEY_PREFIX}:{order_id}", ttl, json.dumps(temps))
    finally:
        await r.aclose()


async def get_cached_temperatures(order_id: int) -> Optional[list[float]]:
    """获取订单冷链温度曲线（无则返回 None）。"""
    r = await _get_redis()
    try:
        data = await r.get(f"{TEMP_KEY_PREFIX}:{order_id}")
        return json.loads(data) if data else None
    finally:
        await r.aclose()


async def _cache_route_meta(order_id: int, hub: Optional[dict[str, float]], ttl: int = ROUTE_TTL) -> None:
    """缓存路线元信息（中转站）。"""
    r = await _get_redis()
    try:
        if hub:
            await r.setex(f"{HUB_KEY_PREFIX}:{order_id}", ttl, json.dumps(hub))
        else:
            await r.delete(f"{HUB_KEY_PREFIX}:{order_id}")
    finally:
        await r.aclose()


async def get_cached_route_meta(order_id: int) -> Optional[dict[str, Any]]:
    """获取路线元信息（中转站），无则返回 None。"""
    r = await _get_redis()
    try:
        data = await r.get(f"{HUB_KEY_PREFIX}:{order_id}")
        return json.loads(data) if data else None
    finally:
        await r.aclose()


async def get_cached_route(order_id: int) -> Optional[list[dict[str, float]]]:
    r = await _get_redis()
    try:
        data = await r.get(f"{ROUTE_KEY_PREFIX}:{order_id}")
        return json.loads(data) if data else None
    finally:
        await r.aclose()


async def get_cached_position(order_id: int) -> Optional[dict[str, float]]:
    r = await _get_redis()
    try:
        data = await r.get(f"{POSITION_KEY_PREFIX}:{order_id}")
        return json.loads(data) if data else None
    finally:
        await r.aclose()


# =============================================================================
# WebSocket 推送引擎
# =============================================================================

async def start_delivery_stream(
    order_id: int,
    positions: list[dict[str, float]],
    websocket_send: Any,  # fastapi.WebSocket.send_json
    interval: float = 2.0,
    temperatures: Optional[list[float]] = None,
    hub: Optional[dict[str, float]] = None,
) -> None:
    """逐点推送配送位置更新到 WebSocket 客户端。

    每 interval 秒推送一个坐标点，直到到达终点。
    状态随位置实时变化：仓库出库 → 前往中转站 → 到达中转站 →
    即将送达 → 已送达；到达终点时自动把订单落库为 delivered。
    冷链订单额外推送当前车厢温度（temperatures）。
    支持客户端断开时优雅退出。

    Args:
        order_id: 订单 ID
        positions: 完整的路径坐标列表
        websocket_send: WebSocket 的 send_json 方法
        interval: 推送间隔（秒），默认 2 秒
        temperatures: 可选，与 positions 对齐的冷链温度曲线
    """
    total = len(positions)
    logger.info("开始配送流推送：order_id=%d, 总点数=%d, 间隔=%.1fs, 冷链=%s",
                order_id, total, interval, bool(temperatures))

    # 计算中转站对应的路线点下标，用于按位置切换实时状态
    hub_index: Optional[int] = None
    if hub and "lng" in hub and "lat" in hub:
        hub_index = min(
            range(total),
            key=lambda k: _geo_distance(
                positions[k]["lng"], positions[k]["lat"], hub["lng"], hub["lat"]
            ),
        )

    for i, pos in enumerate(positions):
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("配送推送被取消：order_id=%d", order_id)
            break

        # 更新 Redis 当前位置
        await _cache_position(order_id, pos)

        progress = round((i + 1) / total * 100, 1)
        is_last = i == total - 1
        temp = temperatures[i] if temperatures and i < len(temperatures) else None
        status_text = _delivery_status_text(i, total, hub_index)

        msg: dict[str, Any] = {
            "type": "delivery_complete" if is_last else "position_update",
            "order_id": order_id,
            "position": pos,
            "progress": progress,
            "status": status_text,
            "index": i + 1,
            "total": total,
        }
        if temp is not None:
            msg["temperature"] = temp
            msg["cold_chain"] = True
            # 超温判定：低于 2℃ 或高于 8℃ 触发告警
            if temp < 2.0 or temp > 8.0:
                msg["temperature_alert"] = True
                logger.warning("冷链超温告警：order_id=%d, 温度=%.1f℃", order_id, temp)

        try:
            await websocket_send(msg)
        except Exception:
            logger.info("WebSocket 连接已断开：order_id=%d", order_id)
            break

        if is_last:
            logger.info("配送完成：order_id=%d", order_id)
            # 货车到达收货点：自动把订单状态落库为已送达
            try:
                from app.crud.drug_crud import deliver_order
                from app.database import async_session_factory

                async with async_session_factory() as db:
                    await deliver_order(db, order_id)
                logger.info("订单已标记送达：order_id=%d", order_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("标记订单已送达失败：order_id=%d, %s", order_id, exc)


def _delivery_status_text(i: int, total: int, hub_index: Optional[int]) -> str:
    """按配送进度生成实时状态文案（位置一变状态就变）。"""
    if i == total - 1:
        return "已送达"
    if total - i <= 3:
        return "即将送达"
    if hub_index is not None:
        if i < hub_index:
            return "仓库已出库，前往中转站"
        if i == hub_index:
            return "已到达中转站，正在分拣"
        return "中转站已发出，正在配送"
    return "配送中"
