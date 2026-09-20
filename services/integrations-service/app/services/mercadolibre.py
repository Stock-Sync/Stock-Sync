"""
SDK client para a API do Mercado Livre.

Encapsula todas as chamadas HTTP para o ML — OAuth, user info e atualização de estoque.
Usa httpx.Client síncrono (alinhado ao stack sync do serviço).
"""

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# TTL padrão do access_token do ML: 6 horas
ML_ACCESS_TOKEN_TTL_HOURS = 6


class MercadoLibreClient:
    """Cliente para a API do Mercado Livre."""

    def __init__(self) -> None:
        self.base_url = settings.ml_api_base_url
        self.app_id = settings.ml_app_id
        self.client_secret = settings.ml_client_secret
        self.redirect_uri = settings.ml_redirect_uri

    # ── OAuth ─────────────────────────────────────────────────────────────

    def get_auth_url(self, user_id: str) -> str:
        """
        Monta a URL de autorização OAuth do Mercado Livre.

        O `state` é o user_id interno do SaaS, devolvido no callback
        para associar o código ao tenant correto.
        """
        params = {
            "response_type": "code",
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "state": user_id,
        }
        return f"https://auth.mercadolibre.com.br/authorization?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict:
        """
        Troca o authorization code por access_token e refresh_token.

        Returns:
            Dict com access_token, refresh_token, expires_in, user_id (seller_id ML).
        """
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.app_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        with httpx.Client(base_url=self.base_url, timeout=15.0) as client:
            response = client.post("/oauth/token", data=payload)
            response.raise_for_status()
            return response.json()

    def refresh_token(self, refresh_token: str) -> dict:
        """
        Renova o access_token usando o refresh_token.

        Returns:
            Dict com novos access_token, refresh_token e expires_in.
        """
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.app_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }
        with httpx.Client(base_url=self.base_url, timeout=15.0) as client:
            response = client.post("/oauth/token", data=payload)
            response.raise_for_status()
            return response.json()

    def get_user_info(self, access_token: str) -> dict:
        """
        Retorna informações do vendedor autenticado (inclui o seller_id do ML).

        Returns:
            Dict com id, nickname, email, etc.
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
            response = client.get("/users/me", headers=headers)
            response.raise_for_status()
            return response.json()

    # ── Estoque ───────────────────────────────────────────────────────────

    def update_stock(
        self, item_id: str, quantity: int, access_token: str
    ) -> dict:
        """
        Atualiza a quantidade em estoque de um anúncio no ML.

        Args:
            item_id: ID do anúncio no ML (ex: 'MLB123456789').
            quantity: Nova quantidade em estoque.
            access_token: Token de acesso do vendedor.

        Returns:
            Resposta da API do ML.
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {"available_quantity": quantity}
        with httpx.Client(base_url=self.base_url, timeout=15.0) as client:
            response = client.put(
                f"/items/{item_id}", json=payload, headers=headers
            )
            response.raise_for_status()
            return response.json()

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def calculate_expiry(expires_in_seconds: int) -> datetime:
        """Calcula o datetime UTC de expiração a partir dos segundos retornados pela API."""
        return datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)


# Instância singleton para uso nas rotas e worker
ml_client = MercadoLibreClient()
