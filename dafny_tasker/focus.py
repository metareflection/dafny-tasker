from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import re
import uuid

from .constants import CODE_HERE_MARKER
from .lsp_outline import document_symbols
from .lsp_def import goto_definition, header_contains_lemma

ASSERT_RE = re.compile(r'^\s*assert\b.*;\s*$')
CALL_RE   = re.compile(r'^\s*(?P<callee>[A-Za-z_]\w*)\s*\(.*\)\s*;\s*$')

@dataclass
class Site:
    line_idx: int  # 0-based
    kind: str      # 'assert' | 'lemma-call'
    original: str

def _brace_body_bounds(lines: List[str], start_line: int, end_line: int) -> Optional[Tuple[int,int]]:
    n=len(lines); brace_open=-1
    for j in range(start_line, min(end_line+1,n)):
        if '{' in lines[j]: brace_open=j; break
    if brace_open==-1: return None
    depth=0
    for k in range(brace_open, min(end_line+1,n)):
        depth += lines[k].count('{'); depth -= lines[k].count('}')
        if depth==0: return (brace_open,k)
    return None

def _header_kind_name(lines: List[str], sl: int) -> Tuple[str,str]:
    hdr  = lines[sl].strip() if sl < len(lines) else ""
    hdr2 = lines[sl+1].strip() if sl+1 < len(lines) else ""
    m = re.search(r'\b(lemma|method)\s+([A-Za-z_]\w*)', f"{hdr} {hdr2}")
    return (m.group(1), m.group(2)) if m else ("","")

def _find_target_lemma_range(path: Path, lemma_name: str, lines: List[str]) -> Optional[Tuple[int,int,int,int]]:
    for s in document_symbols(path):
        rng = s.get("range") or {}
        start=rng.get("start") or {}; end=rng.get("end") or {}
        sl=int(start.get("line",-1)); el=int(end.get("line",-1))
        if sl<0 or el<0: continue
        kind, nm = _header_kind_name(lines, sl)
        if kind=="lemma" and s.get("name")==lemma_name:
            body=_brace_body_bounds(lines, sl, el)
            if body: return (sl, el, body[0], body[1])
    return None

def _enumerate_sites(path: Path, lines: List[str], bstart: int, bend: int) -> List[Site]:
    out: List[Site]=[]
    for i in range(bstart, bend+1):
        ln=lines[i]
        if ASSERT_RE.match(ln):
            out.append(Site(i,"assert",ln)); continue
        mc = CALL_RE.match(ln)
        if not mc: continue
        callee = mc.group("callee")
        col = ln.find(callee)
        if col<0: continue
        got = goto_definition(path, i, col)
        if not got: continue
        def_file, def_line0, _ = got
        if header_contains_lemma(def_file, def_line0):
            out.append(Site(i,"lemma-call",ln))
    return out

def _mask_whole_statement(line: str) -> str:
    indent_len = len(line) - len(line.lstrip())
    indent = line[:indent_len]
    trailing = ";" if line.rstrip().endswith(";") else ""
    return f"{indent}{CODE_HERE_MARKER}{trailing}"

def _inject_axiom_in_header(header: str) -> str:
    h = re.sub(r'\s+', ' ', header.strip())
    if '{' in h: h = h.split('{',1)[0].rstrip()
    m = re.search(r'\blemma\s*\{:\s*([^}]*)\}', h)
    if m:
        attrs = m.group(1).strip()
        parts = [a.strip() for a in re.split(r'\s*,\s*', attrs)] if attrs else []
        if 'axiom' not in parts:
            parts = ['axiom'] + [p for p in parts if p]
        new_attr = '{:' + ', '.join(parts) + '}'
        h = re.sub(r'\blemma\s*\{:\s*[^}]*\}', 'lemma ' + new_attr, h, count=1)
    else:
        h = re.sub(r'\blemma\b', 'lemma {:axiom}', h, count=1)
    return h

def _axiomatize_other_lemmas(path: Path, lines: List[str], target_body: Tuple[int,int]) -> List[str]:
    syms = document_symbols(path)
    out = lines[:]
    tgt_start, tgt_end = target_body
    edits = []
    for s in syms:
        rng=s.get("range") or {}; start=rng.get("start") or {}; end=rng.get("end") or {}
        sl=int(start.get("line",-1)); el=int(end.get("line",-1))
        if sl<0 or el<0: continue
        kind,_nm = _header_kind_name(lines, sl)
        if kind!="lemma": continue
        body = _brace_body_bounds(lines, sl, el)
        if not body: continue
        bs, be = body
        if not (be < tgt_start or bs > tgt_end):  # skip target
            continue
        header_text = " ".join([ln.strip() for ln in lines[sl:bs+1]])
        new_header = _inject_axiom_in_header(header_text)
        edits.append((sl, be, new_header))
    for sl, be, new_header in sorted(edits, key=lambda t: t[0], reverse=True):
        out[sl:be+1] = [new_header]
    return out

def build_focus_tasks(path: Path, lemma_name: str, modular: bool = False) -> List[Dict[str,Any]]:
    """Build tasks for a lemma. If modular=True, we first axiomatize other lemmas
    into a *temporary* Dafny file, then run the LSP on that edited program. This way,
    all ranges and line indices come from the edited program, avoiding any index mapping.
    """
    text = path.read_text(encoding="utf-8"); lines = text.splitlines()
    # We'll decide which path and which lines to use for LSP and masking
    path_for_lsp = path
    lines_for_lsp = lines
    tmp_path: Path | None = None
    try:
        if modular:
            # Find the target lemma range on the original text first (to know its body span).
            span0 = _find_target_lemma_range(path, lemma_name, lines)
            if not span0:
                return []
            _sl0, _el0, bstart0, bend0 = span0
            # Produce the modularized text by axiomatizing all other lemmas.
            mod_lines = _axiomatize_other_lemmas(path, lines, (bstart0, bend0))
            # Write to a temp file in the same directory so relative imports etc. still work.
            tmp_path = path.parent / f"{path.stem}.modular.{uuid.uuid4().hex[:8]}.dfy"
            tmp_path.write_text("\n".join(mod_lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
            path_for_lsp = tmp_path
            lines_for_lsp = mod_lines

        # Now (re)discover the target span and sites on the file/content the LSP will see.
        span = _find_target_lemma_range(path_for_lsp, lemma_name, lines_for_lsp)
        if not span:
            return []
        _sl, _el, bstart, bend = span
        sites = _enumerate_sites(path_for_lsp, lines_for_lsp, bstart, bend)

        # Build tasks by masking lines in the same buffer (original or modularized) that the LSP used.
        tasks: List[Dict[str,Any]] = []
        for idx, site in enumerate(sites):
            new_lines = lines_for_lsp[:]
            new_lines[site.line_idx] = _mask_whole_statement(new_lines[site.line_idx])
            program = "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")
            tasks.append({
                "id": f"{path.stem}_{lemma_name}_{idx}",
                "type": "call" if site.kind=="lemma-call" else "assert",
                "program": program,
                "output": site.original.strip()
            })
        return tasks
    finally:
        # Clean up the temp file, if any.
        if tmp_path and tmp_path.exists():
            try: tmp_path.unlink()
            except Exception: pass


def axiomatize_lemmas(input_path: Path, target_lemma: str, output_path: Path) -> bool:
    """Axiomatize all lemmas except the target lemma and write to output file.

    Args:
        input_path: Path to the input Dafny file
        target_lemma: Name of the lemma to keep (all others will be axiomatized)
        output_path: Path where the transformed file will be written

    Returns:
        True if successful, False otherwise
    """
    text = input_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find the target lemma range
    span = _find_target_lemma_range(input_path, target_lemma, lines)
    if not span:
        return False

    _sl, _el, bstart, bend = span

    # Axiomatize all other lemmas
    mod_lines = _axiomatize_other_lemmas(input_path, lines, (bstart, bend))

    # Write to output file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_text = "\n".join(mod_lines) + ("\n" if text.endswith("\n") else "")
    output_path.write_text(output_text, encoding="utf-8")

    return True


def list_lemmas(path: Path) -> list[str]:
    """Return lemma names in file via LSP document symbols."""
    names: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for s in document_symbols(path):
        rng = s.get("range") or {}
        start = rng.get("start") or {}
        sl = int(start.get("line", -1))
        if sl < 0:
            continue
        kind, nm = _header_kind_name(lines, sl)
        if kind == "lemma" and isinstance(s.get("name"), str):
            names.append(s.get("name"))
    return names


def find_lemma_containing_marker(path: Path) -> Optional[str]:
    """Find the lemma that contains the CODE_HERE_MARKER.
    
    Args:
        path: Path to the Dafny file
        
    Returns:
        Name of the lemma containing the marker, or None if not found
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    
    # Find the line with CODE_HERE_MARKER
    marker_line = -1
    for i, line in enumerate(lines):
        if CODE_HERE_MARKER in line:
            marker_line = i
            break
    
    if marker_line == -1:
        return None
    
    # Find which lemma contains this line
    for s in document_symbols(path):
        rng = s.get("range") or {}
        start = rng.get("start") or {}
        end = rng.get("end") or {}
        sl = int(start.get("line", -1))
        el = int(end.get("line", -1))
        if sl < 0 or el < 0:
            continue
        
        kind, nm = _header_kind_name(lines, sl)
        if kind == "lemma" and isinstance(s.get("name"), str):
            # Check if marker_line is within this lemma's body
            body = _brace_body_bounds(lines, sl, el)
            if body:
                bstart, bend = body
                if bstart <= marker_line <= bend:
                    return s.get("name")
    
    return None
