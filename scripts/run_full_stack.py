#!/usr/bin/env python3
"""
Full stack startup script for local development.

This script:
1. Starts docker-compose services
2. Waits for services to be healthy
3. Runs database migrations (creates tables via SQLModel)
4. Runs data migration from sync-service to catalog-service
5. Verifies integration
"""

import os
import sys
import subprocess
import time
import signal
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def run_command(cmd: list, description: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"\n🔧 {description}...")
    print(f"   $ {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
        if result.stdout:
            print(f"   stdout: {result.stdout.strip()}")
        if result.stderr:
            print(f"   stderr: {result.stderr.strip()}")
        if check and result.returncode != 0:
            print(f"   ❌ Failed with exit code {result.returncode}")
            sys.exit(result.returncode)
        print(f"   ✅ Success")
        return result
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        if check:
            sys.exit(1)
        return subprocess.CompletedProcess(cmd, -1, "", str(e))


def wait_for_service_health(url: str, name: str, max_wait: int = 120) -> bool:
    """Wait for a service to become healthy."""
    import httpx
    
    print(f"\n⏳ Waiting for {name} at {url} (max {max_wait}s)...")
    start = time.time()
    
    while time.time() - start < max_wait:
        try:
            response = httpx.get(f"{url}/health", timeout=5.0)
            if response.status_code == 200:
                print(f"✅ {name} is healthy")
                return True
        except Exception:
            pass
        
        elapsed = int(time.time() - start)
        print(f"   Waiting... ({elapsed}s)")
        time.sleep(5)
    
    print(f"❌ {name} failed to become healthy after {max_wait}s")
    return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Run full StackSync stack locally")
    parser.add_argument("--skip-migration", action="store_true", help="Skip data migration step")
    parser.add_argument("--skip-verify", action="store_true", help="Skip integration verification")
    parser.add_argument("--build", action="store_true", help="Force rebuild docker images")
    parser.add_argument("--detach", action="store_true", help="Run in background (don't wait)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("🚀 StackSync Full Stack Startup")
    print("=" * 60)
    
    # Step 1: Start docker-compose
    compose_cmd = ["docker-compose", "up"]
    if args.build:
        compose_cmd.append("--build")
    if args.detach:
        compose_cmd.append("-d")
    
    # Start services
    if args.detach:
        run_command(compose_cmd, "Starting docker-compose services (detached)", check=False)
    else:
        # Run in foreground - we'll need another approach
        print("For foreground mode, run: docker-compose up")
        print("This script works best with --detach")
        return
    
    # Step 2: Wait for core services
    print("\n⏳ Waiting for core infrastructure...")
    time.sleep(10)  # Give postgres/redis time to start
    
    # Step 3: Wait for catalog-service
    if not wait_for_service_health("http://localhost:8001", "catalog-service"):
        print("❌ catalog-service failed to start")
        sys.exit(1)
    
    # Step 4: Wait for sync-service
    if not wait_for_service_health("http://localhost:8002", "sync-service"):
        print("❌ sync-service failed to start")
        sys.exit(1)
    
    # Step 5: Wait for integrations-service
    if not wait_for_service_health("http://localhost:8003", "integrations-service"):
        print("❌ integrations-service failed to start")
        sys.exit(1)
    
    # Step 6: Tables are auto-created via SQLModel.metadata.create_all() on service startup
    print("\n✅ Tables auto-created via SQLModel on service startup")
    
    # Step 7: Run data migration (if not skipped)
    if not args.skip_migration:
        print("\n📦 Running data migration...")
        result = run_command(
            [sys.executable, "scripts/migrate_mappings.py", "--verify"],
            "Running mapping migration",
            check=False
        )
        if result.returncode != 0:
            print("⚠️  Migration had issues (check output above)")
    else:
        print("\n⏭️  Skipping data migration")
    
    # Step 8: Verify integration (if not skipped)
    if not args.skip_verify:
        print("\n🔍 Verifying integration...")
        result = run_command(
            [sys.executable, "scripts/verify_integration.py", "--wait"],
            "Verifying service integration",
            check=False
        )
        if result.returncode != 0:
            print("⚠️  Integration verification had issues")
    else:
        print("\n⏭️  Skipping integration verification")
    
    print("\n" + "=" * 60)
    print("🎉 Full stack is running!")
    print("=" * 60)
    print("\nService URLs:")
    print("  catalog-service:    http://localhost:8001 (docs: /docs)")
    print("  sync-service:       http://localhost:8002 (docs: /docs)")
    print("  integrations-service: http://localhost:8003 (docs: /docs)")
    print("  sales-service:      http://localhost:8004 (docs: /docs)")
    print("  postgres:           localhost:5433")
    print("  redis:              localhost:6379")
    print("\nTo stop: docker-compose down")
    print("To view logs: docker-compose logs -f [service-name]")


if __name__ == "__main__":
    main()