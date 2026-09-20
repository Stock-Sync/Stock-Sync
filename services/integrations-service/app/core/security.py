"""
Módulo de segurança do integrations-service.

Responsabilidades:
  - Criptografia/descriptografia de tokens em repouso (Fernet AES-128-CBC)
  - Verificação de assinatura HMAC-SHA256 dos webhooks da Shopee
"""

import hashlib
import hmac
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Retorna instância singleton do Fernet, inicializando na primeira chamada."""
    global _fernet
    if _fernet is None:
        key = settings.encryption_key
        if not key:
            raise RuntimeError(
                "ENCRYPTION_KEY não configurada. "
                "Gere com: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt(plaintext: str) -> str:
    """
    Criptografa um texto puro usando Fernet (AES-128-CBC + HMAC-SHA256).

    Args:
        plaintext: Texto a criptografar (ex: access_token do marketplace).

    Returns:
        String criptografada em base64 URL-safe, segura para armazenar no banco.
    """
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """
    Descriptografa um valor criptografado pelo Fernet.

    Args:
        ciphertext: Valor criptografado (lido do banco).

    Returns:
        Texto original descriptografado.

    Raises:
        InvalidToken: Se o ciphertext foi adulterado ou a chave é incorreta.
    """
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Falha ao descriptografar token — chave inválida ou dado corrompido.")
        raise


def verify_shopee_signature(body: bytes, received_signature: str) -> bool:
    """
    Valida a assinatura HMAC-SHA256 enviada pelo webhook da Shopee.

    A Shopee assina o payload usando a SHOPEE_PARTNER_KEY e envia o resultado
    no header 'Authorization'. Referência: Shopee Open Platform Webhook Docs.

    Args:
        body: Corpo bruto da requisição HTTP (bytes).
        received_signature: Valor do header 'Authorization' da requisição.

    Returns:
        True se a assinatura é válida, False caso contrário.
    """
    partner_key = settings.shopee_partner_key.encode()
    expected = hmac.new(partner_key, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received_signature)
