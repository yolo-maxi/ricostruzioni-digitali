"""Read-only HTTPS artifact verification; run explicitly after publication."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

from test_site import Tree

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://ricostruzioni-digitali.repo.box/"


def fetch(path):
    request = urllib.request.Request(BASE + path, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=30) as response:
        assert response.status == 200
        return response.read()


def verify(path):
    relative = path.relative_to(ROOT / "public").as_posix()
    data = fetch(relative)
    assert data == path.read_bytes(), relative
    return {"path": relative, "status": 200, "sha256": hashlib.sha256(data).hexdigest()}


def main():
    paths = sorted(p for p in (ROOT / "public").rglob("*") if p.is_file())
    with ThreadPoolExecutor(max_workers=6) as pool:
        verified = list(pool.map(verify, paths))
    home = fetch("").decode()
    assert home == (ROOT / "public/index.html").read_text()
    tree = Tree(home)
    cards = [n for n in tree.by_id("fonts").iter("article") if "face" in n.classes()]
    assert len(cards) == 2
    assert all(len(list(card.iter("button"))) == 1 for card in cards)
    rail = tree.by_id("source-slides")
    images = list(rail.iter("img"))
    assert len(images) == 12 and all(n.attrs["loading"] == "lazy" for n in images)
    assert all(n.tag == "img" for n in rail.iter())
    assert [n.attrs["id"] for card in cards for n in card.iter("input")] == ["tester-a", "tester-p"]
    for retired in ("Download the fonts", "Original-materials ZIP", "contenteditable", "What’s in the download"):
        assert retired not in home
    missing = ["downloads/balilla-type-lab-original-materials.zip",
               "fonts/Balilla-Rounded-Reconstructed.ttf", "fonts/Balilla-Rounded-Reconstructed.woff2"]
    for path in missing:
        try:
            fetch(path)
        except urllib.error.HTTPError as error:
            assert error.code == 404, (path, error.code)
        else:
            raise AssertionError("Retired path is still served: " + path)
    receipt = {"target": BASE, "files_verified": len(verified), "artifacts": verified,
               "retired_404": missing, "face_cards": len(cards), "lazy_original_images": len(images),
               "browser_proof": False}
    (ROOT / "docs/live-verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"HTTPS 200 and byte equality: {len(verified)}/{len(paths)} artifacts; home matches; 2 cards; 12 lazy rail images; 3 retired paths return 404")


if __name__ == "__main__":
    main()
