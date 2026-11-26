"""Read-only preflight for publishing this Git history. Prints paths, never matches.

Run with Python from the repository root. Nonzero means publication must wait.
Historical non-public evidence is not silently removed or relicensed by this audit.
"""
import io
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "credential": rb"(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,}|sk-[A-Za-z0-9]{32,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)",
    "machine-local path": rb"/(?:home|Users)/[A-Za-z0-9_-]+/",
}


def scan(label, data, findings):
    for kind, pattern in PATTERNS.items():
        if re.search(pattern, data):
            findings.add((kind, label))
    if data.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in archive.namelist():
                if not name.endswith("/"):
                    scan(label + "!" + name, archive.read(name), findings)


def main():
    findings = set()
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for name in filter(None, files):
        path = ROOT / name
        if path.is_file():
            scan("working tree:" + name, path.read_bytes(), findings)
    # Scan all reachable blobs, including archives, before any public push.
    records = subprocess.check_output(["git", "rev-list", "--objects", "HEAD"], cwd=ROOT).decode().splitlines()
    for record in records:
        oid, _, name = record.partition(" ")
        if subprocess.check_output(["git", "cat-file", "-t", oid], cwd=ROOT).strip() != b"blob":
            continue
        scan("history:" + oid[:12] + ":" + name,
             subprocess.check_output(["git", "cat-file", "blob", oid], cwd=ROOT), findings)
    # The existing evidence contract explicitly excludes this additional close photo.
    close = "source/balilla-lab/assets/img_9eb5018c1e1c.jpg"
    if close in files:
        findings.add(("explicitly unpublished close-photo input", close))
    for kind, name in sorted(findings):
        print(kind + ": " + name)
    print("PUBLIC SOURCE PREFLIGHT: " + ("BLOCKED" if findings else "PASS"))
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
