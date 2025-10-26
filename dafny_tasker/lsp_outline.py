from __future__ import annotations
from pathlib import Path
from typing import Any, List, Dict
import urllib.parse

from .lsp import LspClient

def _uri(p: Path) -> str:
    return "file://" + urllib.parse.quote(str(p.resolve()))

def document_symbols(path: Path, *, timeout: float = 5.0) -> List[Dict]:
    text = path.read_text(encoding="utf-8")
    cli = LspClient()
    try:
        uri = _uri(path)
        cli.initialize(_uri(path.parent)); cli.initialized()
        cli.notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "dafny", "version": 1, "text": text}})
        res = cli.request("textDocument/documentSymbol", {"textDocument":{"uri":uri}}, timeout=timeout)
        flat: List[Dict] = []
        def visit(node: Any) -> None:
            if isinstance(node, dict):
                flat.append({
                    "name": node.get("name"),
                    "kind": node.get("kind"),
                    "range": node.get("range") or (node.get("location") or {}).get("range")
                })
                for ch in node.get("children") or []:
                    visit(ch)
        if isinstance(res, list):
            for s in res: visit(s)
        return flat
    finally:
        cli.shutdown()
