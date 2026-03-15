from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class DsConfig(AppConfig):
    name = "app.ds"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from django.conf import settings

        from .infrastructure.container import Container

        self._container = Container.build(settings)

        try:
            self._container.search_index.rebuild_from_lake(settings.LAKE_DIR)
        except Exception:
            logger.warning("Could not rebuild search index on startup", exc_info=True)
