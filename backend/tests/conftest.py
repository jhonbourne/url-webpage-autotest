from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "pages"


@pytest.fixture
def products_html() -> str:
    return (FIXTURES / "products.html").read_text(encoding="utf-8")
