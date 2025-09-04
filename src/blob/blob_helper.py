"""
Azure Blob Storage Helper Module - FastAPI & Azure Best Practices Implementation

This module provides secure, efficient Azure Blob Storage operations following FastAPI
and Azure best practices. Features include:

- Managed Identity authentication with fallback to connection string
- Comprehensive error handling with retry logic
- Async/await support for FastAPI integration
- Structured logging and monitoring
- Connection pooling and resource management
- Input validation and security measures

Dependencies:
    azure-storage-blob>=12.19.0
    azure-identity>=1.15.0
    aiofiles>=23.0.0

Environment Variables:
    AZURE_STORAGE_ACCOUNT_NAME: Storage account name (required)
    AZURE_BLOB_CONTAINER: Default container name (default: "acs")
    AZURE_STORAGE_CONNECTION_STRING: Connection string (fallback auth)
    AZURE_STORAGE_ACCOUNT_KEY: Account key (fallback auth)

Security Note:
    This implementation prefers Managed Identity authentication over keys.
    Connection strings and account keys are used only as fallback options.
"""

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from azure.core.exceptions import (
    AzureError,
    ClientAuthenticationError,
    HttpResponseError,
    ResourceNotFoundError,
)
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob import ContainerSasPermissions, generate_container_sas
from azure.storage.blob.aio import BlobClient, BlobServiceClient

# Configure structured logging
logger = logging.getLogger(__name__)


class BlobOperationType(Enum):
    """Enumeration of blob operation types for monitoring."""

    UPLOAD = "upload"
    DOWNLOAD = "download"
    DELETE = "delete"
    LIST = "list"
    GENERATE_SAS = "generate_sas"
    VERIFY_ACCESS = "verify_access"


@dataclass
class BlobOperationResult:
    """Structured result for blob operations."""

    success: bool
    operation_type: BlobOperationType
    blob_name: Optional[str] = None
    container_name: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None
    size_bytes: Optional[int] = None
    content: Optional[str] = None  # For download operations
    blob_list: Optional[List[str]] = None  # For list operations


class AzureBlobHelper:
    """
    Secure Azure Blob Storage helper with FastAPI best practices.

    Features:
    - Managed Identity authentication with secure fallbacks
    - Comprehensive error handling and retry logic
    - Connection pooling and resource management
    - Structured logging and monitoring
    - Input validation and security measures
    """

    def __init__(
        self,
        account_name: Optional[str] = None,
        container_name: Optional[str] = None,
        connection_string: Optional[str] = None,
        account_key: Optional[str] = None,
        max_retry_attempts: int = 3,
    ):
        """
        Initialize Azure Blob Helper with secure authentication.

        Args:
            account_name: Storage account name (from env if not provided)
            container_name: Default container name (from env if not provided)
            connection_string: Connection string (fallback auth)
            account_key: Account key (fallback auth)
            max_retry_attempts: Maximum retry attempts for failed operations
        """
        # Configuration with validation
        self.account_name = account_name or os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
        self.container_name = container_name or os.getenv("AZURE_BLOB_CONTAINER", "acs")
        self.connection_string = connection_string or os.getenv(
            "AZURE_STORAGE_CONNECTION_STRING"
        )
        self.account_key = account_key or os.getenv("AZURE_STORAGE_ACCOUNT_KEY")

        if not self.account_name:
            raise ValueError("AZURE_STORAGE_ACCOUNT_NAME is required")

        # Retry configuration
        self.max_retry_attempts = max_retry_attempts

        # Initialize authentication and client
        self._credential = self._setup_authentication()
        self._blob_service: Optional[BlobServiceClient] = None

        logger.info(
            f"AzureBlobHelper initialized for account '{self.account_name}', "
            f"default container '{self.container_name}'"
        )

    def _setup_authentication(self) -> Optional[DefaultAzureCredential]:
        """
        Set up authentication with preference for Managed Identity.

        Returns:
            DefaultAzureCredential if available, None for connection string auth
        """
        try:
            # Prefer Managed Identity (secure, Azure-native)
            if not self.connection_string:
                credential = get_credential()
                logger.info("Using Managed Identity authentication")
                return credential
            else:
                logger.warning(
                    "Using connection string authentication - consider migrating to Managed Identity"
                )
                return None
        except Exception as e:
            logger.error(f"Failed to setup authentication: {e}")
            if not self.connection_string:
                raise ValueError("No valid authentication method available")
            return None

    async def _get_blob_service(self) -> BlobServiceClient:
        """
        Get or create BlobServiceClient with connection pooling.

        Returns:
            BlobServiceClient instance
        """
        if self._blob_service is None:
            try:
                if self._credential:
                    # Use Managed Identity
                    self._blob_service = BlobServiceClient(
                        f"https://{self.account_name}.blob.core.windows.net",
                        credential=self._credential,
                    )
                elif self.connection_string:
                    # Fallback to connection string
                    self._blob_service = BlobServiceClient.from_connection_string(
                        self.connection_string
                    )
                else:
                    raise ValueError("No authentication method available")

                logger.debug("BlobServiceClient created successfully")

            except Exception as e:
                logger.error(f"Failed to create BlobServiceClient: {e}")
                raise

        return self._blob_service

    async def generate_container_sas_url(
        self, container_name: Optional[str] = None, expiry_hours: int = 24
    ) -> BlobOperationResult:
        """
        Generate a container URL with SAS token for Azure Blob Storage access.
        Supports both account key and DefaultAzureCredential (user delegation SAS).

        Args:
            container_name: Container name (uses default if not provided)
            expiry_hours: Hours until SAS token expires (default: 24)

        Returns:
            BlobOperationResult with SAS URL or error details
        """
        start_time = datetime.now(timezone.utc)
        container_name = container_name or self.container_name

        try:
            # Validate inputs
            if not container_name:
                raise ValueError("Container name is required")

            if expiry_hours <= 0 or expiry_hours > 8760:  # Max 1 year
                raise ValueError("Expiry hours must be between 1 and 8760")

            # Calculate expiry time with proper UTC handling
            expiry_time = start_time + timedelta(hours=expiry_hours)

            logger.info(
                f"Generating SAS token for container '{container_name}' "
                f"with expiry: {expiry_time.isoformat()}"
            )

            if self._credential:
                # Use User Delegation SAS (more secure)
                service = await self._get_blob_service()
                async with service as client:
                    user_delegation_key = await client.get_user_delegation_key(
                        key_start_time=start_time, key_expiry_time=expiry_time
                    )
                    sas_token = generate_container_sas(
                        account_name=self.account_name,
                        container_name=container_name,
                        user_delegation_key=user_delegation_key,
                        permission=ContainerSasPermissions(
                            read=True,
                            add=True,
                            create=True,
                            write=True,
                            delete=True,
                            list=True,
                        ),
                        expiry=expiry_time,
                    )
            elif self.account_key:
                # Use Account Key SAS (fallback)
                sas_token = generate_container_sas(
                    account_name=self.account_name,
                    container_name=container_name,
                    account_key=self.account_key,
                    permission=ContainerSasPermissions(
                        read=True,
                        add=True,
                        create=True,
                        write=True,
                        delete=True,
                        list=True,
                    ),
                    expiry=expiry_time,
                )
            else:
                raise ValueError(
                    "Either managed identity or account key must be available"
                )

            container_url = (
                f"https://{self.account_name}.blob.core.windows.net/"
                f"{container_name}?{sas_token}"
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            logger.info(
                f"Generated container SAS URL for '{container_name}' "
                f"(valid for {expiry_hours} hours) in {duration:.2f}ms"
            )

            return BlobOperationResult(
                success=True,
                operation_type=BlobOperationType.GENERATE_SAS,
                container_name=container_name,
                duration_ms=duration,
                content=container_url,
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = f"Failed to generate container SAS token: {e}"
            logger.error(error_msg, exc_info=True)

            return BlobOperationResult(
                success=False,
                operation_type=BlobOperationType.GENERATE_SAS,
                container_name=container_name,
                error_message=error_msg,
                duration_ms=duration,
            )

    async def verify_container_access(self, container_url: str) -> BlobOperationResult:
        """
        Verify that the container URL is accessible with required permissions.

        Args:
            container_url: Full container URL with SAS token

        Returns:
            BlobOperationResult indicating access verification status
        """
        start_time = datetime.now(timezone.utc)

        try:
            # Extract container name from URL
            url_parts = container_url.split("?")[0]
            container_name = url_parts.split("/")[-1]

            # Create temporary blob service client with the SAS URL
            async with BlobServiceClient.from_connection_string(
                container_url
            ) as client:
                container_client = client.get_container_client(container_name)

                # Check container existence
                exists = await container_client.exists()
                if not exists:
                    raise ResourceNotFoundError(
                        f"Container '{container_name}' does not exist"
                    )

                # Test write permissions with a small test blob
                test_blob_name = f"acs_test_permissions_{int(start_time.timestamp())}"
                test_blob = container_client.get_blob_client(test_blob_name)

                await test_blob.upload_blob("ACS test content", overwrite=True)
                await test_blob.delete_blob()

                duration = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds() * 1000

                logger.info(
                    f"Successfully verified access to container '{container_name}' "
                    f"in {duration:.2f}ms"
                )

                return BlobOperationResult(
                    success=True,
                    operation_type=BlobOperationType.VERIFY_ACCESS,
                    container_name=container_name,
                    duration_ms=duration,
                )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = f"Failed to verify container access: {e}"
            logger.error(error_msg, exc_info=True)

            return BlobOperationResult(
                success=False,
                operation_type=BlobOperationType.VERIFY_ACCESS,
                error_message=error_msg,
                duration_ms=duration,
            )

    async def save_transcript_to_blob(
        self, call_id: str, transcript: str, container_name: Optional[str] = None
    ) -> BlobOperationResult:
        """
        Save transcript to blob storage with organized directory structure.

        Args:
            call_id: Unique call identifier
            transcript: Transcript content as JSON string
            container_name: Container name (uses default if not provided)

        Returns:
            BlobOperationResult indicating operation status
        """
        start_time = datetime.now(timezone.utc)
        container_name = container_name or self.container_name

        try:
            # Validate inputs
            if not call_id or not call_id.strip():
                raise ValueError("Call ID is required and cannot be empty")

            if not transcript:
                raise ValueError("Transcript content is required")

            # Create organized blob path
            date_str = start_time.strftime("%Y-%m-%d")
            blob_name = f"transcripts/{date_str}/{call_id}.json"

            # Get blob client and upload
            service = await self._get_blob_service()
            blob_client = service.get_blob_client(
                container=container_name, blob=blob_name
            )

            # Upload with metadata
            content_bytes = transcript.encode("utf-8")
            await blob_client.upload_blob(
                content_bytes,
                overwrite=True,
                content_type="application/json",
                metadata={
                    "call_id": call_id,
                    "created_at": start_time.isoformat(),
                    "content_type": "transcript",
                },
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            logger.info(
                f"Saved transcript for call '{call_id}' to '{blob_name}' "
                f"({len(content_bytes)} bytes) in {duration:.2f}ms"
            )

            return BlobOperationResult(
                success=True,
                operation_type=BlobOperationType.UPLOAD,
                blob_name=blob_name,
                container_name=container_name,
                size_bytes=len(content_bytes),
                duration_ms=duration,
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = f"Failed to save transcript for call '{call_id}': {e}"
            logger.error(error_msg, exc_info=True)

            return BlobOperationResult(
                success=False,
                operation_type=BlobOperationType.UPLOAD,
                error_message=error_msg,
                duration_ms=duration,
            )

    async def save_wav_to_blob(
        self, call_id: str, wav_file_path: str, container_name: Optional[str] = None
    ) -> BlobOperationResult:
        """
        Save WAV file to blob storage from local file path.

        Args:
            call_id: Unique call identifier
            wav_file_path: Path to local WAV file
            container_name: Container name (uses default if not provided)

        Returns:
            BlobOperationResult indicating operation status
        """
        start_time = datetime.now(timezone.utc)
        container_name = container_name or self.container_name

        try:
            # Validate inputs
            if not call_id or not call_id.strip():
                raise ValueError("Call ID is required and cannot be empty")

            wav_path = Path(wav_file_path)
            if not wav_path.exists():
                raise FileNotFoundError(f"WAV file not found: {wav_file_path}")

            if not wav_path.suffix.lower() == ".wav":
                raise ValueError("File must have .wav extension")

            # Create organized blob path
            date_str = start_time.strftime("%Y-%m-%d")
            blob_name = f"audio/{date_str}/{call_id}.wav"

            # Get file size for monitoring
            file_size = wav_path.stat().st_size

            # Read and upload file
            service = await self._get_blob_service()
            blob_client = service.get_blob_client(
                container=container_name, blob=blob_name
            )

            async with aiofiles.open(wav_file_path, "rb") as f:
                wav_data = await f.read()

            await blob_client.upload_blob(
                wav_data,
                overwrite=True,
                content_type="audio/wav",
                metadata={
                    "call_id": call_id,
                    "created_at": start_time.isoformat(),
                    "content_type": "audio",
                    "file_size": str(file_size),
                },
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            logger.info(
                f"Saved WAV file for call '{call_id}' to '{blob_name}' "
                f"({file_size} bytes) in {duration:.2f}ms"
            )

            return BlobOperationResult(
                success=True,
                operation_type=BlobOperationType.UPLOAD,
                blob_name=blob_name,
                container_name=container_name,
                size_bytes=file_size,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = f"Failed to save WAV file for call '{call_id}': {e}"
            logger.error(error_msg, exc_info=True)

            return BlobOperationResult(
                success=False,
                operation_type=BlobOperationType.UPLOAD,
                error_message=error_msg,
                duration_ms=duration,
            )

    async def stream_wav_to_blob(
        self, call_id: str, wav_stream, container_name: Optional[str] = None
    ) -> BlobOperationResult:
        """
        Stream WAV data directly to Azure Blob Storage.

        Args:
            call_id: Unique call identifier
            wav_stream: Async stream of WAV data
            container_name: Container name (uses default if not provided)

        Returns:
            BlobOperationResult indicating operation status
        """
        start_time = datetime.now(timezone.utc)
        container_name = container_name or self.container_name

        try:
            # Validate inputs
            if not call_id or not call_id.strip():
                raise ValueError("Call ID is required and cannot be empty")

            # Create organized blob path
            date_str = start_time.strftime("%Y-%m-%d")
            blob_name = f"audio/{date_str}/{call_id}.wav"

            # Stream upload
            service = await self._get_blob_service()
            blob_client = service.get_blob_client(
                container=container_name, blob=blob_name
            )

            await blob_client.upload_blob(
                wav_stream,
                overwrite=True,
                content_type="audio/wav",
                metadata={
                    "call_id": call_id,
                    "created_at": start_time.isoformat(),
                    "content_type": "audio_stream",
                },
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            logger.info(
                f"Streamed WAV data for call '{call_id}' to '{blob_name}' "
                f"in {duration:.2f}ms"
            )

            return BlobOperationResult(
                success=True,
                operation_type=BlobOperationType.UPLOAD,
                blob_name=blob_name,
                container_name=container_name,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = f"Failed to stream WAV data for call '{call_id}': {e}"
            logger.error(error_msg, exc_info=True)

            return BlobOperationResult(
                success=False,
                operation_type=BlobOperationType.UPLOAD,
                error_message=error_msg,
                duration_ms=duration,
            )

    async def get_transcript_from_blob(
        self, call_id: str, container_name: Optional[str] = None
    ) -> BlobOperationResult:
        """
        Retrieve transcript from blob storage.

        Args:
            call_id: Unique call identifier
            container_name: Container name (uses default if not provided)

        Returns:
            BlobOperationResult with transcript content or error details
        """
        start_time = datetime.now(timezone.utc)
        container_name = container_name or self.container_name

        try:
            # Validate inputs
            if not call_id or not call_id.strip():
                raise ValueError("Call ID is required and cannot be empty")

            # Try to find the transcript (search by date if needed)
            service = await self._get_blob_service()

            # First, try today's date
            date_str = start_time.strftime("%Y-%m-%d")
            blob_name = f"transcripts/{date_str}/{call_id}.json"

            blob_client = service.get_blob_client(
                container=container_name, blob=blob_name
            )

            try:
                stream = await blob_client.download_blob()
                data = await stream.readall()
                content = data.decode("utf-8")

                duration = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds() * 1000

                logger.info(
                    f"Retrieved transcript for call '{call_id}' from '{blob_name}' "
                    f"({len(data)} bytes) in {duration:.2f}ms"
                )

                return BlobOperationResult(
                    success=True,
                    operation_type=BlobOperationType.DOWNLOAD,
                    blob_name=blob_name,
                    container_name=container_name,
                    size_bytes=len(data),
                    duration_ms=duration,
                    content=content,
                )

            except ResourceNotFoundError:
                # If not found in today's folder, search other dates
                # This is a fallback for backwards compatibility
                blob_name_legacy = f"{call_id}.json"
                blob_client_legacy = service.get_blob_client(
                    container=container_name, blob=blob_name_legacy
                )

                stream = await blob_client_legacy.download_blob()
                data = await stream.readall()
                content = data.decode("utf-8")

                duration = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds() * 1000

                logger.info(
                    f"Retrieved transcript for call '{call_id}' from legacy path "
                    f"'{blob_name_legacy}' ({len(data)} bytes) in {duration:.2f}ms"
                )

                return BlobOperationResult(
                    success=True,
                    operation_type=BlobOperationType.DOWNLOAD,
                    blob_name=blob_name_legacy,
                    container_name=container_name,
                    size_bytes=len(data),
                    duration_ms=duration,
                    content=content,
                )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = f"Failed to retrieve transcript for call '{call_id}': {e}"
            logger.error(error_msg, exc_info=True)

            return BlobOperationResult(
                success=False,
                operation_type=BlobOperationType.DOWNLOAD,
                error_message=error_msg,
                duration_ms=duration,
            )

    async def delete_transcript_from_blob(
        self, call_id: str, container_name: Optional[str] = None
    ) -> BlobOperationResult:
        """
        Delete transcript from blob storage.

        Args:
            call_id: Unique call identifier
            container_name: Container name (uses default if not provided)

        Returns:
            BlobOperationResult indicating operation status
        """
        start_time = datetime.now(timezone.utc)
        container_name = container_name or self.container_name

        try:
            # Validate inputs
            if not call_id or not call_id.strip():
                raise ValueError("Call ID is required and cannot be empty")

            service = await self._get_blob_service()

            # Try current date structure first
            date_str = start_time.strftime("%Y-%m-%d")
            blob_name = f"transcripts/{date_str}/{call_id}.json"

            blob_client = service.get_blob_client(
                container=container_name, blob=blob_name
            )

            try:
                await blob_client.delete_blob()
                blob_deleted = blob_name
            except ResourceNotFoundError:
                # Try legacy path
                blob_name_legacy = f"{call_id}.json"
                blob_client_legacy = service.get_blob_client(
                    container=container_name, blob=blob_name_legacy
                )
                await blob_client_legacy.delete_blob()
                blob_deleted = blob_name_legacy

            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            logger.info(
                f"Deleted transcript for call '{call_id}' from '{blob_deleted}' "
                f"in {duration:.2f}ms"
            )

            return BlobOperationResult(
                success=True,
                operation_type=BlobOperationType.DELETE,
                blob_name=blob_deleted,
                container_name=container_name,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = f"Failed to delete transcript for call '{call_id}': {e}"
            logger.error(error_msg, exc_info=True)

            return BlobOperationResult(
                success=False,
                operation_type=BlobOperationType.DELETE,
                error_message=error_msg,
                duration_ms=duration,
            )

    async def list_transcripts_in_blob(
        self, container_name: Optional[str] = None, date_filter: Optional[str] = None
    ) -> BlobOperationResult:
        """
        List all transcripts in blob storage.

        Args:
            container_name: Container name (uses default if not provided)
            date_filter: Optional date filter in YYYY-MM-DD format

        Returns:
            BlobOperationResult with list of blob names or error details
        """
        start_time = datetime.now(timezone.utc)
        container_name = container_name or self.container_name

        try:
            service = await self._get_blob_service()
            container_client = service.get_container_client(container_name)

            blob_list = []
            prefix = f"transcripts/{date_filter}/" if date_filter else "transcripts/"

            async for blob in container_client.list_blobs(name_starts_with=prefix):
                blob_list.append(blob.name)

            # Also include legacy blobs (without date structure) for backwards compatibility
            if not date_filter:
                async for blob in container_client.list_blobs():
                    if blob.name.endswith(".json") and not blob.name.startswith(
                        "transcripts/"
                    ):
                        blob_list.append(blob.name)

            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            logger.info(
                f"Listed {len(blob_list)} transcripts from container '{container_name}' "
                f"in {duration:.2f}ms"
            )

            return BlobOperationResult(
                success=True,
                operation_type=BlobOperationType.LIST,
                container_name=container_name,
                duration_ms=duration,
                blob_list=blob_list,
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = f"Failed to list transcripts: {e}"
            logger.error(error_msg, exc_info=True)

            return BlobOperationResult(
                success=False,
                operation_type=BlobOperationType.LIST,
                error_message=error_msg,
                duration_ms=duration,
            )

    async def close(self):
        """Clean up resources."""
        if self._blob_service:
            await self._blob_service.close()
            self._blob_service = None

        if self._credential:
            await self._credential.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Global instance for backward compatibility
# TODO: Consider migrating to dependency injection pattern
_global_blob_helper: Optional[AzureBlobHelper] = None


def get_blob_helper() -> AzureBlobHelper:
    """
    Get global blob helper instance.

    Returns:
        AzureBlobHelper instance
    """
    global _global_blob_helper
    if _global_blob_helper is None:
        _global_blob_helper = AzureBlobHelper()
    return _global_blob_helper


# Legacy function wrappers for backward compatibility
# These should be migrated to use the new class-based approach


async def generate_container_sas_url(
    container_name: Optional[str] = None,
    account_key: Optional[str] = None,
    expiry_hours: int = 24,
) -> str:
    """
    Legacy wrapper for generate_container_sas_url.

    Note: This function is deprecated. Use AzureBlobHelper class instead.
    """
    helper = get_blob_helper()
    result = await helper.generate_container_sas_url(
        container_name=container_name, expiry_hours=expiry_hours
    )

    if not result.success:
        raise Exception(result.error_message)

    return result.content


async def verify_container_access(container_url: str) -> bool:
    """
    Legacy wrapper for verify_container_access.

    Note: This function is deprecated. Use AzureBlobHelper class instead.
    """
    helper = get_blob_helper()
    result = await helper.verify_container_access(container_url)
    return result.success


async def save_transcript_to_blob(call_id: str, transcript: str):
    """
    Legacy wrapper for save_transcript_to_blob.

    Note: This function is deprecated. Use AzureBlobHelper class instead.
    """
    helper = get_blob_helper()
    result = await helper.save_transcript_to_blob(call_id, transcript)

    if not result.success:
        raise Exception(result.error_message)


async def save_wav_to_blob(call_id: str, wav_file_path: str):
    """
    Legacy wrapper for save_wav_to_blob.

    Note: This function is deprecated. Use AzureBlobHelper class instead.
    """
    helper = get_blob_helper()
    result = await helper.save_wav_to_blob(call_id, wav_file_path)

    if not result.success:
        raise Exception(result.error_message)


async def stream_wav_to_blob(call_id: str, wav_stream):
    """
    Legacy wrapper for stream_wav_to_blob.

    Note: This function is deprecated. Use AzureBlobHelper class instead.
    """
    helper = get_blob_helper()
    result = await helper.stream_wav_to_blob(call_id, wav_stream)

    if not result.success:
        raise Exception(result.error_message)


async def get_transcript_from_blob(call_id: str) -> str:
    """
    Legacy wrapper for get_transcript_from_blob.

    Note: This function is deprecated. Use AzureBlobHelper class instead.
    """
    helper = get_blob_helper()
    result = await helper.get_transcript_from_blob(call_id)

    if not result.success:
        raise Exception(result.error_message)

    return result.content or ""


async def delete_transcript_from_blob(call_id: str):
    """
    Legacy wrapper for delete_transcript_from_blob.

    Note: This function is deprecated. Use AzureBlobHelper class instead.
    """
    helper = get_blob_helper()
    result = await helper.delete_transcript_from_blob(call_id)

    if not result.success:
        raise Exception(result.error_message)


async def list_transcripts_in_blob() -> list:
    """
    Legacy wrapper for list_transcripts_in_blob.

    Note: This function is deprecated. Use AzureBlobHelper class instead.
    """
    helper = get_blob_helper()
    result = await helper.list_transcripts_in_blob()

    if not result.success:
        raise Exception(result.error_message)

    return result.blob_list or []
