import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlparse

import cloudinary
import cloudinary.uploader
import httpx
import redis.asyncio as redis
from redis.exceptions import RedisError
from sqlalchemy import or_
from sqlmodel import Session, select

from app.core.config import settings
from app.core.errors import APIError
from app.core.redis import (
    ML_REFRESH_LOCK_KEY_PREFIX,
    acquire_refresh_lock,
    release_refresh_lock,
)
from app.models.marketplace_credential import Marketplace, MarketplaceCredential, MarketplaceItem

logger = logging.getLogger(__name__)

ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ML_API_BASE = "https://api.mercadolibre.com"
ML_SITES_URL = "https://api.mercadolibre.com/sites/MLB"

# Internal catalog-service endpoints used by the listing saga.
CATALOG_PLATFORM_MAPPINGS_PATH = "/api/v1/internal/platform-mappings"
CATALOG_PLATFORM_MAPPINGS_UNBIND_PATH = (
    "/api/v1/internal/platform-mappings/unbind"
)
CATALOG_LIST_PLATFORM_MAPPINGS_PATH = "/api/v1/platform-mappings"
CATALOG_PLATFORM_MAPPINGS_STATE_PATH = (
    "/api/v1/internal/platform-mappings/state"
)

# How often a process waiting for the refresh lock retries.
_REFRESH_LOCK_POLL_SECONDS = 0.2


def item_has_variations(item_data: dict[str, Any] | None) -> bool:
    """Return true when an ML listing payload contains child variations.

    Multi-variation listings are persisted for audit/history but must never be
    mapped to the parent SKU nor participate in stock/reconciliation loops.
    """
    if not isinstance(item_data, dict):
        return False
    return bool(item_data.get("children")) or bool(item_data.get("variations"))


class MercadoLivreService:
    def __init__(self, session: Session):
        self.session = session
        self.client_id = settings.mercado_livre_app_id
        self.client_secret = settings.mercado_livre_client_secret
        self.redirect_uri = (
            f"{settings.public_api_url.rstrip('/')}/api/v1/auth/mercadolivre/callback"
        )
        self._redis: redis.Redis | None = None
        
        # Initialize Cloudinary
        cloudinary.config(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            secure=True
        )

    @property
    def redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    def get_auth_url(self, state: str) -> str:
        """Generate the Mercado Livre OAuth authorization URL."""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
        }
        return f"{ML_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str, tenant_id: str) -> dict[str, Any]:
        """Exchange authorization code for access and refresh tokens."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                ML_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
                headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            return response.json()

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh the access token using refresh token."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                ML_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                },
                headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            return response.json()

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Get Mercado Livre user information."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ML_API_BASE}/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json()

    def save_credential(
        self,
        tenant_id: str,
        token_data: dict[str, Any],
        user_info: dict[str, Any],
        account_name: str | None = None,
    ) -> MarketplaceCredential:
        """Save or update marketplace credential."""
        expires_in = token_data.get("expires_in", 21600)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        ml_user_id = user_info.get("id")
        ml_nickname = user_info.get("nickname")

        # Check if credential already exists for this tenant and marketplace
        existing = self.session.exec(
            select(MarketplaceCredential).where(
                MarketplaceCredential.tenant_id == tenant_id,
                MarketplaceCredential.marketplace == Marketplace.mercadolivre,
            )
        ).first()

        if existing:
            existing.access_token = token_data["access_token"]
            existing.refresh_token = token_data.get("refresh_token")
            existing.expires_at = expires_at
            existing.ml_user_id = ml_user_id
            existing.ml_nickname = ml_nickname
            existing.account_name = account_name or existing.account_name
            existing.is_active = True
            existing.updated_at = datetime.now(UTC)
            self.session.add(existing)
            self.session.commit()
            self.session.refresh(existing)
            return existing

        credential = MarketplaceCredential(
            tenant_id=tenant_id,
            marketplace=Marketplace.mercadolivre,
            account_name=account_name or f"Mercado Livre {ml_user_id}",
            ml_user_id=ml_user_id,
            ml_nickname=ml_nickname,
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            expires_at=expires_at,
            is_active=True,
        )
        self.session.add(credential)
        self.session.commit()
        self.session.refresh(credential)
        return credential

    def _needs_refresh(self, credential: MarketplaceCredential) -> bool:
        """Return True when the access token is inside the refresh window."""
        if not credential.expires_at:
            return False

        expires_at = credential.expires_at
        if expires_at.tzinfo is None:
            # Database stores naive datetime, assume UTC
            expires_at = expires_at.replace(tzinfo=UTC)

        buffer = timedelta(seconds=settings.ml_refresh_buffer_seconds)
        return expires_at <= datetime.now(UTC) + buffer

    async def get_valid_credential(self, tenant_id: str) -> MarketplaceCredential | None:
        """Get valid (non-expired) credential for tenant."""
        credential = self.session.exec(
            select(MarketplaceCredential).where(
                MarketplaceCredential.tenant_id == tenant_id,
                MarketplaceCredential.marketplace == Marketplace.mercadolivre,
                MarketplaceCredential.is_active == True,
            )
        ).first()

        if not credential:
            return None

        if self._needs_refresh(credential):
            return await self._refresh_credential_with_lock(credential)

        return credential

    async def _acquire_refresh_lock(self, lock_key: str, lock_token: str) -> bool:
        """Poll ``SET NX PX`` until the lock is acquired or the timeout expires.

        If Redis is unavailable the refresh proceeds without the lock: failing
        every Mercado Livre call because of a cache outage is worse than a
        possible refresh stampede. The lock is strictly an optimization.
        """
        # A negative timeout would otherwise loop forever without a deadline.
        timeout_seconds = max(settings.ml_refresh_lock_timeout_seconds, 0)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds

        while True:
            try:
                if await acquire_refresh_lock(
                    lock_key,
                    lock_token,
                    ttl_seconds=settings.ml_refresh_lock_ttl_seconds,
                ):
                    return True
            except RedisError as exc:
                logger.warning(
                    "ml_refresh_lock_unavailable",
                    extra={"lock_key": lock_key, "error": str(exc)},
                )
                return False

            if loop.time() >= deadline:
                logger.warning(
                    "ml_refresh_lock_timeout",
                    extra={"lock_key": lock_key},
                )
                return False

            await asyncio.sleep(_REFRESH_LOCK_POLL_SECONDS)

    async def _refresh_credential_with_lock(
        self, credential: MarketplaceCredential
    ) -> MarketplaceCredential | None:
        """Refresh an expiring credential under a per-tenant distributed lock.

        Concurrency works in two phases: the lock serializes refreshes, and the
        post-acquisition re-read (double-check) means a waiter that lost the
        race returns the token the winner just persisted instead of refreshing
        again (Mercado Livre rotates refresh tokens on every use).
        """
        if not self._needs_refresh(credential):
            return credential

        lock_key = f"{ML_REFRESH_LOCK_KEY_PREFIX}{credential.tenant_id}"
        lock_token = str(uuid.uuid4())
        lock_acquired = await self._acquire_refresh_lock(lock_key, lock_token)

        try:
            # Re-fetch even when the lock was not acquired (timeout): another
            # process may have refreshed while this one was waiting.
            try:
                self.session.refresh(credential)
            except Exception:
                # The credential disappeared mid-refresh; nothing to return.
                return None

            if not self._needs_refresh(credential):
                return credential

            if not credential.refresh_token:
                return None

            try:
                token_data = await self.refresh_access_token(credential.refresh_token)
                expires_in = token_data.get("expires_in", 21600)
                credential.access_token = token_data["access_token"]
                credential.refresh_token = token_data.get(
                    "refresh_token", credential.refresh_token
                )
                credential.expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
                credential.updated_at = datetime.now(UTC)

                self.session.add(credential)
                self.session.commit()
                self.session.refresh(credential)
            except Exception:
                # Leave the previous (still persisted) tokens untouched and
                # let the next call retry.
                self.session.rollback()
                return None

            return credential
        finally:
            if lock_acquired:
                await release_refresh_lock(lock_key, lock_token)

    # =========================================================================
    # User Products v3 Methods
    # =========================================================================

    async def check_user_product_tag(self, access_token: str) -> bool:
        """Check if seller has the user_product_seller tag."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ML_API_BASE}/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            user_data = response.json()
            tags = user_data.get("tags", [])
            return "user_product_seller" in tags

    def upload_to_cloudinary(self, file_path: str) -> str:
        """Upload image to Cloudinary and return the secure URL."""
        try:
            result = cloudinary.uploader.upload(
                file_path,
                folder="mercadolivre/listings",
                resource_type="image",
                quality="auto",
                fetch_format="auto",
                width=1000,
                height=1000,
                crop="limit"
            )
            return result["secure_url"]
        except Exception as e:
            raise APIError(
                status_code=500,
                code="cloudinary_upload_failed",
                message=f"Failed to upload image to Cloudinary: {str(e)}",
            )

    async def upload_picture(self, access_token: str, cloudinary_url: str) -> str:
        """Upload picture to Mercado Livre CDN via Cloudinary URL.
        Returns the official secure_url from ML CDN.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ML_API_BASE}/pictures",
                json={"source": cloudinary_url},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()
            secure_url = data.get("secure_url")
            if not secure_url:
                # Mercado Livre returns variations with secure_url instead of top-level
                variations = data.get("variations", [])
                if variations:
                    secure_url = variations[0].get("secure_url")
            if not secure_url:
                raise APIError(
                    status_code=500,
                    code="picture_upload_failed",
                    message="Mercado Livre did not return secure_url for uploaded picture",
                    details={"ml_response": data},
                )
            return secure_url

    async def upload_pictures(self, access_token: str, cloudinary_urls: list[str]) -> list[str]:
        """Upload multiple pictures to Mercado Livre CDN."""
        secure_urls = []
        for url in cloudinary_urls:
            secure_url = await self.upload_picture(access_token, url)
            secure_urls.append(secure_url)
        return secure_urls

    async def get_site_categories(self, access_token: str) -> list[dict[str, Any]]:
        """List the site's categories (GET /sites/MLB/categories) for tree navigation."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ML_SITES_URL}/categories",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json()

    async def get_root_categories(self, access_token: str) -> list[dict[str, Any]]:
        """Alias kept for clarity: root categories of the MLB site."""
        return await self.get_site_categories(access_token)

    async def get_category(self, access_token: str, category_id: str) -> dict[str, Any]:
        """Get category details including children to validate leaf category."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ML_API_BASE}/categories/{category_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json()

    async def is_leaf_category(self, access_token: str, category_id: str) -> bool:
        """Check if a category is a leaf category (no children)."""
        category = await self.get_category(access_token, category_id)
        children = category.get("children_categories", [])
        return len(children) == 0

    async def create_item_description(self, access_token: str, item_id: str, description: str) -> dict[str, Any]:
        """Create description for an item (separate call in v3)."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ML_API_BASE}/items/{item_id}/description",
                json={"plain_text": description},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            return response.json()

    async def update_item_description(self, access_token: str, item_id: str, description: str) -> dict[str, Any]:
        """Update an item description.

        Mercado Livre exposes PUT for updates and POST for initial creation;
        fall back to POST when the item has no description yet.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                f"{ML_API_BASE}/items/{item_id}/description",
                json={"plain_text": description},
                headers=headers,
            )
            if response.status_code == 404:
                response = await client.post(
                    f"{ML_API_BASE}/items/{item_id}/description",
                    json={"plain_text": description},
                    headers=headers,
                )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                details = {"status_code": e.response.status_code}
                try:
                    details["ml_error"] = e.response.json()
                except Exception:
                    details["ml_error"] = e.response.text
                raise APIError(
                    status_code=422,
                    code="item_description_failed",
                    message="Falha ao atualizar a descrição do anúncio no Mercado Livre.",
                    details=details,
                ) from e
            return response.json()

    async def _fetch_item_description_plain_text(
        self, access_token: str, item_id: str
    ) -> str | None:
        """Fetch the full description text for an item.

        Returns ``None`` when ML returns ``404`` (no description registered).
        Raises ``APIError`` on ``5xx``/timeout so the caller can disable only
        the description field while still allowing price/stock edits.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{ML_API_BASE}/items/{item_id}/description",
                    headers=headers,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise APIError(
                    status_code=503,
                    code="item_description_timeout",
                    message="Tempo esgotado ao buscar a descrição no Mercado Livre.",
                    details={"item_id": item_id},
                ) from exc

            if response.status_code == 404:
                return None

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                details = {"status_code": e.response.status_code}
                try:
                    details["ml_error"] = e.response.json()
                except Exception:
                    details["ml_error"] = e.response.text
                raise APIError(
                    status_code=502,
                    code="item_description_failed",
                    message="Falha ao buscar a descrição do anúncio no Mercado Livre.",
                    details=details,
                ) from e

            data = response.json()
            return data.get("plain_text") or data.get("text")
        """Get category attributes from Mercado Livre with Redis caching."""
        cache_key = f"ml:category:attributes:{category_id}"
        
        # Try to get from cache
        cached = await self.redis.get(cache_key)
        if cached:
            import json
            return json.loads(cached)

        # Fetch from ML API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ML_API_BASE}/categories/{category_id}/attributes",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            data = response.json()

            # Cache for 24 hours (86400 seconds)
            import json
            await self.redis.setex(cache_key, 86400, json.dumps(data))
            
            return data

    async def create_item_v3(self, tenant_id: str, item_data: dict[str, Any]) -> dict[str, Any]:
        """Create an item using User Products v3 API."""
        credential = await self.get_valid_credential(tenant_id)
        if not credential:
            raise APIError(status_code=401, code="unauthorized", message="No valid Mercado Livre credential found")

        # Check user_product_seller tag
        has_tag = await self.check_user_product_tag(credential.access_token)
        if not has_tag:
            raise APIError(
                status_code=422,
                code="user_product_tag_missing",
                message="Your Mercado Livre account does not yet support the User Products model. Please wait for the platform to automatically enable it."
            )

        # Validate category is leaf
        category_id = item_data.get("category_id")
        if category_id:
            is_leaf = await self.is_leaf_category(credential.access_token, category_id)
            if not is_leaf:
                raise APIError(
                    status_code=422,
                    code="invalid_category",
                    message=f"Category {category_id} is not a leaf category. Please select a leaf category."
                )

        # Upload pictures to ML CDN
        cloudinary_urls = item_data.get("pictures", [])
        if cloudinary_urls:
            try:
                # Extract source URLs from picture objects [{source: "..."}]
                urls = [p.get("source", "") for p in cloudinary_urls if p.get("source")]
                # Pre-register images on ML CDN via /pictures (optional pre-warming),
                # but send the ORIGINAL Cloudinary URLs as `source` to /items.
                # Mercado Libre's /items endpoint downloads from `source`; it cannot
                # fetch from its own CDN secure_urls.
                await self.upload_pictures(credential.access_token, urls)
                item_data["pictures"] = [{"source": url} for url in urls]
            except httpx.HTTPStatusError as e:
                details = {"status_code": e.response.status_code}
                try:
                    details["ml_error"] = e.response.json()
                except Exception:
                    details["ml_error"] = e.response.text
                raise APIError(
                    status_code=422,
                    code="picture_upload_failed",
                    message="Falha ao enviar fotos para o Mercado Livre. Verifique se as imagens estão acessíveis e tente novamente.",
                    details=details,
                )

        # Remove description from item_data as it's sent separately in v3
        description = item_data.pop("description", None)

        # Local catalog links must not be forwarded to Mercado Livre
        sku_id = item_data.pop("sku_id", None)
        product_id = item_data.pop("product_id", None)
        item_data.pop("platform_sku", None)
        # Variations are rejected by the API; never leak them to ML either.
        item_data.pop("variations", None)

        # Empty variations list is invalid for the items endpoint
        if not item_data.get("children"):
            item_data.pop("children", None)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{ML_API_BASE}/items",
                json=item_data,
                headers={
                    "Authorization": f"Bearer {credential.access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                details = {"status_code": e.response.status_code}
                try:
                    details["ml_error"] = e.response.json()
                except Exception:
                    details["ml_error"] = e.response.text
                raise APIError(
                    status_code=422,
                    code="item_creation_failed",
                    message="Falha ao criar item no Mercado Livre. Verifique os dados do anúncio.",
                    details=details,
                )
            result = response.json()

        # Create description if provided
        if description and result.get("id"):
            await self.create_item_description(credential.access_token, result["id"], description)

        # Context consumed by sync_item_to_local; never sent to Mercado Livre
        result["_sku_id"] = sku_id
        result["_product_id"] = product_id
        result["_description"] = description
        # Preserve original Cloudinary URLs for local edit/recovery. Mercado Libre
        # only returns its own CDN secure_urls, which cannot be used as `source`
        # on PUT /items (ML cannot download from its own CDN).
        result["_cloudinary_urls"] = [
            p.get("source", "") for p in cloudinary_urls if p.get("source")
        ]

        return result

    # =========================================================================
    # Orchestrated listing lifecycle (Plan 7)
    # =========================================================================

    @staticmethod
    def _validate_cloudinary_pictures(
        pictures: list[dict[str, Any]] | None,
    ) -> None:
        """Reject pictures that Mercado Livre cannot download from Cloudinary.

        New listings must be published exclusively with Cloudinary URLs; the
        ML CDN URLs cannot be used as ``source`` on a create request.
        """
        for picture in pictures or []:
            if isinstance(picture, dict):
                source = picture.get("source")
            else:
                source = picture
            parsed = urlparse(str(source or ""))
            host = (parsed.hostname or "").lower()
            is_cloudinary = host == "cloudinary.com" or host.endswith(
                ".cloudinary.com"
            )
            if parsed.scheme not in {"http", "https"} or not is_cloudinary:
                raise APIError(
                    status_code=422,
                    code="invalid_picture_source",
                    message="Only Cloudinary picture URLs are supported.",
                    details={"source": source},
                )

    @staticmethod
    def _serialize_item(item: MarketplaceItem) -> dict[str, Any]:
        """Serialize a local MarketplaceItem for the API response."""
        return {
            "id": item.item_id,
            "item_id": item.item_id,
            "title": item.title,
            "price": item.price,
            "available_quantity": item.available_quantity,
            "status": item.status,
            "thumbnail": item.thumbnail,
            "permalink": item.permalink,
            "category_id": item.category_id,
            "condition": item.condition,
            "listing_type_id": item.listing_type_id,
            "family_name": item.family_name,
            "sku_id": item.sku_id,
            "product_id": item.product_id,
            "description": item.description,
            "attributes": item.attributes,
            "updated_at": (
                item.updated_at.isoformat() if item.updated_at else None
            ),
        }

    def find_existing_listing(
        self, tenant_id: str, sku_id: int
    ) -> MarketplaceItem | None:
        """Return the active local listing already published for a SKU."""
        return self.session.exec(
            select(MarketplaceItem)
            .where(
                MarketplaceItem.tenant_id == tenant_id,
                MarketplaceItem.sku_id == sku_id,
                MarketplaceItem.marketplace == "mercado_livre",
                MarketplaceItem.is_deleted.is_(False),
            )
            .order_by(MarketplaceItem.updated_at.desc())
        ).first()

    def _catalog_headers(self, tenant_id: str) -> dict[str, str]:
        return {
            "X-Internal-Secret": settings.internal_service_secret,
            "X-Tenant-ID": tenant_id,
            "Accept": "application/json",
        }

    async def _fetch_catalog_mapping(
        self, tenant_id: str, platform_product_id: str
    ) -> dict[str, Any] | None:
        """Fetch the current mapping of a listing from catalog-service."""
        url = (
            f"{settings.catalog_service_url.rstrip('/')}"
            f"{CATALOG_LIST_PLATFORM_MAPPINGS_PATH}"
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    url,
                    params={
                        "platform": "mercado_livre",
                        "platform_product_id": platform_product_id,
                    },
                    headers=self._catalog_headers(tenant_id),
                )
                response.raise_for_status()
                mappings = response.json()
                return mappings[0] if mappings else None
        except Exception as exc:
            logger.warning(
                "catalog_mapping_lookup_failed",
                extra={
                    "tenant_id": tenant_id,
                    "platform_product_id": platform_product_id,
                    "error": str(exc),
                },
            )
            return None

    async def _create_catalog_mapping(
        self,
        tenant_id: str,
        sku_id: int,
        platform_sku: str,
        platform_product_id: str,
    ) -> dict[str, Any]:
        """Create/reactivate the local PlatformMapping in catalog-service."""
        url = (
            f"{settings.catalog_service_url.rstrip('/')}"
            f"{CATALOG_PLATFORM_MAPPINGS_PATH}"
        )
        payload = {
            "sku_id": sku_id,
            "platform": "mercado_livre",
            "platform_sku": platform_sku,
            "platform_product_id": platform_product_id,
            "is_active": True,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._catalog_headers(tenant_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            details: dict[str, Any] = {
                "status_code": exc.response.status_code,
            }
            try:
                details["catalog_error"] = exc.response.json()
            except Exception:
                details["catalog_error"] = exc.response.text
            raise APIError(
                status_code=502,
                code="catalog_mapping_failed",
                message="Falha ao registrar o vínculo do anúncio no catálogo.",
                details=details,
            ) from exc
        except Exception as exc:
            raise APIError(
                status_code=502,
                code="catalog_mapping_failed",
                message="Falha ao comunicar com o catálogo interno.",
                details={"error": str(exc)},
            ) from exc

    async def unbind_catalog_mapping(
        self,
        tenant_id: str,
        platform_product_id: str,
        reason: str = "listing_deleted",
    ) -> dict[str, Any]:
        """Soft delete the local mapping of a deleted marketplace listing."""
        url = (
            f"{settings.catalog_service_url.rstrip('/')}"
            f"{CATALOG_PLATFORM_MAPPINGS_UNBIND_PATH}"
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    url,
                    json={
                        "platform_product_id": platform_product_id,
                        "reason": reason,
                    },
                    headers=self._catalog_headers(tenant_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            details: dict[str, Any] = {
                "status_code": exc.response.status_code,
            }
            try:
                details["catalog_error"] = exc.response.json()
            except Exception:
                details["catalog_error"] = exc.response.text
            raise APIError(
                status_code=502,
                code="catalog_unbind_failed",
                message="Falha ao desvincular o anúncio no catálogo.",
                details=details,
            ) from exc
        except Exception as exc:
            raise APIError(
                status_code=502,
                code="catalog_unbind_failed",
                message="Falha ao comunicar com o catálogo interno.",
                details={"error": str(exc)},
            ) from exc

    async def sync_catalog_mapping_state(
        self,
        tenant_id: str,
        item_id: str,
        is_active: bool,
        event_timestamp: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Propagate an ML lifecycle change to the catalog mapping.

        Best-effort: the item mirror was already updated authoritatively, and a
        catalog outage must not make the webhook retry forever. The catalog
        endpoint ignores stale events by comparing ``updated_at``.
        """
        url = (
            f"{settings.catalog_service_url.rstrip('/')}"
            f"{CATALOG_PLATFORM_MAPPINGS_STATE_PATH}"
        )
        payload: dict[str, Any] = {
            "platform": "mercado_livre",
            "platform_product_id": item_id,
            "is_active": is_active,
        }
        if event_timestamp is not None:
            payload["event_timestamp"] = event_timestamp.isoformat()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._catalog_headers(tenant_id),
                )
                response.raise_for_status()
                return response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "catalog_mapping_state_sync_failed",
                extra={
                    "tenant_id": tenant_id,
                    "item_id": item_id,
                    "error": str(exc),
                },
            )
            return None

    async def _compensate_created_item(
        self, tenant_id: str, item_id: str
    ) -> None:
        """Delete a partially created listing, pausing it as a fallback."""
        try:
            credential = await self.get_valid_credential(tenant_id)
        except Exception:
            credential = None
        if credential is None:
            logger.error(
                "ml_listing_compensation_missing_credential",
                extra={"tenant_id": tenant_id, "item_id": item_id},
            )
            return

        headers = {
            "Authorization": f"Bearer {credential.access_token}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.delete(
                    f"{ML_API_BASE}/items/{item_id}", headers=headers
                )
                if response.status_code == 404:
                    return
                response.raise_for_status()
                return
            except Exception as exc:
                logger.warning(
                    "ml_listing_compensation_delete_failed",
                    extra={
                        "tenant_id": tenant_id,
                        "item_id": item_id,
                        "error": str(exc),
                    },
                )

            # Never close the listing automatically: pause it instead so the
            # seller can inspect/recover it from the ML dashboard.
            try:
                response = await client.put(
                    f"{ML_API_BASE}/items/{item_id}",
                    json={"status": "paused"},
                    headers={
                        **headers,
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
            except Exception:
                logger.exception(
                    "ml_listing_compensation_pause_failed",
                    extra={"tenant_id": tenant_id, "item_id": item_id},
                )

    async def create_orchestrated_listing(
        self, tenant_id: str, item_data: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None, bool]:
        """Create a marketplace listing, its description and local links atomically.

        Returns ``(item, mapping, existing)``. When an active listing already
        exists for the SKU the remote creation is skipped and the persisted
        item/mapping are returned with ``existing=True`` (idempotent retry).

        Failures after the remote item exists trigger a compensation routine:
        DELETE the listing (or PAUSE it when DELETE fails), roll back the local
        transaction and skip the catalog mapping call.
        """
        if item_data.get("children") or item_data.get("variations"):
            raise APIError(
                status_code=422,
                code="variations_not_supported",
                message="Variations are not supported",
            )

        sku_id = item_data.get("sku_id")
        if sku_id is None:
            raise APIError(
                status_code=422,
                code="sku_required",
                message="sku_id is required to publish a listing",
            )

        existing = self.find_existing_listing(tenant_id, int(sku_id))
        if existing is not None:
            mapping = await self._fetch_catalog_mapping(
                tenant_id, existing.item_id
            )
            return self._serialize_item(existing), mapping, True

        self._validate_cloudinary_pictures(item_data.get("pictures"))

        credential = await self.get_valid_credential(tenant_id)
        if not credential:
            raise APIError(
                status_code=401,
                code="unauthorized",
                message="No valid Mercado Livre credential found",
            )

        description = item_data.get("description")
        platform_sku = item_data.get("platform_sku") or str(sku_id)
        remote_payload = dict(item_data)
        remote_payload.pop("description", None)
        remote_payload.pop("platform_sku", None)

        step = "marketplace_creation"
        item_id: str | None = None
        mapping: dict[str, Any] | None = None

        try:
            item_result = await self.create_item_v3(tenant_id, remote_payload)
            item_id = item_result.get("id")
            if not item_id:
                raise APIError(
                    status_code=500,
                    code="item_creation_failed",
                    message="Mercado Livre did not return an item id",
                )

            step = "description"
            if description and str(description).strip():
                await self.create_item_description(
                    credential.access_token, item_id, str(description)
                )

            # Context consumed by sync_item_to_local.
            item_result["_description"] = description

            step = "local_persistence"
            item = self.sync_item_to_local(
                tenant_id,
                item_result,
                credential.ml_user_id,
                commit=False,
            )

            step = "catalog_mapping"
            mapping = await self._create_catalog_mapping(
                tenant_id,
                int(sku_id),
                str(platform_sku),
                item_id,
            )

            step = "commit"
            self.session.commit()
            try:
                self.session.refresh(item)
            except Exception:
                # The item fields already came from the ML response; a refresh
                # failure must not undo a successfully committed creation.
                logger.warning(
                    "listing_local_refresh_failed",
                    extra={"tenant_id": tenant_id, "item_id": item_id},
                )

            return self._serialize_item(item), mapping, False
        except Exception as exc:
            if item_id:
                await self._compensate_created_item(tenant_id, item_id)
            if mapping is not None:
                # The remote mapping was already created: best-effort unbind
                # so compensation cannot leave it dangling.
                try:
                    await self.unbind_catalog_mapping(tenant_id, item_id)
                except Exception:
                    logger.exception(
                        "listing_compensation_unbind_failed",
                        extra={"tenant_id": tenant_id, "item_id": item_id},
                    )
            self.session.rollback()

            if (
                step == "marketplace_creation"
                and item_id is None
                and isinstance(exc, APIError)
            ):
                # Nothing was created remotely: preserve the validation/API
                # error (e.g. invalid category or ML 422) for the client.
                raise

            raise APIError(
                status_code=500,
                code="listing_creation_failed",
                message=(
                    "Falha ao publicar o anúncio; a criação foi compensada."
                ),
                details={
                    "step": step,
                    "item_id": item_id,
                    "error": str(exc),
                },
            ) from exc

    async def update_item(self, tenant_id: str, item_id: str, item_data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing item (only editable fields)."""
        if item_data.get("children") or item_data.get("variations"):
            raise APIError(
                status_code=422,
                code="variations_not_supported",
                message="Variations are not supported",
            )

        credential = await self.get_valid_credential(tenant_id)
        if not credential:
            raise APIError(status_code=401, code="unauthorized", message="No valid Mercado Livre credential found")

        # Description is not an editable field of /items; it is updated through
        # the dedicated /items/{id}/description endpoint below.
        description = item_data.pop("description", None)

        # Immutable or managed fields that must never reach PUT /items.
        # User Products v3 rejects them (e.g. title/family_name, category_id),
        # and local ERP metadata is not recognized by Mercado Livre.
        forbidden_update_fields = [
            "title",
            "family_name",
            "category_id",
            "buying_mode",
            "currency_id",
            "listing_type_id",
            "condition",
            "sku_id",
            "product_id",
            "platform_sku",
            "description",
            "variations",
            "_sku_id",
            "_product_id",
            "_description",
            "_cloudinary_urls",
        ]
        for field in forbidden_update_fields:
            item_data.pop(field, None)

        # Plan 12: NEVER send `pictures` in PUT /items edits. Photos are managed
        # exclusively via Mercado Livre dashboard (or Cloudinary for new listings).
        # Omitting the array prevents corrupting ML CDN URLs with 422 errors.
        item_data.pop("pictures", None)

        # Remove empty attributes: Mercado Livre rejects null/blank values
        # (e.g. a numeric attribute left untouched in the form).
        attributes = item_data.get("attributes")
        if isinstance(attributes, list):
            sanitized_attributes: list[dict[str, Any]] = []
            for attribute in attributes:
                if not isinstance(attribute, dict):
                    continue
                value_name = attribute.get("value_name")
                if value_name is not None:
                    value_name = str(value_name).strip()
                    if value_name:
                        attribute["value_name"] = value_name
                    else:
                        attribute.pop("value_name", None)
                value_id = attribute.get("value_id")
                if value_id is not None:
                    value_id = str(value_id).strip()
                    if value_id:
                        attribute["value_id"] = value_id
                    else:
                        attribute.pop("value_id", None)
                if attribute.get("value_name") or attribute.get("value_id"):
                    sanitized_attributes.append(attribute)
            item_data["attributes"] = sanitized_attributes

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.put(
                f"{ML_API_BASE}/items/{item_id}",
                json=item_data,
                headers={
                    "Authorization": f"Bearer {credential.access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                details = {"status_code": e.response.status_code}
                try:
                    details["ml_error"] = e.response.json()
                except Exception:
                    details["ml_error"] = e.response.text
                raise APIError(
                    status_code=422,
                    code="item_update_failed",
                    message="Falha ao atualizar o anúncio no Mercado Livre. Verifique os dados informados.",
                    details=details,
                ) from e

        if description and str(description).strip():
            await self.update_item_description(
                credential.access_token, item_id, str(description)
            )

        return response.json()

    async def prepare_item_unlink(self, tenant_id: str, item_id: str) -> dict[str, Any]:
        """Pause and zero an item before its local mapping is soft-deleted.

        Plan 9 orchestrated unbind:
        - ``active``: pause the listing and set ``available_quantity = 0``;
        - ``paused``: only guarantee ``available_quantity = 0``;
        - ``closed``/``404``: nothing to do;
        - any remote/network failure aborts with ``503`` so the caller keeps
          the mapping (local state is never changed on partial failure).
        """
        try:
            item = await self.get_item(tenant_id, item_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {
                    "item_id": item_id,
                    "status": "closed",
                    "remote_action": "skipped",
                    "reason": "not_found",
                }
            raise APIError(
                status_code=503,
                code="remote_unlink_failed",
                message="Falha ao consultar o anuncio no Mercado Livre.",
                details={"item_id": item_id, "error": str(exc)},
            ) from exc
        except Exception as exc:  # noqa: BLE001 - timeout/network raises many types
            raise APIError(
                status_code=503,
                code="remote_unlink_failed",
                message="Falha ao consultar o anuncio no Mercado Livre.",
                details={"item_id": item_id, "error": str(exc)},
            ) from exc

        status = item.get("status")
        if status == "closed":
            return {
                "item_id": item_id,
                "status": "closed",
                "remote_action": "skipped",
                "reason": "already_closed",
            }
        if status not in {"active", "paused"}:
            # under_review, not_yet_active, ...: never guess; leave untouched.
            return {
                "item_id": item_id,
                "status": status,
                "remote_action": "skipped",
                "reason": "unsupported_status",
            }

        payload: dict[str, Any] = {"available_quantity": 0}
        if status == "active":
            payload["status"] = "paused"

        try:
            result = await self.update_item(tenant_id, item_id, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ml_prepare_unlink_failed",
                extra={"tenant_id": tenant_id, "item_id": item_id, "error": str(exc)},
            )
            raise APIError(
                status_code=503,
                code="remote_unlink_failed",
                message="Nao foi possivel pausar/zerar o anuncio no Mercado Livre.",
                details={"item_id": item_id, "error": str(exc)},
            ) from exc

        return {
            "item_id": item_id,
            "status": result.get("status", "paused" if status == "active" else status),
            "available_quantity": result.get("available_quantity", 0),
            "remote_action": "paused_and_zeroed"
            if status == "active"
            else "zeroed",
        }

    async def update_seller_custom_field(
        self, tenant_id: str, item_id: str, seller_custom_field: str
    ) -> dict[str, Any]:
        """Best-effort update of the ML seller SKU (``seller_custom_field``)."""
        return await self.update_item(
            tenant_id, item_id, {"seller_custom_field": seller_custom_field}
        )

    async def delete_item(self, tenant_id: str, item_id: str) -> dict[str, Any]:
        """Delete/pause an item."""
        credential = await self.get_valid_credential(tenant_id)
        if not credential:
            raise APIError(status_code=401, code="unauthorized", message="No valid Mercado Livre credential found")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{ML_API_BASE}/items/{item_id}",
                headers={
                    "Authorization": f"Bearer {credential.access_token}",
                    "Accept": "application/json",
                },
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Already deleted on Mercado Livre: the operation is idempotent.
                if exc.response.status_code == 404:
                    return {
                        "id": item_id,
                        "status": "closed",
                        "already_deleted": True,
                    }
                raise
            return response.json()

    async def list_items(
        self,
        tenant_id: str,
        page: int = 1,
        limit: int = 10,
        search: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """List items with pagination (converts page/limit to offset/limit)."""
        credential = await self.get_valid_credential(tenant_id)
        if not credential:
            raise APIError(status_code=401, code="unauthorized", message="No valid Mercado Livre credential found")

        offset = (page - 1) * limit
        params = {"offset": offset, "limit": limit}
        if search:
            params["q"] = search
        if status:
            params["status"] = status

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ML_API_BASE}/users/{credential.ml_user_id}/items/search",
                params=params,
                headers={"Authorization": f"Bearer {credential.access_token}"},
            )
            response.raise_for_status()
            data = response.json()
            
            # Transform ML response to our format
            results = data.get("results", [])
            total = data.get("paging", {}).get("total", 0)
            
            return {
                "items": results,
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": (total + limit - 1) // limit,
            }

    async def get_item(self, tenant_id: str, item_id: str) -> dict[str, Any]:
        """Get single item details."""
        credential = await self.get_valid_credential(tenant_id)
        if not credential:
            raise APIError(status_code=401, code="unauthorized", message="No valid Mercado Livre credential found")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ML_API_BASE}/items/{item_id}",
                headers={"Authorization": f"Bearer {credential.access_token}"},
            )
            response.raise_for_status()
            return response.json()

    async def get_order(self, tenant_id: str, order_id: str) -> dict[str, Any]:
        """Get full order details (GET /orders/{id})."""
        credential = await self.get_valid_credential(tenant_id)
        if not credential:
            raise APIError(status_code=401, code="unauthorized", message="No valid Mercado Livre credential found")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ML_API_BASE}/orders/{order_id}",
                headers={
                    "Authorization": f"Bearer {credential.access_token}",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            return response.json()

    async def search_all_items(
        self, tenant_id: str, page_size: int = 50, max_pages: int | None = None
    ) -> list[str]:
        """Return ALL item ids of the connected seller using scroll search."""
        result = await self.search_all_items_with_metadata(
            tenant_id, page_size=page_size, max_pages=max_pages
        )
        return result["item_ids"]

    async def search_all_items_with_metadata(
        self, tenant_id: str, page_size: int = 50, max_pages: int | None = None
    ) -> dict[str, Any]:
        """Return ALL item ids plus pagination completeness metadata.

        Offset pagination on ``/users/{id}/items/search`` is capped at 1,000
        items. Sellers above that limit are only fully enumerated with
        ``search_type=scan`` (scroll pagination), so this method always uses
        the scroll mode.

        The result is a dict with ``item_ids``, ``reported_total`` and
        ``truncated``. ``truncated`` is true when the marketplace reported more
        items than were actually fetched (e.g. the scroll ended early), which
        the caller must treat as a failed pull and never reconcile against.
        """
        credential = await self.get_valid_credential(tenant_id)
        if not credential:
            raise APIError(
                status_code=401,
                code="unauthorized",
                message="No valid Mercado Livre credential found",
            )

        item_ids: list[str] = []
        seen: set[str] = set()
        scroll_id: str | None = None
        reported_total: int | None = None
        pages = 0
        no_progress_pages = 0
        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                params: dict[str, Any] = {
                    "search_type": "scan",
                    "limit": page_size,
                }
                if scroll_id:
                    params["scroll_id"] = scroll_id
                response = await client.get(
                    f"{ML_API_BASE}/users/{credential.ml_user_id}/items/search",
                    params=params,
                    headers={"Authorization": f"Bearer {credential.access_token}"},
                )
                response.raise_for_status()
                data = response.json()
                results = data.get("results") or []
                paging = data.get("paging") or {}
                if reported_total is None and paging.get("total") is not None:
                    reported_total = int(paging["total"])

                before = len(item_ids)
                for item_id in results:
                    if item_id not in seen:
                        seen.add(item_id)
                        item_ids.append(item_id)

                pages += 1
                if max_pages is not None and pages >= max_pages:
                    break
                if not results:
                    break
                if reported_total is not None and len(item_ids) >= reported_total:
                    break

                next_scroll_id = data.get("scroll_id")
                if not next_scroll_id:
                    # Without a scroll id the API fell back to a single page;
                    # stop instead of looping over the same offset forever.
                    break

                # Defensive guard: a broken scroll that keeps returning the
                # same page must end the search as truncated instead of
                # looping forever.
                if len(item_ids) == before:
                    no_progress_pages += 1
                    if no_progress_pages >= 2:
                        break
                else:
                    no_progress_pages = 0

                scroll_id = next_scroll_id
                # Small pause to stay friendly to ML's rate limit (~25 req / 2s)
                await asyncio.sleep(0.25)

        truncated = reported_total is not None and len(item_ids) < reported_total
        if truncated:
            logger.warning(
                "ml_items_search_truncated",
                extra={
                    "tenant_id": tenant_id,
                    "fetched": len(item_ids),
                    "reported_total": reported_total,
                    "pages": pages,
                },
            )
        return {
            "item_ids": item_ids,
            "reported_total": reported_total,
            "truncated": truncated,
        }

    def _local_active_items_statement(
        self,
        tenant_id: str,
        synced_before: datetime | None = None,
    ):
        """Base query for the local active mirror, optionally time-bounded."""
        statement = select(MarketplaceItem).where(
            MarketplaceItem.tenant_id == tenant_id,
            MarketplaceItem.is_deleted.is_(False),
        )
        if synced_before is not None:
            # The column is timezone-naive; normalize the aware timestamp sent
            # by sync-service so the comparison is deterministic.
            if synced_before.tzinfo is not None:
                synced_before = synced_before.astimezone(UTC).replace(tzinfo=None)
            statement = statement.where(
                or_(
                    MarketplaceItem.last_synced_at.is_(None),
                    MarketplaceItem.last_synced_at < synced_before,
                )
            )
        return statement

    def list_local_active_items(
        self,
        tenant_id: str,
        synced_before: datetime | None = None,
    ) -> tuple[list[str], list[str]]:
        """Return ``(active_item_ids, variation_item_ids)`` for the mirror.

        Variation listings are returned separately because Plan 8 excludes them
        from both sides of the reconciliation diff: they are persisted for
        audit but managed exclusively in Mercado Livre's Application Manager.
        """
        items = list(
            self.session.exec(
                self._local_active_items_statement(tenant_id, synced_before)
            ).all()
        )
        active: list[str] = []
        variations: list[str] = []
        for item in items:
            if item_has_variations(item.raw_payload):
                variations.append(item.item_id)
            else:
                active.append(item.item_id)
        return active, variations

    def soft_delete_items(
        self,
        tenant_id: str,
        item_ids: list[str],
    ) -> list[str]:
        """Soft delete an explicit set of local listings.

        This is the second step of the inverted reconciliation (after the
        catalog mappings were unbound). It is idempotent: already-deleted ids
        are ignored. Variation listings are never deleted by reconciliation.
        """
        unique_ids = list(dict.fromkeys(item_ids))
        if not unique_ids:
            return []

        statement = select(MarketplaceItem).where(
            MarketplaceItem.tenant_id == tenant_id,
            MarketplaceItem.item_id.in_(unique_ids),
            MarketplaceItem.is_deleted.is_(False),
        )
        items = [
            item
            for item in self.session.exec(statement).all()
            if not item_has_variations(item.raw_payload)
        ]
        now = datetime.now(UTC)
        for item in items:
            item.is_deleted = True
            item.updated_at = now
            self.session.add(item)
        if items:
            self.session.commit()
        return [item.item_id for item in items]

    def soft_delete_missing_items(
        self,
        tenant_id: str,
        seen_item_ids: list[str],
        synced_before: datetime | None = None,
    ) -> list[str]:
        """Soft delete local items that are no longer listed in Mercado Livre.

        Legacy query-based path kept for backwards compatibility. New callers
        use the inverted flow (catalog unbind first, then ``soft_delete_items``
        with the explicit missing ids). Variation listings are never removed.
        """
        statement = self._local_active_items_statement(tenant_id, synced_before)
        if seen_item_ids:
            statement = statement.where(
                MarketplaceItem.item_id.notin_(seen_item_ids)
            )

        items = [
            item
            for item in self.session.exec(statement).all()
            if not item_has_variations(item.raw_payload)
        ]
        now = datetime.now(UTC)
        for item in items:
            item.is_deleted = True
            item.updated_at = now
            self.session.add(item)
        if items:
            self.session.commit()
        return [item.item_id for item in items]

    async def get_item_description(self, tenant_id: str, item_id: str) -> dict[str, Any]:
        """Get item description."""
        credential = await self.get_valid_credential(tenant_id)
        if not credential:
            raise APIError(status_code=401, code="unauthorized", message="No valid Mercado Livre credential found")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ML_API_BASE}/items/{item_id}/description",
                headers={"Authorization": f"Bearer {credential.access_token}"},
            )
            response.raise_for_status()
            return response.json()

    # =========================================================================
    # Local Database Sync Methods
    # =========================================================================

    def sync_item_to_local(
        self,
        tenant_id: str,
        item_data: dict[str, Any],
        ml_user_id: int,
        *,
        commit: bool = True,
    ) -> MarketplaceItem:
        """Sync Mercado Livre item to local database.

        Reads the transient keys set by create_item_v3 (`_sku_id`,
        `_product_id`, `_description`) to persist the link between the
        marketplace item and the internal catalog, removing them from the
        payload before it is stored/returned.

        ``commit=False`` flushes the row into the caller's transaction instead
        of committing it. The orchestrated creation uses this to keep the
        MarketplaceItem pending until the catalog mapping also succeeds, so a
        failure can be rolled back without persisting an orphan listing.
        """
        sku_id = item_data.pop("_sku_id", None)
        product_id = item_data.pop("_product_id", None)
        description = item_data.pop("_description", None)

        # Extract main item data
        item_id = item_data.get("id")
        user_product_id = item_data.get("user_product_id")
        title = item_data.get("title")
        price = item_data.get("price")
        available_quantity = item_data.get("available_quantity", 0)
        status = item_data.get("status")
        is_active = status == "active"
        category_id = item_data.get("category_id")
        condition = item_data.get("condition")
        pictures = item_data.get("pictures", [])
        thumbnail = pictures[0].get("secure_url") if pictures else None
        permalink = item_data.get("permalink")
        family_name = item_data.get("family_name")
        listing_type_id = item_data.get("listing_type_id")
        attributes = item_data.get("attributes", [])
        children = item_data.get("children", [])

        # Upsert to local database
        existing = self.session.exec(
            select(MarketplaceItem).where(
                MarketplaceItem.tenant_id == tenant_id,
                MarketplaceItem.item_id == item_id,
            )
        ).first()

        if existing:
            existing.title = title
            existing.price = price
            existing.available_quantity = available_quantity
            existing.status = status
            existing.is_active = is_active
            existing.thumbnail = thumbnail
            existing.permalink = permalink
            existing.family_name = family_name
            existing.listing_type_id = listing_type_id
            existing.category_id = category_id
            existing.condition = condition
            existing.attributes = attributes
            if sku_id is not None:
                existing.sku_id = sku_id
            if product_id is not None:
                existing.product_id = product_id
            if description is not None:
                existing.description = description
            existing.raw_payload = item_data
            existing.last_synced_at = datetime.now(UTC)
            existing.updated_at = datetime.now(UTC)
            # The item exists again in Mercado Livre (or was incorrectly
            # reconciled): resurrect it instead of keeping a stale tombstone.
            existing.is_deleted = False
            self.session.add(existing)
            if commit:
                self.session.commit()
                self.session.refresh(existing)
            else:
                self.session.flush()
            return existing

        item = MarketplaceItem(
            item_id=item_id,
            user_product_id=user_product_id,
            tenant_id=tenant_id,
            ml_user_id=ml_user_id,
            marketplace="mercado_livre",
            title=title,
            price=price,
            available_quantity=available_quantity,
            status=status,
            is_active=is_active,
            thumbnail=thumbnail,
            permalink=permalink,
            family_name=family_name,
            listing_type_id=listing_type_id,
            category_id=category_id,
            condition=condition,
            sku_id=sku_id,
            product_id=product_id,
            description=description,
            attributes=attributes,
            raw_payload=item_data,
            last_synced_at=datetime.now(UTC),
        )
        self.session.add(item)
        if commit:
            self.session.commit()
            self.session.refresh(item)
        else:
            self.session.flush()
        return item

    def handle_webhook_item(self, tenant_id: str, item_data: dict[str, Any]) -> MarketplaceItem | None:
        """Process item webhook notification and sync to local DB."""
        ml_user_id = item_data.get("seller_id")
        if not ml_user_id:
            return None

        # Find credential by ml_user_id
        credential = self.session.exec(
            select(MarketplaceCredential).where(
                MarketplaceCredential.ml_user_id == ml_user_id,
                MarketplaceCredential.marketplace == Marketplace.mercadolivre,
            )
        ).first()

        if not credential:
            return None

        return self.sync_item_to_local(credential.tenant_id, item_data, ml_user_id)