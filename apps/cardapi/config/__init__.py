"""
Configuration Package for CardAPI
==================================

Minimal configuration for CardAPI backend.

Usage:
    from config import AZURE_COSMOS_CONNECTION_STRING, AZURE_COSMOS_DATABASE_NAME
"""

from .appconfig_provider import bootstrap_appconfig
from .settings import (
    AZURE_COSMOS_CONNECTION_STRING,
)

__all__ = [
    "bootstrap_appconfig",
    "AZURE_COSMOS_CONNECTION_STRING"
]
