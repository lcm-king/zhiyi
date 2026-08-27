"""支付接口鉴权测试：未登录不得创建/查询支付。"""

from __future__ import annotations


def test_payment_create_requires_auth(client):
    resp = client.post(
        "/api/pay/alipay/create",
        json={"order_id": 1, "order_type": "drug", "amount": 0.01},
    )
    assert resp.status_code in (401, 403)


def test_payment_query_requires_auth(client):
    resp = client.get(
        "/api/pay/alipay/query",
        params={"out_trade_no": "ZHIYI_drug_1_1_1"},
    )
    assert resp.status_code in (401, 403)
