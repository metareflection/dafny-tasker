from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple
import urllib.parse

from .lsp import LspClient

def _uri(p: Path) -> str:
    return "file://" + urllib.parse.quote(str(p.resolve()))

def goto_definition(file: Path, line0: int, char0: int, *, timeout: float = 5.0) -> Optional[Tuple[Path,int,int]]:
    text = file.read_text(encoding="utf-8")
    cli = LspClient()
    try:
        uri = _uri(file)
        cli.initialize(_uri(file.parent)); cli.initialized()
        cli.notify("textDocument/didOpen", {
            "textDocument": {"uri": uri, "languageId": "dafny", "version": 1, "text": text}
        })
        res = cli.request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": line0, "character": char0}
        }, timeout=timeout)
        locs = res if isinstance(res, list) else ([res] if isinstance(res, dict) else [])
        if not locs: return None
        loc = locs[0]
        rng = loc.get("targetRange") or loc.get("range") or {}
        start = rng.get("start") or {}
        uri_out = loc.get("targetUri") or loc.get("uri")
        if not uri_out: return None
        def_path = Path(urllib.parse.urlparse(uri_out).path)
        return def_path, int(start.get("line", 0)), int(start.get("character", 0))
    finally:
        cli.shutdown()

def header_contains_lemma(def_file: Path, def_line0: int) -> bool:
    lines = def_file.read_text(encoding="utf-8").splitlines()
    hdr  = lines[def_line0].strip() if def_line0 < len(lines) else ""
    hdr2 = lines[def_line0+1].strip() if def_line0+1 < len(lines) else ""
    toks = (hdr + " " + hdr2).replace("(", " ").replace("{", " ").split()
    return "lemma" in toks
