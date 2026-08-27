"""
支付宝沙箱支付服务
使用 alipay.trade.precreate 生成扫码支付二维码
"""
from __future__ import annotations

import base64
import json
import os
import time
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import quote, urlencode

logger = logging.getLogger("zhiyi.alipay")

ALIPAY_APPID = os.getenv("ALIPAY_APPID", "")
ALIPAY_PRIVATE_KEY = os.getenv("ALIPAY_PRIVATE_KEY", "")
ALIPAY_PUBLIC_KEY = os.getenv("ALIPAY_PUBLIC_KEY", "")
ALIPAY_NOTIFY_URL = os.getenv("ALIPAY_NOTIFY_URL", "")
ALIPAY_GATEWAY = os.getenv("ALIPAY_GATEWAY", "https://openapi-sandbox.dl.alipaydev.com/gateway.do")
PAY_MOCK = os.getenv("PAY_MOCK", "false").lower() == "true"
ALIPAY_SANDBOX = os.getenv("ALIPAY_SANDBOX", "true").lower() == "true"
APP_DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# 自动补全 PEM 头尾
if ALIPAY_PRIVATE_KEY and "BEGIN" not in ALIPAY_PRIVATE_KEY:
    ALIPAY_PRIVATE_KEY = (
        "-----BEGIN PRIVATE KEY-----\n"
        + ALIPAY_PRIVATE_KEY
        + "\n-----END PRIVATE KEY-----"
    )
if ALIPAY_PUBLIC_KEY and "BEGIN" not in ALIPAY_PUBLIC_KEY:
    ALIPAY_PUBLIC_KEY = (
        "-----BEGIN PUBLIC KEY-----\n"
        + ALIPAY_PUBLIC_KEY
        + "\n-----END PUBLIC KEY-----"
    )


def _sort_params(params: dict) -> str:
    """按 key 字母序排序拼接参数（不含 sign）"""
    keys = sorted(params.keys())
    return "&".join(f"{k}={params[k]}" for k in keys if params[k] not in (None, ""))


def _rsa_sign(content: str) -> Optional[str]:
    """RSA2-SHA256 签名"""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend

        key = serialization.load_pem_private_key(
            ALIPAY_PRIVATE_KEY.encode(), password=None, backend=default_backend()
        )
        sig = key.sign(content.encode(), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(sig).decode()
    except Exception as e:
        logger.error("RSA 签名失败: %s", e)
        return None


def _rsa_verify(content: str, signature: str) -> bool:
    """RSA2-SHA256 验签"""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend

        key = serialization.load_pem_public_key(
            ALIPAY_PUBLIC_KEY.encode(), backend=default_backend()
        )
        sig = base64.b64decode(signature)
        key.verify(sig, content.encode(), padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception:
        return False


def _call_alipay(method: str, biz_content: dict) -> dict:
    """调用支付宝沙箱 API"""
    params = {
        "app_id": ALIPAY_APPID,
        "method": method,
        "format": "JSON",
        "charset": "utf-8",
        "sign_type": "RSA2",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "1.0",
        "notify_url": ALIPAY_NOTIFY_URL,
        "biz_content": json.dumps(biz_content, ensure_ascii=False),
    }

    sign_str = _sort_params(params)
    signature = _rsa_sign(sign_str)
    if not signature:
        raise RuntimeError("RSA 签名失败，请检查私钥配置")
    params["sign"] = signature

    # 发送请求
    import urllib.request
    body = urlencode(params).encode("utf-8")
    req = urllib.request.Request(ALIPAY_GATEWAY, data=body, method="POST")
    resp = urllib.request.urlopen(req, timeout=15)
    raw = json.loads(resp.read().decode("utf-8"))

    # 解析响应
    key = method.replace(".", "_") + "_response"
    data = raw.get(key, {})
    code = data.get("code", "")
    if code != "10000":
        msg = data.get("sub_msg") or data.get("msg") or code
        logger.error("支付宝 API 失败 [%s]: %s", method, msg)
        raise RuntimeError(f"支付宝错误: {msg}")
    return data


def generate_payment_url(
    out_trade_no: str,
    subject: str,
    total_amount: float,
) -> dict:
    """
    生成扫码支付二维码。

    返回:
        qr_code: 支付宝扫描支付短链接（如 qr.alipay.com/xxx）
        qr_data_url: Base64 二维码图片
        trade_no: 交易号
    """
    if PAY_MOCK and APP_DEBUG:
        return {
            "qr_code": "",
            "qr_data_url": "",
            "trade_no": f"MOCK{int(time.time() * 1000)}",
            "mock": True,
        }
    if not ALIPAY_APPID:
        raise RuntimeError("未配置支付宝 AppID，且当前不是调试模式")

    biz_content = {
        "out_trade_no": out_trade_no,
        "total_amount": f"{total_amount:.2f}",
        "subject": subject,
        "product_code": "FACE_TO_FACE_PAYMENT",  # 当面付 → 扫码支付
    }

    try:
        result = _call_alipay("alipay.trade.precreate", biz_content)
        qr_code = result.get("qr_code", "")

        # 生成二维码图片
        qr_data_url = ""
        if qr_code:
            try:
                import io
                import qrcode
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=3,
                    border=2,
                )
                qr.add_data(qr_code)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                qr_data_url = (
                    "data:image/png;base64,"
                    + base64.b64encode(buf.getvalue()).decode()
                )
            except Exception as e:
                logger.warning("二维码图片生成失败: %s", e)

        return {
            "qr_code": qr_code,
            "qr_data_url": qr_data_url,
            "trade_no": result.get("out_trade_no", out_trade_no),
            "mock": False,
        }
    except Exception as e:
        logger.warning("支付宝 precreate 失败: %s", e)
        if APP_DEBUG or ALIPAY_SANDBOX:
            return {
                "qr_code": "",
                "qr_data_url": "",
                "trade_no": f"ALIPAY{int(time.time() * 1000)}",
                "mock": True,
            }
        raise


def query_payment(out_trade_no: str) -> dict:
    """查询支付状态"""
    if PAY_MOCK and APP_DEBUG:
        return {"trade_status": "TRADE_SUCCESS", "mock": True}

    try:
        result = _call_alipay(
            "alipay.trade.query",
            {"out_trade_no": out_trade_no},
        )
        return {
            "trade_status": result.get("trade_status", "WAIT_BUYER_PAY"),
            "trade_no": result.get("trade_no", ""),
            "total_amount": result.get("total_amount", "0"),
            "mock": False,
        }
    except Exception as e:
        logger.warning("支付查询失败: %s", e)
        if APP_DEBUG or ALIPAY_SANDBOX:
            return {"trade_status": "UNKNOWN", "mock": False}
        raise
