#!/usr/bin/env python3
"""
Migration script to upload local knowledge_base folder structure to Azure Blob Storage.

This is a ONE-TIME USE script to migrate existing files to Azure Blob Storage.
After successful migration, you can delete this script.

Usage:
    1. Set AZURE_STORAGE_CONNECTION_STRING in .env
    2. Run: python migrate_to_azure_blob.py
    3. Verify files in Azure Portal
    4. Delete this script

Requirements:
    pip install azure-storage-blob python-dotenv
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

try:
    from azure.storage.blob import BlobServiceClient
    from azure.core.exceptions import ResourceExistsError
except ImportError:
    print("Error: azure-storage-blob not installed")
    print("Run: pip install azure-storage-blob")
    sys.exit(1)

# Load environment variables
load_dotenv()

# Configuration
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "knowledge-base")
LOCAL_KB_DIR = Path("./knowledge_base")


def migrate():
    """Migrate local knowledge_base to Azure Blob Storage."""

    # Validate configuration
    if not AZURE_STORAGE_CONNECTION_STRING:
        print("❌ Error: AZURE_STORAGE_CONNECTION_STRING not set in .env")
        print("\nTo set it up:")
        print("1. Go to Azure Portal > Storage Account > Access Keys")
        print("2. Copy the Connection String")
        print("3. Add to .env: AZURE_STORAGE_CONNECTION_STRING=<your-connection-string>")
        sys.exit(1)

    if not LOCAL_KB_DIR.exists():
        print(f"❌ Error: Local directory '{LOCAL_KB_DIR}' not found")
        sys.exit(1)

    # Initialize Azure Blob client
    print("🔌 Connecting to Azure Blob Storage...")
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)

        # Create container if it doesn't exist
        try:
            container_client.create_container()
            print(f"✅ Created container: {AZURE_STORAGE_CONTAINER_NAME}")
        except ResourceExistsError:
            print(f"✅ Using existing container: {AZURE_STORAGE_CONTAINER_NAME}")

    except Exception as e:
        print(f"❌ Failed to connect to Azure Blob Storage: {e}")
        sys.exit(1)

    # Discover series folders
    series_folders = [
        d for d in LOCAL_KB_DIR.iterdir()
        if d.is_dir() and not d.name.startswith('.')
    ]

    if not series_folders:
        print(f"❌ No series folders found in '{LOCAL_KB_DIR}'")
        sys.exit(1)

    print(f"\n📁 Found {len(series_folders)} series to migrate:\n")
    for folder in sorted(series_folders):
        file_count = len(list(folder.glob("*.md")))
        print(f"   {folder.name}: {file_count} files")

    # Confirm migration
    print(f"\n⚠️  This will upload all files to Azure Blob container '{AZURE_STORAGE_CONTAINER_NAME}'")
    confirm = input("Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("Migration cancelled.")
        sys.exit(0)

    # Migrate files
    print("\n🚀 Starting migration...\n")

    total_uploaded = 0
    total_skipped = 0
    total_errors = 0
    total_bytes = 0

    for series_folder in sorted(series_folders):
        series_name = series_folder.name
        md_files = list(series_folder.glob("*.md"))

        if not md_files:
            print(f"⏭️  {series_name}: No .md files, skipping")
            continue

        print(f"📤 {series_name}: Uploading {len(md_files)} files...")

        for file_path in sorted(md_files):
            blob_name = f"{series_name}/{file_path.name}"

            try:
                # Read file content
                with open(file_path, "rb") as f:
                    content = f.read()

                # Upload to blob
                blob_client = container_client.get_blob_client(blob_name)
                blob_client.upload_blob(content, overwrite=True)

                total_uploaded += 1
                total_bytes += len(content)
                print(f"   ✓ {file_path.name} ({len(content):,} bytes)")

            except Exception as e:
                total_errors += 1
                print(f"   ✗ {file_path.name}: {e}")

    # Summary
    print("\n" + "=" * 50)
    print("📊 Migration Summary")
    print("=" * 50)
    print(f"   Files uploaded: {total_uploaded}")
    print(f"   Files skipped:  {total_skipped}")
    print(f"   Errors:         {total_errors}")
    print(f"   Total size:     {total_bytes:,} bytes ({total_bytes / 1024 / 1024:.2f} MB)")
    print(f"   Container:      {AZURE_STORAGE_CONTAINER_NAME}")

    if total_errors == 0:
        print("\n✅ Migration completed successfully!")
        print("\nNext steps:")
        print("1. Verify files in Azure Portal > Storage Account > Containers")
        print("2. Update .env with AZURE_STORAGE_CONNECTION_STRING (if not already)")
        print("3. Restart your OrbitLLM server")
        print("4. The server will now read from Azure Blob Storage")
        print("5. You can safely delete this script: rm migrate_to_azure_blob.py")
    else:
        print(f"\n⚠️  Migration completed with {total_errors} errors.")
        print("Please check the errors above and retry if needed.")


def verify():
    """Verify the migration by listing blobs in the container."""

    if not AZURE_STORAGE_CONNECTION_STRING:
        print("❌ Error: AZURE_STORAGE_CONNECTION_STRING not set")
        sys.exit(1)

    print("🔍 Verifying Azure Blob Storage contents...\n")

    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)

    # Count files per series
    series_counts = {}
    total_size = 0

    for blob in container_client.list_blobs():
        if "/" in blob.name:
            series = blob.name.split("/")[0]
            if blob.name.endswith(".md"):
                series_counts[series] = series_counts.get(series, 0) + 1
                total_size += blob.size

    print(f"Container: {AZURE_STORAGE_CONTAINER_NAME}\n")
    print("Series in Azure Blob Storage:")
    for series, count in sorted(series_counts.items()):
        print(f"   {series}: {count} files")

    print(f"\nTotal: {sum(series_counts.values())} files, {total_size:,} bytes")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        verify()
    else:
        migrate()
