from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import re
import uuid

from .constants import CODE_HERE_MARKER, SKETCH_HERE_MARKER
from .lsp_outline import document_symbols
from .lsp_def import goto_definition, header_contains_lemma

ASSERT_RE = re.compile(r'^\s*(?:.*\{\s*)?assert\b.*;\s*(?://.*)?$')
CALL_RE   = re.compile(r'^\s*(?:.*\{\s*)?(?P<callee>[A-Za-z_]\w*)\s*\(.*\)\s*;\s*(?://.*)?$')
CALC_RE   = re.compile(r'^\s*calc\s*(==|>=|<=|>|<)?\s*\{')
FORALL_RE = re.compile(r'^\s*forall\s+')

@dataclass
class Site:
    line_idx: int      # 0-based start line
    end_idx: int       # 0-based end line (same as line_idx for single-line statements)
    kind: str          # 'assert' | 'lemma-call' | 'calc' | 'forall'
    original: str      # Full text of the statement/block

def _brace_body_bounds(lines: List[str], start_line: int, end_line: int) -> Optional[Tuple[int,int]]:
    """Find the brace-delimited body of a lemma/method.

    Returns (start_line, end_line) of the body, or None if no body found.
    A body starts when we see more opening braces than closing braces on a line.
    """
    n=len(lines); brace_open=-1
    for j in range(start_line, min(end_line+1,n)):
        open_count = lines[j].count('{')
        close_count = lines[j].count('}')
        if open_count > close_count:
            brace_open=j
            break
    if brace_open==-1: return None

    # Find where the body closes
    depth=0
    for k in range(brace_open, min(end_line+1,n)):
        depth += lines[k].count('{')
        depth -= lines[k].count('}')
        if depth==0: return (brace_open,k)
    return None

def _find_brace_balanced_block(lines: List[str], start_idx: int) -> Optional[Tuple[int, str]]:
    """Find a brace-balanced block starting from start_idx.

    Args:
        lines: List of lines
        start_idx: Starting line index (0-based) that should contain an opening brace

    Returns:
        Tuple of (end_idx, full_text) or None if not found
    """
    if start_idx >= len(lines):
        return None

    # Find opening brace on the start line
    if '{' not in lines[start_idx]:
        return None

    depth = 0
    for i in range(start_idx, len(lines)):
        depth += lines[i].count('{')
        depth -= lines[i].count('}')
        if depth == 0:
            # Found the closing brace
            full_text = "\n".join(lines[start_idx:i+1])
            return (i, full_text)

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

def _enumerate_sites(path: Path, lines: List[str], bstart: int, bend: int, extract_types: set[str] = None) -> List[Site]:
    """Enumerate sites (statements to extract) in a lemma body.

    Args:
        path: Path to the Dafny file
        lines: List of lines in the file
        bstart: Start line of lemma body (0-based)
        bend: End line of lemma body (0-based)
        extract_types: Set of types to extract ('assert', 'lemma-call', 'calc', 'forall')
                      If None, defaults to {'assert', 'lemma-call'}

    Returns:
        List of Site objects
    """
    if extract_types is None:
        extract_types = {'assert', 'lemma-call'}

    out: List[Site] = []
    i = bstart
    while i <= bend:
        ln = lines[i]

        # Check for assert statements
        if 'assert' in extract_types and ASSERT_RE.match(ln):
            out.append(Site(i, i, "assert", ln))
            i += 1
            continue

        # Check for calc statements
        if 'calc' in extract_types and CALC_RE.match(ln):
            block = _find_brace_balanced_block(lines, i)
            if block:
                end_idx, full_text = block
                out.append(Site(i, end_idx, "calc", full_text))
                i = end_idx + 1
                continue

        # Check for forall statements (not predicates - must have braces)
        if 'forall' in extract_types and FORALL_RE.match(ln):
            # Find the line with the opening brace (might be on a later line)
            brace_line = None
            for j in range(i, min(i + 5, len(lines))):  # Look up to 5 lines ahead
                if '{' in lines[j]:
                    brace_line = j
                    break
                # Stop if we hit a semicolon (it's a predicate, not a statement)
                if ';' in lines[j]:
                    break

            if brace_line is not None:
                block = _find_brace_balanced_block(lines, brace_line)
                if block:
                    end_idx, _ = block
                    # Get full text from forall start to closing brace
                    full_text = "\n".join(lines[i:end_idx+1])
                    out.append(Site(i, end_idx, "forall", full_text))
                    i = end_idx + 1
                    continue

        # Check for lemma calls
        if 'lemma-call' in extract_types:
            mc = CALL_RE.match(ln)
            if mc:
                callee = mc.group("callee")
                col = ln.find(callee)
                if col >= 0:
                    got = goto_definition(path, i, col)
                    if got:
                        def_file, def_line0, _ = got
                        if header_contains_lemma(def_file, def_line0):
                            out.append(Site(i, i, "lemma-call", ln))

        i += 1

    return out

def _mask_whole_statement(line: str) -> str:
    indent_len = len(line) - len(line.lstrip())
    indent = line[:indent_len]
    return f"{indent}{CODE_HERE_MARKER}"

def _mask_statement_block(lines: List[str], start_idx: int, end_idx: int) -> List[str]:
    """Mask a multi-line statement block with CODE_HERE marker.

    Args:
        lines: List of all lines
        start_idx: Starting line index (0-based) to mask
        end_idx: Ending line index (0-based) to mask

    Returns:
        New list of lines with the block replaced by CODE_HERE
    """
    new_lines = lines[:]
    if start_idx == end_idx:
        # Single line - use existing function
        new_lines[start_idx] = _mask_whole_statement(new_lines[start_idx])
    else:
        # Multi-line block - replace with single CODE_HERE line
        first_line = lines[start_idx]
        indent_len = len(first_line) - len(first_line.lstrip())
        indent = first_line[:indent_len]
        # Replace entire block with one line
        new_lines[start_idx:end_idx+1] = [f"{indent}{CODE_HERE_MARKER}"]
    return new_lines

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

def build_sketch_task(path: Path, lemma_name: str, modular: bool = False, extract_types: set[str] = None) -> Optional[Dict[str,Any]]:
    """Build a sketch task for a lemma by removing all extractable statements.

    Args:
        path: Path to the Dafny file
        lemma_name: Name of the lemma to sketch
        modular: If True, axiomatize other lemmas
        extract_types: Set of types to extract ('assert', 'lemma-call', 'calc', 'forall')
                      If None, defaults to {'assert', 'lemma-call'}

    Returns:
        A single task dictionary with the sketch as program (statements removed)
        and full lemma body as output, or None if lemma not found
    """
    if extract_types is None:
        extract_types = {'assert', 'lemma-call'}

    text = path.read_text(encoding="utf-8"); lines = text.splitlines()
    path_for_lsp = path
    lines_for_lsp = lines
    tmp_path: Path | None = None
    try:
        if modular:
            span0 = _find_target_lemma_range(path, lemma_name, lines)
            if not span0:
                return None
            _sl0, _el0, bstart0, bend0 = span0
            mod_lines = _axiomatize_other_lemmas(path, lines, (bstart0, bend0))
            tmp_path = path.parent / f"{path.stem}.modular.{uuid.uuid4().hex[:8]}.dfy"
            tmp_path.write_text("\n".join(mod_lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
            path_for_lsp = tmp_path
            lines_for_lsp = mod_lines

        span = _find_target_lemma_range(path_for_lsp, lemma_name, lines_for_lsp)
        if not span:
            return None
        sl, el, bstart, bend = span
        sites = _enumerate_sites(path_for_lsp, lines_for_lsp, bstart, bend, extract_types)

        if not sites:
            # No sites to mask - return None (or could return lemma unchanged)
            return None

        # First, create the output (sketched body with statements removed)
        # Track how many lines we've deleted before the body end
        lines_deleted_before_bend = 0

        # Remove all sites in reverse order (to avoid offset issues)
        # Simply delete the lines for each site
        new_lines = lines_for_lsp[:]
        for site in sorted(sites, key=lambda s: s.line_idx, reverse=True):
            # Count lines deleted that would affect bend
            num_deleted = site.end_idx - site.line_idx + 1
            if site.line_idx <= bend:
                lines_deleted_before_bend += num_deleted
            # Delete lines from start_idx to end_idx inclusive
            del new_lines[site.line_idx:site.end_idx+1]

        # Adjust bend for deleted lines
        new_bend = bend - lines_deleted_before_bend

        # Extract the sketched lemma body as output (from new_lines after deletions)
        # Don't include the outer braces - just the body content
        lemma_body_lines = new_lines[bstart+1:new_bend]
        output = "\n".join(lemma_body_lines)

        # Now create the program: replace entire lemma body with just SKETCH_HERE marker
        program_lines = lines_for_lsp[:]
        # Delete the entire body content (keep only opening and closing braces)
        # Delete everything between bstart+1 and bend (exclusive of braces)
        if bend > bstart:
            del program_lines[bstart+1:bend]

        # Insert SKETCH_HERE marker after opening brace
        indent = program_lines[bstart + 1][:len(program_lines[bstart + 1]) - len(program_lines[bstart + 1].lstrip())] if bstart + 1 < len(program_lines) else "  "
        sketch_marker = f"{indent}{SKETCH_HERE_MARKER}"
        program_lines.insert(bstart + 1, sketch_marker)

        program = "\n".join(program_lines) + ("\n" if text.endswith("\n") else "")

        return {
            "id": f"{path.stem}_{lemma_name}_sketch",
            "type": "sketch",
            "program": program,
            "output": output
        }
    finally:
        if tmp_path and tmp_path.exists():
            try: tmp_path.unlink()
            except Exception: pass


def build_focus_tasks(path: Path, lemma_name: str, modular: bool = False, extract_types: set[str] = None) -> List[Dict[str,Any]]:
    """Build tasks for a lemma. If modular=True, we first axiomatize other lemmas
    into a *temporary* Dafny file, then run the LSP on that edited program. This way,
    all ranges and line indices come from the edited program, avoiding any index mapping.

    Args:
        path: Path to the Dafny file
        lemma_name: Name of the lemma to focus on
        modular: If True, axiomatize other lemmas
        extract_types: Set of types to extract ('assert', 'lemma-call', 'calc', 'forall')
                      If None, defaults to {'assert', 'lemma-call'}

    Returns:
        List of task dictionaries
    """
    if extract_types is None:
        extract_types = {'assert', 'lemma-call'}

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
        sites = _enumerate_sites(path_for_lsp, lines_for_lsp, bstart, bend, extract_types)

        # Build tasks by masking lines in the same buffer (original or modularized) that the LSP used.
        tasks: List[Dict[str,Any]] = []
        for idx, site in enumerate(sites):
            new_lines = _mask_statement_block(lines_for_lsp, site.line_idx, site.end_idx)
            program = "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")
            tasks.append({
                "id": f"{path.stem}_{lemma_name}_{idx}",
                "type": site.kind,
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


def build_empty_body_file(path: Path, lemma_name: str, modular: bool = False) -> Optional[str]:
    """Build a Dafny file with the specified lemma's body emptied.

    Args:
        path: Path to the Dafny file
        lemma_name: Name of the lemma to empty
        modular: If True, axiomatize other lemmas

    Returns:
        The modified file content as a string, or None if lemma not found
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find the target lemma range
    span = _find_target_lemma_range(path, lemma_name, lines)
    if not span:
        return None

    _sl, _el, bstart, bend = span

    # If modular, axiomatize other lemmas first
    if modular:
        lines = _axiomatize_other_lemmas(path, lines, (bstart, bend))
        # Re-find the lemma range after axiomatization (line numbers may have changed)
        # Write temp file for LSP
        tmp_path = path.parent / f"{path.stem}.empty.tmp.dfy"
        tmp_path.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
        try:
            span = _find_target_lemma_range(tmp_path, lemma_name, lines)
            if not span:
                return None
            _sl, _el, bstart, bend = span
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    # Empty the lemma body: keep only the opening and closing braces
    # Find the opening brace line and closing brace line
    new_lines = lines[:]

    # Get indentation from the line after opening brace (or use default)
    if bstart + 1 < len(lines) and bstart + 1 < bend:
        sample_line = lines[bstart + 1]
        indent = sample_line[:len(sample_line) - len(sample_line.lstrip())]
    else:
        indent = "  "

    # Delete everything between opening brace and closing brace
    # Keep the line with '{' and the line with '}'
    if bend > bstart + 1:
        del new_lines[bstart + 1:bend]

    return "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")


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
