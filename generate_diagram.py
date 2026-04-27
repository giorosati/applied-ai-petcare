"""Fetch a PNG rendering of system_diagram.mmd and save it to assets/."""
import base64
import pathlib
import urllib.request
import zlib

MMD_FILE = pathlib.Path(__file__).parent / "system_diagram.mmd"
OUT_FILE = pathlib.Path(__file__).parent / "assets" / "system_diagram.png"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; diagram-generator/1.0)"}


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def via_mermaid_ink(source: str) -> bytes:
    encoded = base64.urlsafe_b64encode(source.encode("utf-8")).decode("ascii")
    url = f"https://mermaid.ink/img/{encoded}?bgColor=white"
    print(f"  Trying mermaid.ink …")
    return _fetch(url)


def via_kroki(source: str) -> bytes:
    """kroki.io renders Mermaid to PNG without auth."""
    compressed = zlib.compress(source.encode("utf-8"), 9)
    encoded = base64.urlsafe_b64encode(compressed).decode("ascii")
    url = f"https://kroki.io/mermaid/png/{encoded}"
    print(f"  Trying kroki.io …")
    return _fetch(url)


def main() -> None:
    source = MMD_FILE.read_text(encoding="utf-8")
    png_bytes: bytes | None = None

    for renderer in (via_mermaid_ink, via_kroki):
        try:
            png_bytes = renderer(source)
            break
        except Exception as exc:
            print(f"  Failed: {exc}")

    if not png_bytes:
        raise RuntimeError("All rendering services failed. Check your internet connection.")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_bytes(png_bytes)
    print(f"Saved {len(png_bytes):,} bytes to {OUT_FILE}")


if __name__ == "__main__":
    main()
