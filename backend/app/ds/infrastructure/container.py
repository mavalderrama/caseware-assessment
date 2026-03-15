from __future__ import annotations

from typing import Any

from ..use_cases.ingest import IngestUseCase
from ..use_cases.search import SearchUseCase
from .checkpoint import FileCheckpointStore
from .event_emitter import FileAndSqsEventEmitter
from .lake_writer import LakeWriter
from .search_index import InMemorySearchIndex


class Container:
    """Wires all concrete implementations to use-case constructors."""

    def __init__(
        self,
        ingest_use_case: IngestUseCase,
        search_use_case: SearchUseCase,
        search_index: InMemorySearchIndex,
    ) -> None:
        self.ingest_use_case = ingest_use_case
        self.search_use_case = search_use_case
        self.search_index = search_index

    @classmethod
    def build(cls, settings: Any) -> Container:
        from ..adapters.repositories.case_repository import DjangoCaseRepository
        from ..adapters.repositories.customer_repository import DjangoCustomerRepository

        checkpoint_store = FileCheckpointStore(settings.STATE_DIR)
        lake_writer = LakeWriter(settings.LAKE_DIR)

        sqs_client = None
        queue_url = getattr(settings, "EVENTS_QUEUE_URL", "")
        if queue_url:
            try:
                import boto3

                sqs_client = boto3.client(
                    "sqs",
                    endpoint_url=getattr(settings, "AWS_ENDPOINT_URL", None),
                )
            except Exception:
                pass

        event_emitter = FileAndSqsEventEmitter(
            events_dir=settings.EVENTS_DIR,
            queue_url=queue_url,
            sqs_client=sqs_client,
        )

        search_index = InMemorySearchIndex(
            model_name=getattr(settings, "EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        )

        customer_repo = DjangoCustomerRepository()
        case_repo = DjangoCaseRepository()

        ingest_use_case = IngestUseCase(
            customer_repository=customer_repo,
            case_repository=case_repo,
            checkpoint_store=checkpoint_store,
            lake_writer=lake_writer,
            event_emitter=event_emitter,
            search_index=search_index,
            lake_dir=settings.LAKE_DIR,
        )

        search_use_case = SearchUseCase(search_index=search_index)

        return cls(
            ingest_use_case=ingest_use_case,
            search_use_case=search_use_case,
            search_index=search_index,
        )
