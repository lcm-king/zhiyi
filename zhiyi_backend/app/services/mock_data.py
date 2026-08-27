"""
智医 (ZhiYi) — 演示账号兜底数据
数据库不可用时的登录降级账号（真实环境由数据库种子账号提供）。
"""

USERS = {
    "doctor": {"id": 101, "name": "郑经纬", "role": "doctor", "title": "主治医师", "organization": "长沙市岳麓区社区卫生服务中心", "avatar": "郑"},
    "patient": {"id": 201, "name": "郑经纬", "role": "patient", "title": "患者", "organization": "湖南省长沙市", "avatar": "郑"},
    "admin": {"id": 501, "name": "admin_li", "role": "admin", "title": "平台管理员", "organization": "智医运营中心", "avatar": "a"},
}
