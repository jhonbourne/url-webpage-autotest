"""Controlled executor for a declarative SelectorPlan.

This is the security-relevant substitute for the old 'generate code + subprocess'
path: the LLM only produces selectors, and this fixed, auditable code applies them.
"""

import logging
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

from app.services.extraction.models import FieldSelector, SelectorPlan

logger = logging.getLogger(__name__)


class SelectorExecutor:
    def execute(
        self, html: str, selector_plan: SelectorPlan, is_list: bool
    ) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")

        if is_list and selector_plan.record_selector:
            containers = soup.select(selector_plan.record_selector)
            records = [self._extract_record(c, selector_plan.fields) for c in containers]
        else:
            records = [self._extract_record(soup, selector_plan.fields)]

        logger.info("selector execution produced %d record(s)", len(records))
        return records

    def _extract_record(
        self, scope: Tag | BeautifulSoup, fields: dict[str, FieldSelector]
    ) -> dict[str, Any]:
        record: dict[str, Any] = {}
        for name, spec in fields.items():
            record[name] = self._extract_field(scope, spec)
        return record

    @staticmethod
    def _extract_field(scope: Tag | BeautifulSoup, spec: FieldSelector) -> str | None:
        try:
            element = scope.select_one(spec.selector) if spec.selector else scope
        except Exception:
            # An invalid selector yields a null value rather than crashing the run
            return None
        if element is None:
            return None
        if spec.attr == "text":
            text = element.get_text(strip=True)
            return text or None
        value = element.get(spec.attr)
        if isinstance(value, list):
            return " ".join(value)
        return value
