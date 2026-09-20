"""
SDK client para a API da Shopee (Open Platform).

Toda requisição autenticada na Shopee exige uma assinatura HMAC-SHA256
montada com: partner_id + api_path + timestamp (+ access_token + shop_id, quando aplicável).

Referência: https://open.shopee.com/developer-guide/12
"""

import hashlib
import hmac
import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# TTL padrão do access_token da Shopee: 4 horas
SHOPEE_ACCESS_TOKEN_TTL_HOURS = 4


class ShopeeClient:
    """Cliente para a Shopee Open Platform API v2."""

    def __init__(self) -> None:
        self.base_url = settings.shopee_api_base_url
        self.partner_id = int(settings.shopee_partner_id) if settings.shopee_partner_id else 0
        self.partner_key = settings.shopee_partner_key
        self.redirect_uri = settings.shopee_redirect_uri

    # ── Assinatura ────────────────────────────────────────────────────────

    def _sign(self, path: str, timestamp: int, access_token: str = "", shop_id: int = 0) -> str:
        """
        Gera a assinatura HMAC-SHA256 requerida pela Shopee.

        Base string: {partner_id}{path}{timestamp}[{access_token}][{shop_id}]
        """
        base = f"{self.partner_id}{path}{timestamp}"
        if access_token:
            base += access_token
        if shop_id:
            base += str(shop_id)
        return hmac.new(
            self.partner_key.encode(), base.encode(), hashlib.sha256
        ).hexdigest()

    def _common_params(
        self, path: str, access_token: str = "", shop_id: int = 0
    ) -> dict:
        """Retorna os parâmetros de autenticação comuns a todas as requisições."""
        ts = int(time.time())
        return {
            "partner_id": self.partner_id,
            "timestamp": ts,
            "sign": self._sign(path, ts, access_token, shop_id),
        }

    # ── OAuth ─────────────────────────────────────────────────────────────

    def get_auth_url(self, user_id: str) -> str:
        """
        Monta a URL de autorização OAuth da Shopee.

        O `state` é o user_id interno do SaaS para rastrear o callback.
        """
        path = "/api/v2/shop/auth_partner"
        ts = int(time.time())
        sign = self._sign(path, ts)
        params = {
            "partner_id": self.partner_id,
            "timestamp": ts,
            "sign": sign,
            "redirect": self.redirect_uri,
        }
        return f"{self.base_url}{path}?{urlencode(params)}&state={user_id}"

    def exchange_code(self, code: str, shop_id: int) -> dict:
        """
        Troca o authorization code por access_token e refresh_token.

        Args:
            code: Código retornado pelo redirect OAuth da Shopee.
            shop_id: ID da loja do vendedor na Shopee.

        Returns:
            Dict com access_token, refresh_token, expire_in, request_id.
        """
        path = "/api/v2/auth/token/get"
        params = self._common_params(path)
        payload = {
            "code": code,
            "shop_id": shop_id,
            "partner_id": self.partner_id,
        }
        with httpx.Client(base_url=self.base_url, timeout=15.0) as client:
            response = client.post(path, params=params, json=payload)
            response.raise_for_status()
            return response.json()

    def refresh_token(self, refresh_token: str, shop_id: int) -> dict:
        """
        Renova o access_token usando o refresh_token.

        Returns:
            Dict com novos access_token, refresh_token e expire_in.
        """
        path = "/api/v2/auth/access_token/get"
        params = self._common_params(path)
        payload = {
            "refresh_token": refresh_token,
            "shop_id": shop_id,
            "partner_id": self.partner_id,
        }
        with httpx.Client(base_url=self.base_url, timeout=15.0) as client:
            response = client.post(path, params=params, json=payload)
            response.raise_for_status()
            return response.json()

    def get_shop_info(self, access_token: str, shop_id: int) -> dict:
        """
        Retorna informações da loja do vendedor autenticado.

        Returns:
            Dict com shop_name, shop_id, status, etc.
        """
        path = "/api/v2/shop/get_shop_info"
        params = {
            **self._common_params(path, access_token, shop_id),
            "access_token": access_token,
            "shop_id": shop_id,
        }
        with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
            response = client.get(path, params=params)
            response.raise_for_status()
            return response.json()

    # ── Estoque ───────────────────────────────────────────────────────────

    def update_stock(
        self,
        item_id: int,
        model_id: int,
        quantity: int,
        access_token: str,
        shop_id: int,
    ) -> dict:
        """
        Atualiza a quantidade em estoque de um produto/variação na Shopee.

        Args:
            item_id: ID do produto na Shopee.
            model_id: ID da variação/modelo (0 se não houver variação).
            quantity: Nova quantidade em estoque.
            access_token: Token de acesso do vendedor.
            shop_id: ID da loja na Shopee.

        Returns:
            Resposta da API da Shopee.
        """
        path = "/api/v2/product/update_stock"
        params = {
            **self._common_params(path, access_token, shop_id),
            "access_token": access_token,
            "shop_id": shop_id,
        }
        payload = {
            "item_id": item_id,
            "stock_list": [{"model_id": model_id, "normal_stock": quantity}],
        }
        with httpx.Client(base_url=self.base_url, timeout=15.0) as client:
            response = client.post(path, params=params, json=payload)
            response.raise_for_status()
            return response.json()

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def calculate_expiry(expire_in_seconds: int) -> datetime:
        """Calcula o datetime UTC de expiração a partir dos segundos retornados pela API."""
        return datetime.now(timezone.utc) + timedelta(seconds=expire_in_seconds)


# Instância singleton para uso nas rotas e worker
shopee_client = ShopeeClient()
