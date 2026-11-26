"""The public hub publishes only explicitly selected evidence, never raw probes."""
import hashlib
import json
import string


from fontTools.ttLib import TTFont
from PIL import Image
from test_site import Tree, ROOT, PUBLIC, make_public
from test_public_release import FONT_SHA

EXPECTED = {
    'blackletter-source.png', 'blackletter-proof.png',
    'alphabet-source.jpg', 'alphabet-contact.png',
    'cursive-source.png', 'cursive-proof.png',
    'Alphabet-Sheet-EXPERIMENTAL-Observed-Only.ttf',
    'Alphabet-Sheet-EXPERIMENTAL-Observed-Only.woff2',
}


def test_exact_public_experiment_allowlist_and_source_bytes():
    assert set(make_public.EXPERIMENT_FILES) == EXPECTED
    assert {p.name for p in (PUBLIC / 'experiments').iterdir()} == EXPECTED
    for name, source in make_public.EXPERIMENT_FILES.items():
        published = PUBLIC / 'experiments' / name
        assert published.read_bytes() == (ROOT / 'experiments' / source).read_bytes()
        if published.suffix in ('.png', '.jpg'):
            with Image.open(published) as image:
                image.verify()


def test_three_distinct_truthful_cards_and_only_real_downloads():
    tree = Tree((PUBLIC / 'index.html').read_text())
    panel = tree.by_id('experiments')
    cards = list(panel.iter('article'))
    assert [c.attrs['id'] for c in cards] == [
        'experiment-blackletter', 'experiment-alphabet', 'experiment-cursive']
    for card, images in zip(cards, [
        ['blackletter-source.png', 'blackletter-proof.png'],
        ['alphabet-source.jpg', 'alphabet-contact.png'],
        ['cursive-source.png', 'cursive-proof.png'],
    ]):
        assert [i.attrs['src'] for i in card.iter('img')] == ['experiments/' + p for p in images]
        assert all(i.attrs.get('alt') for i in card.iter('img'))
    black, alphabet, cursive = [c.text() for c in cards]
    for phrase in ('No font', 'Only o and l', 'diagnostic observed-outline candidates',
                   'w and h were rejected', 'decorative initial is excluded'):
        assert phrase in black
    for phrase in ('Experimental / observed-only / 63 characters (A–Z, a–z, 0–9, &)',
                   'No missing characters were invented', 'not production-quality or historical verification',
                   'not recovered historical spacing'):
        assert phrase in alphabet
    for phrase in ('No font', 'zero complete glyphs accepted', 'Connected strokes',
                   'hairlines', 'without intervention', 'blackletter heading is excluded'):
        assert phrase in cursive
    assert not list(cards[0].iter('a')) and not list(cards[2].iter('a'))
    links = list(cards[1].iter('a'))
    assert len(links) == 2
    assert {a.attrs['href'] for a in links} == {
        'experiments/Alphabet-Sheet-EXPERIMENTAL-Observed-Only.' + ext for ext in ('ttf', 'woff2')}
    assert all('download' in a.attrs for a in links)


def test_experimental_font_exact_coverage_and_pinned_hashes():
    hashes = json.loads((ROOT / 'experiments/alphabet-sheet-probe/output/report.json').read_text())
    for ext in ('ttf', 'woff2'):
        name = 'Alphabet-Sheet-EXPERIMENTAL-Observed-Only.' + ext
        path = PUBLIC / 'experiments' / name
        with TTFont(path) as font:
            assert set(font.getBestCmap()) == set(map(ord, string.ascii_letters + string.digits + '&'))
            assert len(font.getBestCmap()) == 63
        assert hashlib.sha256(path.read_bytes()).hexdigest() == hashes['artifacts']['fonts/' + name]


def test_active_font_bytes_match_requested_base():
    for name in make_public.FONT_FILES:
        rel = 'source/balilla-lab/fonts/' + name
        # Pinned base digests keep source-archive reproductions independent of Git history.
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == FONT_SHA[name]
        assert (ROOT / rel).read_bytes() == (PUBLIC / 'fonts' / name).read_bytes()


def test_regeneration_removes_unapproved_probe_outputs(tmp_path, monkeypatch):
    output = tmp_path / 'public'
    raw = output / 'experiments' / 'glyphs' / 'raw-mask.png'
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b'not approved')
    monkeypatch.setattr(make_public, 'PUBLIC', output)
    make_public.main()
    assert not raw.exists()
    assert sorted(str(p.relative_to(output)) for p in output.rglob('*') if p.is_file()) == make_public.expected_files(make_public.load())
