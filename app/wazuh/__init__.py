"""Clientes de acceso a Wazuh: API REST (client) e Indexer/OpenSearch (indexer)."""

from .client import WazuhAPIError, WazuhClient
from .indexer import IndexerClient, IndexerError

__all__ = ["WazuhClient", "WazuhAPIError", "IndexerClient", "IndexerError"]
