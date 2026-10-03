#!/usr/bin/env python3
"""
Data migration script: Move catalog mappings from sync-service to catalog-service.

This script reads mappings from the sync-service database (stocksync_sync)
and inserts them into the catalog-service database (stocksync_catalog).

Run this AFTER both services have created their tables via SQLModel.metadata.create_all().
"""

import os
import sys
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Sync-service database URL
SYNC_DB_URL = os.environ.get(
    "SYNC_DB_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/stocksync_sync"
)

# Catalog-service database URL
CATALOG_DB_URL = os.environ.get(
    "CATALOG_DB_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/stocksync_catalog"
)


def get_sync_engine():
    """Get engine for sync-service database."""
    return create_engine(SYNC_DB_URL, echo=False)


def get_catalog_engine():
    """Get engine for catalog-service database."""
    return create_engine(CATALOG_DB_URL, echo=False)


def migrate_mappings(dry_run: bool = False) -> dict:
    """
    Migrate catalog_mapping table from sync-service to catalog-service.
    
    Args:
        dry_run: If True, only report what would be migrated without making changes.
        
    Returns:
        Dictionary with migration statistics.
    """
    stats = {
        "total_found": 0,
        "migrated": 0,
        "skipped": 0,
        "errors": 0,
        "details": []
    }
    
    sync_engine = get_sync_engine()
    catalog_engine = get_catalog_engine()
    
    with Session(sync_engine) as sync_db:
        # Check if catalog_mapping table exists in sync-service
        result = sync_db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'catalog_mapping'
            )
        """))
        table_exists = result.scalar()
        
        if not table_exists:
            print("ℹ️  No catalog_mapping table found in sync-service database. Nothing to migrate.")
            return stats
        
        # Read all mappings from sync-service
        mappings = sync_db.execute(text("""
            SELECT id, user_id, platform, external_item_id, external_model_id, 
                   product_id, sku, is_active, created_at, updated_at
            FROM catalog_mapping
        """)).fetchall()
        
        stats["total_found"] = len(mappings)
        print(f"📋 Found {len(mappings)} mappings in sync-service database")
        
        if len(mappings) == 0:
            return stats
        
        with Session(catalog_engine) as catalog_db:
            for row in mappings:
                try:
                    mapping_id, user_id, platform, external_item_id, external_model_id, \
                    product_id, sku, is_active, created_at, updated_at = row
                    
                    # Check if mapping already exists in catalog-service
                    existing = catalog_db.execute(text("""
                        SELECT id FROM catalog_mapping
                        WHERE user_id = :user_id
                          AND platform = :platform
                          AND external_item_id = :external_item_id
                          AND external_model_id = :external_model_id
                    """), {
                        "user_id": str(user_id),
                        "platform": platform,
                        "external_item_id": external_item_id,
                        "external_model_id": external_model_id or 0,
                    }).first()
                    
                    if existing:
                        stats["skipped"] += 1
                        stats["details"].append(f"Skipped (exists): {platform}/{external_item_id}")
                        continue
                    
                    # Verify product exists in catalog-service, or create a placeholder
                    product_exists = catalog_db.execute(text("""
                        SELECT id FROM product WHERE id = :product_id
                    """), {"product_id": product_id}).first()
                    
                    if not product_exists:
                        # Need to create a placeholder product or skip
                        print(f"⚠️  Product {product_id} not found in catalog-service for mapping {mapping_id}")
                        print(f"   SKU: {sku}, Platform: {platform}, Item: {external_item_id}")
                        # Try to find product by SKU and user_id
                        product_by_sku = catalog_db.execute(text("""
                            SELECT id FROM product WHERE sku = :sku AND user_id = :user_id
                        """), {"sku": sku, "user_id": str(user_id)}).first()
                        
                        if product_by_sku:
                            product_id = product_by_sku[0]
                            print(f"   ✅ Found product by SKU: {product_id}")
                        else:
                            print(f"   ❌ No matching product found. Creating placeholder...")
                            # Create placeholder product
                            result = catalog_db.execute(text("""
                                INSERT INTO product (user_id, name, sku, price, stock_quantity, created_at, updated_at)
                                VALUES (:user_id, :name, :sku, :price, :stock_quantity, :created_at, :updated_at)
                                RETURNING id
                            """), {
                                "user_id": str(user_id),
                                "name": f"Migrated Product {sku}",
                                "sku": sku,
                                "price": 0.0,
                                "stock_quantity": 0,
                                "created_at": datetime.utcnow(),
                                "updated_at": datetime.utcnow(),
                            })
                            product_id = result.fetchone()[0]
                            print(f"   ✅ Created placeholder product: {product_id}")
                    
                    # Insert mapping into catalog-service
                    if not dry_run:
                        catalog_db.execute(text("""
                            INSERT INTO catalog_mapping 
                            (user_id, platform, external_item_id, external_model_id, product_id, sku, is_active, created_at, updated_at)
                            VALUES (:user_id, :platform, :external_item_id, :external_model_id, :product_id, :sku, :is_active, :created_at, :updated_at)
                        """), {
                            "user_id": str(user_id),
                            "platform": platform,
                            "external_item_id": external_item_id,
                            "external_model_id": external_model_id or 0,
                            "product_id": product_id,
                            "sku": sku,
                            "is_active": is_active,
                            "created_at": created_at or datetime.utcnow(),
                            "updated_at": updated_at or datetime.utcnow(),
                        })
                        catalog_db.commit()
                    
                    stats["migrated"] += 1
                    stats["details"].append(f"Migrated: {platform}/{external_item_id} → {sku}")
                    print(f"✅ Migrated: {platform}/{external_item_id} → {sku}")
                    
                except Exception as e:
                    stats["errors"] += 1
                    stats["details"].append(f"Error for {mapping_id}: {str(e)}")
                    print(f"❌ Error migrating mapping {mapping_id}: {e}")
                    if not dry_run:
                        catalog_db.rollback()
    
    return stats


def verify_migration() -> dict:
    """Verify that migration was successful by comparing counts."""
    sync_engine = get_sync_engine()
    catalog_engine = get_catalog_engine()
    
    with Session(sync_engine) as sync_db:
        sync_count = sync_db.execute(text("SELECT COUNT(*) FROM catalog_mapping")).scalar()
    
    with Session(catalog_engine) as catalog_db:
        catalog_count = catalog_db.execute(text("SELECT COUNT(*) FROM catalog_mapping")).scalar()
    
    return {
        "sync_service_count": sync_count,
        "catalog_service_count": catalog_count,
        "match": sync_count == catalog_count
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate mappings from sync-service to catalog-service")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without making changes")
    parser.add_argument("--verify", action="store_true", help="Verify migration after running")
    args = parser.parse_args()
    
    print("=" * 60)
    print("📦 Catalog Mapping Migration: sync-service → catalog-service")
    print("=" * 60)
    print(f"Sync DB: {SYNC_DB_URL}")
    print(f"Catalog DB: {CATALOG_DB_URL}")
    print()
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print()
    
    stats = migrate_mappings(dry_run=args.dry_run)
    
    print()
    print("=" * 60)
    print("📊 Migration Summary")
    print("=" * 60)
    print(f"Total found in sync-service: {stats['total_found']}")
    print(f"Successfully migrated:       {stats['migrated']}")
    print(f"Skipped (already exists):    {stats['skipped']}")
    print(f"Errors:                      {stats['errors']}")
    
    if args.verify or not args.dry_run:
        print()
        print("🔍 Verifying migration...")
        verification = verify_migration()
        print(f"Sync-service mappings:      {verification['sync_service_count']}")
        print(f"Catalog-service mappings:   {verification['catalog_service_count']}")
        print(f"Counts match:               {'✅ YES' if verification['match'] else '❌ NO'}")
    
    if stats['errors'] > 0:
        print()
        print("⚠️  Some errors occurred. Check details above.")
        sys.exit(1)
    
    print()
    print("✅ Migration completed successfully!")


if __name__ == "__main__":
    main()