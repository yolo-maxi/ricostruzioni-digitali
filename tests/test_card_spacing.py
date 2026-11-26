"""Keep breathing room below both inputs without changing the fixed card."""
from test_site import PUBLIC, Tree, Node


def test_download_rows_have_deliberate_spacing_inside_fixed_cards():
    page = (PUBLIC / "index.html").read_text()
    tree = Tree(page)
    for card_id, input_id in (("face-capitals", "tester-a"), ("face-panel", "tester-p")):
        card = tree.by_id(card_id)
        field = tree.by_id(input_id)
        rows = [n for n in card.iter("div") if "face-downloads" in n.classes()]
        assert len(rows) == 1
        row = rows[0]
        assert row.parent is field.parent
        siblings = [n for n in row.parent.children if isinstance(n, Node)]
        assert siblings.index(row) == siblings.index(field) + 1
        assert len(list(row.iter("a"))) == 2
    assert ".face-downloads{display:flex;gap:8px;margin-top:16px}" in page
    assert ".face-downloads .pill{margin:0;white-space:nowrap}" in page
    assert ".face{height:490px" in page
    assert ".face-body{height:188px;padding:12px 20px}" in page
