"""Checks for the served artifact: the two-tab viewer, the release package and the audit.

The viewer has two tabs:

* ``Fonts`` is the landing tab. It shows the two typefaces with editable
  specimens, the scope in plain words and the download section.
* ``Study`` holds the evidence: methods, source crops, scores, glyph
  labels, the proofs for s, t and z of the panel face, build notes, limits.

No browser is used. The tab script runs in Node against a stand-in for the
DOM (``tests/tabs_check.js``).

Run:  .venv/bin/python -m pytest -q
"""
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "source" / "balilla-lab"
PUBLIC = ROOT / "public"
sys.path.insert(0, str(LAB))

import make_public  # noqa: E402

FONTS = ("Balilla-Reconstructed.ttf", "Balilla-Reconstructed.woff2",
         "Balilla-Panel-Reconstructed.ttf", "Balilla-Panel-Reconstructed.woff2")
LABELS = ("Balilla — cover capitals",
          "Balilla Panel — pale panel lettering")
# Words of the evaluation and of the build. They belong in the Study tab, not in the Fonts tab.
JARGON = (r"\bdice\b", r"\biou\b", r"rectif", r"\bglyphs?\b", r"extrapolat", r"\bgates?\b", r"sha-?256",
          r"freetype", r"\bmasks?\b", r"supersampl", r"\bkerning\b", r"\bbaselines?\b", r"least-squares",
          r"\bhinting\b", r"homograph", r"\bpixels?\b", r"\bbearings?\b", r"\bfont units\b", r"\boverlay\b")
OVERCLAIMS = ("pixel-perfect", "perfect match", "100% similarity", "100% match", "identical to the original",
              "complete alphabet", "full alphabet", "faithful restoration", "authentic restoration",
              "open source", "free to use", "royalty-free", "public domain")
VOID = {"meta", "img", "input", "br", "link", "hr"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reports():
    ev = LAB / "evaluation"
    return (json.loads((ev / "report.json").read_text()),
            json.loads((ev / "panel-report.json").read_text()))


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.children, self.data = tag, dict(attrs), parent, [], []

    def iter(self, tag=None):
        for child in self.children:
            if isinstance(child, Node):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.iter(tag)

    def text(self):
        out = []
        for child in self.children:
            out.append(child.text() if isinstance(child, Node) else child)
        return re.sub(r"\s+", " ", " ".join(out)).strip()

    def classes(self):
        return (self.attrs.get("class") or "").split()

    def inside(self, other):
        node = self
        while node is not None:
            if node is other:
                return True
            node = node.parent
        return False


class Tree(HTMLParser):
    """A small tree of the page. It fails on a tag that is closed in the wrong place."""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.current = self.root
        self.order = []
        self.feed(text)
        assert self.current is self.root, "unclosed tag: " + self.current.tag

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        self.order.append(node)
        if tag not in VOID:
            self.current = node

    def handle_endtag(self, tag):
        assert self.current.tag == tag, "tag </%s> closes <%s>" % (tag, self.current.tag)
        self.current = self.current.parent

    def handle_data(self, data):
        if self.current.tag not in ("script", "style"):
            self.current.children.append(data)

    def by_id(self, ident):
        found = [n for n in self.order if n.attrs.get("id") == ident]
        assert len(found) == 1, "id %s occurs %d times" % (ident, len(found))
        return found[0]


@pytest.fixture(scope="module")
def page():
    return (PUBLIC / "index.html").read_text()


@pytest.fixture(scope="module")
def tree(page):
    return Tree(page)


# --------------------------------------------------------------------------
# two tabs
# --------------------------------------------------------------------------

def test_page_has_two_real_tabs_and_fonts_is_the_default(tree):
    lists = [n for n in tree.order if n.attrs.get("role") == "tablist"]
    assert len(lists) == 1 and lists[0].attrs.get("aria-label")
    tabs = [n for n in tree.order if n.attrs.get("role") == "tab"]
    assert [t.text() for t in tabs] == ["Fonts", "Study", "Experiments"]
    assert all(t.tag == "a" and t.attrs.get("href") in ("#fonts", "#study", "#experiments") and t.inside(lists[0]) for t in tabs)
    panels = [n for n in tree.order if n.attrs.get("role") == "tabpanel"]
    assert [p.attrs["id"] for p in panels] == ["fonts", "study", "experiments"]
    for tab, panel in zip(tabs, panels):
        assert tab.attrs["aria-controls"] == panel.attrs["id"]         # tab -> panel
        assert panel.attrs["aria-labelledby"] == tab.attrs["id"]       # panel -> tab
        assert panel.attrs.get("tabindex") == "0"                      # the panel can take the focus
    fonts_tab, study_tab, experiments_tab = tabs
    assert experiments_tab.attrs["aria-selected"] == "false" and experiments_tab.attrs["tabindex"] == "-1"
    assert all("hidden" not in p.attrs for p in panels)
    # Fonts is the default: selected, in the tab order, its panel shown; Study is not
    assert fonts_tab.attrs["aria-selected"] == "true" and fonts_tab.attrs["tabindex"] == "0"
    assert study_tab.attrs["aria-selected"] == "false" and study_tab.attrs["tabindex"] == "-1"
    # The no-script path leaves both panels readable. The inline controller selects
    # Fonts and hides Study only after it has successfully initialized.
    assert "hidden" not in panels[0].attrs and "hidden" not in panels[1].attrs
    # every heading and figure of the content is in one of the two panels
    for node in tree.order:
        if node.tag in ("h1", "h2", "h3", "h4", "figure", "table", "article"):
            assert any(node.inside(panel) for panel in panels), node.tag
    assert [n.tag for n in tree.order if n.tag == "h1"] == ["h1", "h1", "h1"]    # one main heading for each tab
    # one page, no second app or route: the tabs are in-page anchors, and the page has one document
    assert len([n for n in tree.order if n.tag == "main"]) == 1
    assert not [n for n in tree.order if n.tag in ("iframe", "frame", "object", "embed")]


def test_study_has_a_stable_share_address_and_works_without_script(page, tree):
    # the share address of the Study tab is the id of its panel: <page>#study
    assert tree.by_id("study").attrs["role"] == "tabpanel"
    fonts = tree.by_id("fonts")
    links = [a for a in fonts.iter("a") if a.attrs.get("href") == "#study"]
    assert links, "the Fonts tab has no link to the Study tab"
    script = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    for needed in ("location.hash", "hashchange", "aria-selected", "ArrowRight", "ArrowLeft",
                   "Home", "End", ".hidden", "tabIndex"):
        assert needed in script, needed
    # every link inside the page points at an element that exists
    ids = {n.attrs["id"] for n in tree.order if "id" in n.attrs}
    for a in tree.root.iter("a"):
        href = a.attrs.get("href", "")
        if href.startswith("#"):
            assert href[1:] in ids, href
    for ident in ("study-method", "study-capitals", "study-panel", "study-stz", "study-build",
                  "study-limits"):
        assert tree.by_id(ident).inside(tree.by_id("study")), ident
    assert tree.by_id("face-capitals").inside(fonts)
    # without script both tabs are readable: Study has no hidden attribute and the
    # tab controls are ordinary anchors that retain their hash destinations.
    noscript = re.search(r"<noscript>(.*?)</noscript>", page, re.S).group(1)
    assert "tabs" in noscript and "display:none" in noscript


def test_tab_script_behaviour_without_a_browser():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed; the tab script is not run")
    result = subprocess.run([node, str(ROOT / "tests" / "tabs_check.js"), str(PUBLIC / "index.html")],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.strip().splitlines()
    assert lines[-1] == "all checks passed"
    assert not [line for line in lines if line.startswith("FAIL")]
    for wanted in ("no hash: Fonts is the default tab", "address #study opens Study", "ArrowRight moves to Study",
                   "Home goes to Fonts", "End goes to Experiments", "address #study-stz scrolls to the proofs"):
        assert "ok   " + wanted in lines, wanted


# --------------------------------------------------------------------------
# Fonts tab
# --------------------------------------------------------------------------

def test_fonts_tab_has_two_fixed_cards_with_local_downloads(tree):
    fonts = tree.by_id("fonts")
    assert next(fonts.iter("h1")).text().startswith("Two fonts")
    cards = [n for n in fonts.iter("article") if "face" in n.classes()]
    assert [c.attrs["id"] for c in cards] == ["face-capitals", "face-panel"]
    for card, label, kind, stem, key in zip(cards, ("Cover Capitals", "Panel lettering"),
                                          ("caps", "panel"), (make_public.CAPITALS, make_public.PANEL), ("a", "p")):
        specimen = [n for n in card.iter("div") if "specimen" in n.classes()]
        assert len(specimen) == 1 and kind in specimen[0].classes()
        assert next(card.iter("h3")).text() == label
        links = list(card.iter("a"))
        assert [a.attrs["href"] for a in links] == ["./fonts/" + stem + ext for ext in (".ttf", ".woff2")]
        assert all("download" in a.attrs for a in links)
        sample = tree.by_id("live-" + key)
        assert sample.inside(card) and sample.attrs["lang"] == "it"
        assert len(sample.text()) > 60
        control = tree.by_id("recycle-" + key)
        assert control.inside(specimen[0]) and control.tag == "button"
        assert label in control.attrs["aria-label"] and "another" in control.attrs["aria-label"]
        assert control.text() == "♻️"
    assert [n.attrs["id"] for n in fonts.iter("input")] == ["tester-a", "tester-p"]
    for key, card in zip(("a", "p"), cards):
        field = tree.by_id("tester-" + key)
        assert field.inside(card) and field.attrs["type"] == "text"
        assert any(n.attrs.get("for") == field.attrs["id"] and n.text() == "Scrivi qualcosa" for n in card.iter("label"))
    assert not [n for n in fonts.iter() if "contenteditable" in n.attrs]
    assert len([a for a in fonts.iter("a") if "download" in a.attrs]) == 4


def test_fonts_tab_ends_with_license_and_fits_both_dimensions(tree, page):
    fonts = tree.by_id("fonts")
    children = [n for n in fonts.children if isinstance(n, Node)]
    assert children[-1].classes() == ["license-strip"]
    assert "CC BY 4.0" in children[-1].text()
    assert "attribution to Balilla Type Lab" in children[-1].text()
    assert not list(fonts.iter("h2"))
    for hook in (".faces{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))",
                 ".face{height:490px", "height:300px", ".faces,.scope{grid-template-columns:1fr}",
                 "right:12px;bottom:12px", "text.scrollWidth <= box.clientWidth",
                 "text.scrollHeight <= box.clientHeight", "getBoundingClientRect().height",
                 "document.fonts.ready.then(fitAll)", "window.ResizeObserver", "fitAll();"):
        assert hook in page
    assert "original-materials.zip" not in page
    assert "Download the fonts" not in fonts.text()


def test_fonts_tab_is_plain_and_truthful(tree):
    fonts = tree.by_id("fonts")
    text = fonts.text()
    lowered = text.lower()
    for pattern in JARGON:
        assert not re.search(pattern, lowered), "evaluation word in the Fonts tab: " + pattern
    assert not re.search(r"\d\d\.\d\d ?%", text), "a score is in the Fonts tab"
    assert not [n for n in fonts.iter() if n.tag in ("figure", "table", "pre", "code")]
    for label in ("Cover Capitals", "Panel lettering"):
        assert label in text
    for truth in ("CC BY 4.0", "attribution to Balilla Type Lab"):
        assert truth in text, truth
    for claim in OVERCLAIMS:
        assert claim not in lowered, claim
    assert len(text.split()) < 120


# --------------------------------------------------------------------------
# Study tab
# --------------------------------------------------------------------------

def test_study_tab_lists_the_evidence_for_each_face(tree, page):
    study = tree.by_id("study")
    text = study.text()
    rep, prep = reports()
    assert [h.text() for h in study.iter("h2")] == [
        "Full source pages", LABELS[0], LABELS[1], "Panel face: proofs for s, t and z",
        "Code and instructions", "Original materials"]
    assert tree.by_id("study-method").text() == "How it was made"
    # A fixed visible-text budget prevents implementation narration returning.
    assert len(text.replace(tree.by_id("study-source-pages").text(), "").split()) <= 550
    for term in ("Photos", "rectified", "isolated printed shapes", "font outlines",
                 "spacing metrics", "checked against the same samples", "not an independent test",
                 "EDUCAZIONE", "DUCAZION", "ministero educazione nazionale"):
        assert term in text
    for value in (rep["dice"], prep["dice"], prep["aggregate"]["traced_shapes"]["dice"]):
        assert "%.2f%%" % (100 * value) in text
    assert not list(study.iter("table"))
    assert not list(study.iter("pre"))
    for stale in ("build_font.py", "pytest", "SHA-256", "Result for each glyph", "Alignment found"):
        assert stale not in text
    assert not re.search(r"\b[a-f0-9]{64}\b", text)
    link = tree.by_id("study-source-repository")
    assert link.inside(study)
    if make_public.SOURCE_REPOSITORY_URL:
        assert link.tag == "a" and link.attrs["href"] == make_public.SOURCE_REPOSITORY_URL
    else:
        assert link.tag == "span" and "href" not in link.attrs
        assert link.attrs["data-placeholder"] == "SOURCE_REPOSITORY_URL"
    assert not [a for a in study.iter("a") if "cta" in a.classes()]


def test_source_repository_mapping_renders_a_link_when_configured(monkeypatch):
    # Deliberately synthetic test value, never written to the public artifact.
    url = "https://github.com/example/reproduction-test"
    monkeypatch.setattr(make_public, "SOURCE_REPOSITORY_URL", url)
    rendered = make_public.page(make_public.load(), PUBLIC / "downloads" / make_public.ZIP_NAME)
    link = Tree(rendered).by_id("study-source-repository")
    assert link.tag == "a" and link.attrs["href"] == url
    assert "publication pending" not in link.text()


def test_study_tab_shows_s_t_z_next_to_their_source(tree):
    _, prep = reports()
    study = tree.by_id("study")
    section = tree.by_id("study-stz")
    assert section.inside(study) and section.tag == "h2"
    for ch in "stz":
        proof = tree.by_id("study-proof-" + ch)
        assert proof.inside(study)
        assert tree.order.index(proof) > tree.order.index(section)
        assert next(proof.iter("h4")).text() == "Letter " + ch
        images = [i.attrs["src"] for i in proof.iter("img")]
        expected = prep["images"]["glyphs"][ch]
        assert images == ["evaluation/" + expected[k] for k in ("source", "reconstruction", "overlay")]
        for image in proof.iter("img"):
            assert image.attrs.get("alt") and (PUBLIC / image.attrs["src"]).is_file()
        captions = [c.text() for c in proof.iter("figcaption")]
        assert captions[0] == "Source" and captions[1] == "Font file" and captions[2].startswith("Difference")
        assert "Dice" not in proof.text() and "IoU" not in proof.text()
    assert "Two printed z shapes; the font uses the first" in tree.by_id("study-proof-z").text()
    assert "traced from the printed shapes, not constructed additions" in study.text()



# --------------------------------------------------------------------------
# release package
# --------------------------------------------------------------------------

def test_release_package_is_reproducible_and_complete(tmp_path):
    served = PUBLIC / "downloads" / make_public.ZIP_NAME
    assert make_public.RELEASE == "0.8" and make_public.ZIP_NAME == "balilla-type-lab-fonts-0.8.zip"
    one = make_public.build_zip(tmp_path / "one.zip")
    two = make_public.build_zip(tmp_path / "two.zip")
    assert sha(one) == sha(two) == sha(served), "the served package is stale or not reproducible"
    rep, prep = reports()
    with zipfile.ZipFile(served) as zf:
        assert zf.testzip() is None
        root = make_public.PACKAGE + "/"
        names = [n[len(root):] for n in zf.namelist()]
        assert all(n.startswith(root) for n in zf.namelist())
        assert names == [
            "README.txt", "LICENSE.txt",
            "Balilla-Reconstructed/Balilla-Reconstructed.ttf", "Balilla-Reconstructed/Balilla-Reconstructed.woff2",
            "Balilla-Reconstructed/NOTES.txt", "Balilla-Reconstructed/evaluation-report.json",
            "Balilla-Panel-Reconstructed/Balilla-Panel-Reconstructed.ttf",
            "Balilla-Panel-Reconstructed/Balilla-Panel-Reconstructed.woff2",
            "Balilla-Panel-Reconstructed/NOTES.txt", "Balilla-Panel-Reconstructed/evaluation-report.json",
            "Balilla-Panel-Reconstructed/evidence/panel-glyph-s-overlay.png",
            "Balilla-Panel-Reconstructed/evidence/panel-glyph-t-overlay.png",
            "Balilla-Panel-Reconstructed/evidence/panel-glyph-z-overlay.png",
            "SHA256SUMS.txt"]
        for name in FONTS:                                     # the package holds the current font files
            data = zf.read(root + name.rsplit(".", 1)[0] + "/" + name)
            assert hashlib.sha256(data).hexdigest() == sha(LAB / "fonts" / name), name
            if name.endswith(".ttf"):
                TTFont(io.BytesIO(data))                       # opens as a font
        for line in zf.read(root + "SHA256SUMS.txt").decode().splitlines():
            digest, member = line.split("  ", 1)
            assert hashlib.sha256(zf.read(root + member)).hexdigest() == digest, member
        assert json.loads(zf.read(root + "Balilla-Panel-Reconstructed/evaluation-report.json")) == prep
        for name in names:                                     # no photograph is in the package
            assert not name.lower().endswith((".jpg", ".jpeg")), name
        readme = zf.read(root + "README.txt").decode()
        notes_a = zf.read(root + "Balilla-Reconstructed/NOTES.txt").decode()
        notes_p = zf.read(root + "Balilla-Panel-Reconstructed/NOTES.txt").decode()
        licence = zf.read(root + "LICENSE.txt").decode()
    assert "Dice %.2f%%" % (100 * rep["dice"]) in readme and "Dice %.2f%%" % (100 * rep["dice"]) in notes_a
    agg = prep["aggregate"]
    for value in (prep["dice"], agg["traced_shapes"]["dice"], agg["other_occurrences"]["dice"]):
        assert "Dice %.2f%%" % (100 * value) in readme and "Dice %.2f%%" % (100 * value) in notes_p
    for ch, g in prep["glyphs"].items():                       # every traced glyph has its result in the notes
        assert "  %s: %d shape" % (ch, g["occurrences"]) in notes_p
        assert "Dice %.2f%%" % (100 * g["traced_shape"]["dice"]) in notes_p
    assert "A.caps" not in readme and rep["selected_block"]["description"] in notes_a
    assert prep["selected_sample"]["description"] in notes_p
    assert "THE SUPPLIED CLOSE PHOTO" in notes_p and "is not published" in notes_p
    assert "Do not confuse this sample with" in notes_p
    assert "CATALOGUE CHECK" in notes_a
    assert "Creative Commons Attribution 4.0 International" in licence
    assert "creativecommons.org/licenses/by/4.0" in licence and "release 0.8" in licence
    assert "not 100%" in notes_a and "not 100%" in notes_p
    assert "No score is 100%" in readme and "Two study reconstructions" in readme


def test_only_current_release_is_public():
    assert sorted(p.name for p in (PUBLIC / "downloads").iterdir()) == [make_public.ZIP_NAME]
    for version in ("0.3", "0.4", "0.5", "0.6"):
        assert not (PUBLIC / "downloads" / ("balilla-type-lab-fonts-%s.zip" % version)).exists()


# --------------------------------------------------------------------------
# audit of the served artifact
# --------------------------------------------------------------------------

def test_public_artifact_audit(page, tree):
    data = make_public.load()
    present = sorted(str(p.relative_to(PUBLIC)) for p in PUBLIC.rglob("*") if p.is_file())
    # the artifact holds exactly the files that the build lists
    assert present == make_public.expected_files(data)
    assert len(present) == 45
    assert not [p for p in PUBLIC.rglob("*") if p.is_dir() and p.name not in ("assets", "downloads", "evaluation", "fonts", "experiments", "source-pages")]
    kinds = {Path(p).suffix for p in present}
    assert kinds == {".html", ".ttf", ".woff2", ".jpg", ".png", ".json", ".zip"}
    assert not [p for p in present if Path(p).name.startswith(".")]
    # every local reference of the page exists, and the page links every font file
    refs = set(re.findall(r"""(?:src|href)=["']([^"'#]+)["']""", page))
    refs |= set(re.findall(r"""url\(['"]?([^'")]+)['"]?\)""", page))
    local = sorted(r for r in refs if not re.match(r"^(https?:|data:|mailto:)", r))
    assert local
    for ref in local:
        assert (PUBLIC / ref).is_file(), "missing file referenced by index.html: " + ref
    linked = {str((PUBLIC / r).resolve().relative_to(PUBLIC)) for r in local}
    assert linked == set(present) - {"index.html", "downloads/" + make_public.ZIP_NAME}
    for name in FONTS:
        assert 'href="./fonts/%s" download' % name in page, name
        assert sha(PUBLIC / "fonts" / name) == sha(LAB / "fonts" / name), name
    for rel in present:
        if rel.startswith("evaluation/"):
            assert sha(PUBLIC / rel) == sha(LAB / rel), rel
    # the page loads nothing from another site: no script file, no style sheet, no remote image or font
    assert not [n for n in tree.order if n.tag == "script" and "src" in n.attrs]
    assert not [n for n in tree.order if n.tag == "link"]
    for node in tree.order:
        if node.tag in ("img", "source", "video", "audio"):
            assert not re.match(r"^(https?:)?//", node.attrs.get("src", "")), node.attrs
    assert not re.search(r"url\(['\"]?(https?:)?//", page)
    external = sorted({a.attrs["href"] for a in tree.root.iter("a") if a.attrs.get("href", "").startswith("http")})
    expected_external = ["https://creativecommons.org/licenses/by/4.0/"]
    if make_public.SOURCE_REPOSITORY_URL:
        expected_external.append(make_public.SOURCE_REPOSITORY_URL)
    assert external == sorted(expected_external)
    # Existing evidence images plus the twelve explicitly authorized full inputs.
    photos = sorted(p for p in present if p.endswith(".jpg"))
    assert photos == ["assets/capitals-original.jpg", "evaluation/panel-glyph-s-source.jpg",
                      "evaluation/panel-glyph-t-source.jpg", "evaluation/panel-glyph-z-source.jpg",
                      "evaluation/panel-lines-source.jpg", "experiments/alphabet-source.jpg"] + sorted(
                          "source-pages/" + n for n in make_public.SOURCE_PAGES)
    source_hashes = {sha(p): p.name for p in (LAB / "assets").iterdir()}
    for rel in present:
        name = source_hashes.get(sha(PUBLIC / rel))
        assert (name is None or (rel == "assets/" + name and name in make_public.ASSETS)
                or (rel == "source-pages/" + name and name in make_public.SOURCE_PAGES)), rel
    full_sizes = set()
    for path in (LAB / "assets").iterdir():
        with Image.open(path) as im:
            if path.name not in make_public.ASSETS and path.name not in make_public.SOURCE_PAGES:
                full_sizes.add(im.size)
    for rel in present:                    # unpublished close-photo frame stays excluded
        if rel.endswith((".jpg", ".png")):
            with Image.open(PUBLIC / rel) as im:
                assert im.size not in full_sizes, rel
    # no secret and no private path in a text file
    for rel in present:
        if rel.endswith((".html", ".json")):
            text = (PUBLIC / rel).read_text()
            for private in ("/home/", ".hermes", "repo.box", "@gmail", "BEGIN PRIVATE KEY", "api_key", "password"):
                assert private not in text, (rel, private)
    assert "{{" not in page
    assert sum((PUBLIC / p).stat().st_size for p in present if not p.startswith("source-pages/")) < 6_000_000
    assert sum((PUBLIC / "source-pages" / n).stat().st_size for n in make_public.SOURCE_PAGES) == sum(
        p.stat().st_size for p in make_public.SOURCE_PAGES.values())


def test_readme_numbers_come_from_the_reports():
    text = (ROOT / "README.md").read_text()
    rep, prep = reports()
    agg = prep["aggregate"]
    values = [rep["dice"], rep["iou"]]
    values += [prep["dice"], prep["iou"], agg["traced_shapes"]["dice"], agg["traced_shapes"]["iou"],
               agg["other_occurrences"]["dice"], prep["gate"]["value"],
               prep["cross_check_supplied_close_photo"]["all_observed_shapes"]["dice"]]
    values += [prep["glyphs"][ch]["traced_shape"]["dice"] for ch in "stz"] + [prep["glyphs"]["z"]["lowest_dice"]]
    for value in values:
        assert "%.2f%%" % (100 * value) in text, value
    assert make_public.ZIP_NAME in text
    assert "No score is 100%" in text
    for label in ("Balilla — cover capitals",
                  "Balilla Panel — pale panel lettering", "ministero educazione nazionale", "Fonts", "Study",
                  "img_9eb5018c1e1c.jpg", "HXwNXsUWEAALJek.jpg"):
        assert label in text, label