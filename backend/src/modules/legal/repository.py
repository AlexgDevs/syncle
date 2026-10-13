"""Repositories for legal scan history (issue #61, core/base templates)."""

from src.core.base import BaseRepository
from src.modules.legal.models import LegalDocument, LegalScan


class LegalScanRepository(BaseRepository[LegalScan]):
    model = LegalScan


class LegalDocumentRepository(BaseRepository[LegalDocument]):
    model = LegalDocument
