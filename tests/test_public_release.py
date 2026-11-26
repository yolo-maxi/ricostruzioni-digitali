"""Release 0.7: two frozen faces, exact originals and clean regeneration."""
import hashlib
import re
import zipfile
from pathlib import Path

from test_site import Tree

from test_site import FONTS, LAB, PUBLIC, ROOT, make_public


# Active font bytes at dd33a44, before the public-scope correction.
FONT_SHA = {

    "Balilla-Reconstructed.ttf": "7bf270f3f6cd60609258abeab8673ec586a58a1dc063fed7120c2e625a2c97d5",
    "Balilla-Reconstructed.woff2": "074358fe1ff94c4bd87496a99bf7e3b2cd0a40274917d9afb65f35c730f7f605",
    "Balilla-Panel-Reconstructed.ttf": "22d9f0c4e3a3f87354df7ef5c32fff4a8ba8b13a012da74d3fc91a46a138c756",
    "Balilla-Panel-Reconstructed.woff2": "27ac023b1f3735baf3187359317e4e8e94ac0b8caec8c24e3a08ce329fbc2388",
}


def test_active_font_bytes_and_explicit_loading_are_preserved():
    assert set(make_public.FONT_FILES) == set(FONTS) == set(FONT_SHA)
    assert sorted(p.name for p in (PUBLIC / "fonts").iterdir()) == sorted(FONTS)
    for name, digest in FONT_SHA.items():
        for folder in (LAB / "fonts", PUBLIC / "fonts"):
            assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest
    page = (PUBLIC / "index.html").read_text()
    rules = re.findall(r"@font-face\{([^}]+)\}", page)
    assert len(rules) == 2
    for rule, family, stem in zip(rules, ("BalillaCoverFace", "BalillaPanelFace"),
                                  (make_public.CAPITALS, make_public.PANEL)):
        for expected in ("font-family:" + family, "font-weight:400", "font-style:normal",
                         "font-display:block", stem + ".woff2", stem + ".ttf"):
            assert expected in rule
    assert "font-synthesis:none" in page


def test_exactly_two_faces_and_four_fonts_in_current_release():
    page = (PUBLIC / "index.html").read_text()
    tree = Tree(page)
    assert [n.attrs["id"] for n in tree.root.iter("article") if "face" in n.classes()] == [
        "face-capitals", "face-panel"]
    assert [n.attrs["id"] for n in tree.root.iter("input")] == ["tester-a", "tester-p"]
    assert not [n for n in tree.order if "contenteditable" in n.attrs]
    for name in FONTS:
        assert 'href="./fonts/%s" download' % name in page
    assert make_public.ORIGINALS_NAME not in page
    with zipfile.ZipFile(PUBLIC / "downloads" / make_public.ZIP_NAME) as archive:
        fonts = []
        for name in archive.namelist():
            if name.endswith((".ttf", ".woff2")):
                fonts.append(name.rsplit("/", 1)[-1])
        assert sorted(fonts) == sorted(FONTS)
        for name in fonts:
            member = make_public.PACKAGE + "/" + name.rsplit(".", 1)[0] + "/" + name
            assert hashlib.sha256(archive.read(member)).hexdigest() == FONT_SHA[name]


def test_withdrawn_face_is_absent_from_public_tree_and_active_archive():
    for path in PUBLIC.rglob("*"):
        assert "rounded" not in str(path.relative_to(PUBLIC)).lower()
        if path.suffix in (".html", ".json", ".txt", ".css", ".js"):
            assert b"rounded" not in path.read_bytes().lower(), path
    # The immutable supplied originals are provenance, not an active font release.
    with zipfile.ZipFile(PUBLIC / "downloads" / make_public.ZIP_NAME) as archive:
        for name in archive.namelist():
            assert "rounded" not in name.lower()
            if Path(name).suffix in (".txt", ".json", ".html"):
                assert b"rounded" not in archive.read(name).lower(), name


def test_original_materials_are_preserved_but_not_served():
    assert not make_public.ORIGINALS.exists()
    assert not (PUBLIC / "downloads" / make_public.ORIGINALS_NAME).exists()


def test_study_documents_evidence_boundary():
    tree = Tree((PUBLIC / "index.html").read_text())
    study = tree.by_id("study").text()
    for statement in ("Only observed printed glyphs are source evidence",
                      "Missing glyphs are marked as additions, not historical evidence",
                      "Each face uses its own printed sample", "one representative shape",
                      "Handwriting is excluded", "not complete historical alphabets",
                      "not spacing or additions", "not granted a licence",
                      "not historical source materials"):
        assert statement in study
    assert tree.by_id("study-originals").inside(tree.by_id("study"))
    disclosure = tree.by_id("study-withheld")
    assert disclosure.inside(tree.by_id("study"))
    assert "did not support a source-faithful full alphabet" in disclosure.text()


def test_public_text_and_archives_do_not_expose_private_data():
    patterns = (rb"/(?:home|Users|var/lib|opt)/", rb"[A-Z]:\\\\Users\\\\", rb"\.hermes",
                rb"BEGIN [A-Z ]*PRIVATE KEY", rb"(?:api_key|password|secret_key)\s*[:=]",
                rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

    def check(name, data):
        for pattern in patterns:
            assert not re.search(pattern, data, re.I), (name, pattern)

    for path in PUBLIC.rglob("*"):
        if path.suffix in (".html", ".json", ".txt", ".py", ".md"):
            check(path.name, path.read_bytes())
        elif path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    assert not name.startswith("/") and ".." not in Path(name).parts
                    if Path(name).suffix in (".html", ".json", ".txt", ".py", ".md"):
                        check(name, archive.read(name))


def test_generator_removes_stale_artifacts_and_is_reproducible(tmp_path, monkeypatch):
    output = tmp_path / "public"
    # Seed an old publication, including both obsolete archives and retired assets.
    for name in ("downloads/balilla-type-lab-fonts-0.3.zip",
                 "downloads/balilla-type-lab-original-materials.zip",
                 "downloads/balilla-type-lab-fonts-0.6.zip",
                 "downloads/balilla-type-lab-fonts-0.5.zip",
                 "downloads/balilla-type-lab-fonts-0.4.zip",
                 "fonts/Balilla-Rounded-Reconstructed.ttf",
                 "fonts/Balilla-Rounded-Reconstructed.woff2",
                 "evaluation/rounded-report.json", "evaluation/rounded-opera-overlay.png"):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"obsolete publication")
    monkeypatch.setattr(make_public, "PUBLIC", output)
    make_public.main()
    expected = make_public.expected_files(make_public.load())
    assert sorted(str(p.relative_to(output)) for p in output.rglob("*") if p.is_file()) == expected
    for name in expected:
        assert (output / name).read_bytes() == (PUBLIC / name).read_bytes(), name
    make_public.main()
    for name in expected:
        assert (output / name).read_bytes() == (PUBLIC / name).read_bytes(), name
