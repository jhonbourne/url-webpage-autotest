"""Pure HTML parsing and compression. No I/O — fetching lives in FetchService.

The compressed structure is what gets embedded into LLM prompts, so this module
is the main lever for token cost: scripts/styles are dropped, long runs of
similar siblings are truncated, and text is capped per node.
"""

from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

KEPT_ATTRIBUTES = ("id", "class", "href", "src", "name", "type", "role", "aria-label")
SKIPPED_TAGS = {"script", "style", "noscript", "svg", "iframe", "meta", "link"}


class DOMService:
    def __init__(
        self,
        max_depth: int = 12,
        max_children_per_node: int = 15,
        max_text_length: int = 120,
    ):
        self.max_depth = max_depth
        self.max_children_per_node = max_children_per_node
        self.max_text_length = max_text_length

    def extract_structure(self, html: str) -> dict[str, Any]:
        """Convert HTML into a compact JSON tree of the <body>."""
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(list(SKIPPED_TAGS)):
            tag.decompose()

        body = soup.find("body")
        if body is None:
            return {}
        return self._element_to_dict(body, depth=0)

    def count_nodes(self, structured: dict[str, Any]) -> int:
        if not structured:
            return 0
        return 1 + sum(self.count_nodes(child) for child in structured.get("children", []))

    # ---------- internals ----------

    def _element_to_dict(self, element: Tag, depth: int) -> dict[str, Any]:
        node: dict[str, Any] = {"tag": element.name}

        attributes = {}
        for attr in KEPT_ATTRIBUTES:
            value = element.get(attr)
            if value:
                attributes[attr] = " ".join(value) if isinstance(value, list) else value
        if attributes:
            node["attributes"] = attributes

        text = element.find(string=True, recursive=False)
        if text:
            stripped = text.strip()
            if stripped:
                node["text"] = stripped[: self.max_text_length]

        if depth >= self.max_depth:
            node["truncated"] = "max_depth"
            return node

        children = [
            self._element_to_dict(child, depth + 1)
            for child in element.find_all(recursive=False)
            if child.name not in SKIPPED_TAGS
        ]
        if len(children) > self.max_children_per_node:
            omitted = len(children) - self.max_children_per_node
            children = children[: self.max_children_per_node]
            children.append({"tag": "...", "truncated": f"{omitted} similar siblings omitted"})
        if children:
            node["children"] = children

        return node
