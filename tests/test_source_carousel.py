"""Exact owner-authorized original-page publication and presentation contract."""
import hashlib
import re
import subprocess
import zipfile

from test_site import LAB, PUBLIC, ROOT, Tree, make_public

NAMES = (
    "HXwNYdeXgAE-ocC.jpg", "HXwNV_7W8AAs8y6.jpg", "HXwNXsUWEAALJek.jpg",
    "HXwNW6bWQAAleia.jpg", "brown-capitals-original.jpg", "capitals-original.jpg",
    "school-original.jpg", "cover-original.jpg", "green-original.jpg",
    "blackletter-source.jpg", "alphabet-sheet-source.jpg", "cursive-source.jpg",
)
INPUTS = [LAB / "assets" / n for n in NAMES[:9]] + [
    ROOT / "experiments" / probe / "input" / name
    for probe, name in zip(("blackletter-probe", "alphabet-sheet-probe", "cursive-probe"), NAMES[9:])
]


def test_exact_original_allowlist_and_unchanged_input_bytes():
    assert list(make_public.SOURCE_PAGES) == list(NAMES)
    assert list(make_public.SOURCE_PAGES.values()) == INPUTS
    assert sorted(p.name for p in (PUBLIC / "source-pages").iterdir()) == sorted(NAMES)
    for name, source in zip(NAMES, INPUTS):
        assert (PUBLIC / "source-pages" / name).read_bytes() == source.read_bytes()
        assert not re.search(r"proof|crop|rectified|mask|contact|overlay|glyph", name)


def test_carousel_is_first_and_full_originals_are_accessible_without_script():
    page = (PUBLIC / "index.html").read_text()
    tree = Tree(page)
    study = tree.by_id("study")
    carousel = tree.by_id("study-source-pages")
    assert next(study.iter()) is carousel
    assert carousel.attrs["aria-labelledby"] == "source-pages-heading"
    assert tree.by_id("source-pages-heading").text() == "Full source pages"
    assert tree.order.index(carousel) < tree.order.index(tree.by_id("study-method"))
    images = list(carousel.iter("img"))
    assert [n.attrs["src"] for n in images] == ["source-pages/" + n for n in NAMES]
    for image, name in zip(images, NAMES):
        assert name in image.attrs["alt"]
        assert "complete original input" in image.attrs["alt"]
        assert image.parent is tree.by_id("source-slides")
        assert image.attrs["loading"] == "lazy"
    assert not list(carousel.iter("figure"))
    assert not list(carousel.iter("figcaption"))
    assert all("hidden" not in n.attrs for n in images)
    track = tree.by_id("source-slides")
    assert track.attrs["class"] == "source-slides"
    assert track.attrs["aria-label"] == "Scrollable full source pages"
    assert "Display permission does not grant a source-image licence" in carousel.text()
    assert "CC BY 4.0 applies only to the reconstructed fonts" in carousel.text()
    assert "width:auto;height:65vh;max-height:680px" in page
    assert ".source-slides{display:flex;gap:14px;overflow-x:auto;overscroll-behavior-x:contain;scroll-snap-type:x mandatory" in page
    assert "scroll-snap-align:start;margin:0;border:0;padding:0;background:none}" in page
    assert track.attrs["tabindex"] == "0"
    assert all(n.tag == "img" for n in track.iter())
    assert "flex-wrap:wrap" in page and "overflow-wrap:anywhere" in page


def test_frozen_release_and_experiment_font_bytes_match_base():
    paths = list((PUBLIC / "fonts").iterdir()) + list((PUBLIC / "downloads").iterdir())
    paths += [p for p in (ROOT / "experiments").rglob("*") if p.suffix in (".ttf", ".woff2")]
    paths += [p for p in (PUBLIC / "experiments").iterdir() if p.suffix in (".ttf", ".woff2")]
    for path in paths:
        rel = path.relative_to(ROOT).as_posix()
        manifest = __import__("json").loads((ROOT / "docs/frozen-inputs.json").read_text())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest[rel], rel
