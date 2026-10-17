from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
import json

import cloudinary
import cloudinary.uploader
import httpx
import redis.asyncio as redis

from app.core.config import settings
from app.core.errors import APIError
from app.models.marketplace_credential import Marketplace, MarketplaceCredential, MarketplaceItem
from sqlmodel import Session, select


ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ML_API_BASE = "https://api.mercadolibre.com"
ML_SITES_URL = "https://api.mercadolibre.com/sites/MLB"


class MercadoLivreService:
    def __init__(self, session: Session):
        self.session = session
        self.client_id = settings.mercado_livre_app_id
        self.client_secret = settings.mercado_livre_client_secret
        self.redirect_uri = "https://dreamt-roundness-tightwad.ngrok-free.dev/api/v1/auth/mercadolivre/callback"
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

    def get_auth_url(self, tenant_id: str) -> str:
        """Generate the Mercado Livre OAuth authorization URL."""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": tenant_id,
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

        # Check if token is expired or about to expire (within 5 minutes)
        if credential.expires_at:
            # Ensure both datetimes are timezone-aware for comparison
            expires_at = credential.expires_at
            if expires_at.tzinfo is None:
                # Database stores naive datetime, assume UTC
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC) + timedelta(minutes=5):
                return await self._refresh_credential(credential)

        return credential

    async def _refresh_credential(self, credential: MarketplaceCredential) -> MarketplaceCredential | None:
        """Refresh expired credential."""
        if not credential.refresh_token:
            return None

        try:
            token_data = await self.refresh_access_token(credential.refresh_token)
        except Exception:
            return None

        expires_in = token_data.get("expires_in", 21600)
        credential.access_token = token_data["access_token"]
        credential.refresh_token = token_data.get("refresh_token", credential.refresh_token)
        credential.expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        credential.updated_at = datetime.now(UTC)

        self.session.add(credential)
        self.session.commit()
        self.session.refresh(credential)
        return credential

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

    async def get_category_attributes(self, access_token: str, category_id: str) -> list[dict[str, Any]]:
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
                secure_urls = await self.upload_pictures(credential.access_token, urls)
                # Mercado Libre /items endpoint expects {"source": "cloudinary_url"},
                # not {"secure_url": "ml_url"}. Keep original Cloudinary URLs.
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

        return result

    async def update_item(self, tenant_id: str, item_id: str, item_data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing item (only editable fields)."""
        credential = await self.get_valid_credential(tenant_id)
        if not credential:
            raise APIError(status_code=401, code="unauthorized", message="No valid Mercado Livre credential found")

        # Upload new pictures if provided
        cloudinary_urls = item_data.get("pictures", [])
        if cloudinary_urls:
            secure_urls = await self.upload_pictures(credential.access_token, cloudinary_urls)
            item_data["pictures"] = [{"secure_url": url} for url in secure_urls]

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
            response.raise_for_status()
            return response.json()

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
            response.raise_for_status()
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
    # Webhook Methods
    # =========================================================================

    async def subscribe_webhook(self, tenant_id: str, callback_url: str, topics: list[str]) -> dict[str, Any]:
        """Subscribe to Mercado Livre webhook notifications."""
        credential = await self.get_valid_credential(tenant_id)
        if not credential:
            raise APIError(status_code=401, code="unauthorized", message="No valid Mercado Livre credential found")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ML_API_BASE}/webhooks",
                json={
                    "callback_url": callback_url,
                    "topics": topics,
                },
                headers={
                    "Authorization": f"Bearer {credential.access_token}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            return response.json()

    async def unsubscribe_webhook(self, tenant_id: str, webhook_id: str) -> dict[str, Any]:
        """Unsubscribe from Mercado Livre webhook."""
        credential = await self.get_valid_credential(tenant_id)
        if not credential:
            raise APIError(status_code=401, code="unauthorized", message="No valid Mercado Livre credential found")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{ML_API_BASE}/webhooks/{webhook_id}",
                headers={"Authorization": f"Bearer {credential.access_token}"},
            )
            response.raise_for_status()
            return response.json()

    # =========================================================================
    # Local Database Sync Methods
    # =========================================================================

    def sync_item_to_local(self, tenant_id: str, item_data: dict[str, Any], ml_user_id: int) -> MarketplaceItem:
        """Sync Mercado Livre item to local database.

        Reads the transient keys set by create_item_v3 (`_sku_id`,
        `_product_id`, `_description`) to persist the link between the
        marketplace item and the internal catalog, removing them from the
        payload before it is stored/returned.
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
            self.session.add(existing)
            self.session.commit()
            self.session.refresh(existing)
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
        self.session.commit()
        self.session.refresh(item)
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