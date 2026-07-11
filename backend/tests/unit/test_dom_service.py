from app.services.dom_service import DOMService


def test_extracts_body_tree(products_html: str):
    structured = DOMService().extract_structure(products_html)
    assert structured["tag"] == "body"
    assert structured["children"]


def test_keeps_useful_attributes(products_html: str):
    structured = DOMService().extract_structure(products_html)
    # Find any node carrying an href from the product links
    def find_href(node) -> bool:
        if node.get("attributes", {}).get("href"):
            return True
        return any(find_href(c) for c in node.get("children", []))

    assert find_href(structured)


def test_truncates_wide_sibling_runs():
    html = "<html><body><ul>" + "<li>x</li>" * 50 + "</ul></body></html>"
    dom = DOMService(max_children_per_node=15)
    structured = dom.extract_structure(html)
    ul = structured["children"][0]
    # 15 kept + 1 truncation marker
    assert len(ul["children"]) == 16
    assert ul["children"][-1]["truncated"].endswith("siblings omitted")


def test_drops_scripts_and_styles():
    html = "<html><body><p>hi</p><script>evil()</script><style>x{}</style></body></html>"
    structured = DOMService().extract_structure(html)
    tags = [c["tag"] for c in structured["children"]]
    assert "script" not in tags
    assert "style" not in tags
