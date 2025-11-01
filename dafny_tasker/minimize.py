from __future__ import annotations
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import subprocess
import uuid
import tempfile

from .focus import (
    _find_target_lemma_range,
    _enumerate_sites,
    _axiomatize_other_lemmas,
    list_lemmas,
    Site
)


def verify_dafny_file(file_path: Path, timeout: int = 30) -> bool:
    """Verify a Dafny file using the dafny verify command.

    Args:
        file_path: Path to the Dafny file to verify
        timeout: Timeout in seconds (default: 30)

    Returns:
        True if verification succeeds, False otherwise
    """
    try:
        result = subprocess.run(
            ["dafny", "verify", str(file_path)],
            capture_output=True,
            timeout=timeout,
            text=True
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def minimize_lemma(
    path: Path,
    lemma_name: str,
    modular: bool = False,
    extract_types: set[str] = None,
    timeout: int = 30
) -> Tuple[List[str], Dict[str, Any]]:
    """Minimize a single lemma by greedily removing statements.

    Algorithm:
    1. Try empty body first
    2. If that fails, enumerate all extractable statements
    3. Try removing each statement in reverse order (bottom to top)
    4. Keep removals that maintain verification

    Args:
        path: Path to the Dafny file
        lemma_name: Name of the lemma to minimize
        modular: If True, axiomatize other lemmas
        extract_types: Set of types to extract ('assert', 'lemma-call', 'calc', 'forall')
        timeout: Verification timeout in seconds

    Returns:
        Tuple of (minimized_lines, report_dict)
        - minimized_lines: List of lines with minimized lemma
        - report_dict: Statistics about what was removed
    """
    if extract_types is None:
        extract_types = {'assert', 'lemma-call'}

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Setup for modular mode (same as in focus.py)
    path_for_lsp = path
    lines_for_lsp = lines
    tmp_path: Path | None = None

    try:
        if modular:
            span0 = _find_target_lemma_range(path, lemma_name, lines)
            if not span0:
                return lines, {"error": f"Lemma {lemma_name} not found"}
            _sl0, _el0, bstart0, bend0 = span0
            mod_lines = _axiomatize_other_lemmas(path, lines, (bstart0, bend0))
            tmp_path = path.parent / f"{path.stem}.modular.{uuid.uuid4().hex[:8]}.dfy"
            tmp_path.write_text("\n".join(mod_lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
            path_for_lsp = tmp_path
            lines_for_lsp = mod_lines

        # Find the target lemma
        span = _find_target_lemma_range(path_for_lsp, lemma_name, lines_for_lsp)
        if not span:
            return lines, {"error": f"Lemma {lemma_name} not found"}

        sl, el, bstart, bend = span

        # Step 1: Try empty body first
        empty_lines = lines_for_lsp[:]
        # Replace body with just opening and closing braces
        if bend > bstart:
            # Keep the opening brace line, remove everything between, keep closing brace line
            empty_lines[bstart+1:bend] = []

        # Create a temporary file to test verification
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dfy', delete=False, dir=path.parent) as tmp:
            tmp_test_path = Path(tmp.name)
            tmp.write("\n".join(empty_lines) + ("\n" if text.endswith("\n") else ""))

        try:
            if verify_dafny_file(tmp_test_path, timeout):
                # Empty body works! Return it
                return empty_lines, {
                    "lemma": lemma_name,
                    "empty_body_sufficient": True,
                    "statements_removed": "all"
                }
        finally:
            tmp_test_path.unlink()

        # Step 2: Empty body didn't work, enumerate sites
        sites = _enumerate_sites(path_for_lsp, lines_for_lsp, bstart, bend, extract_types)

        if not sites:
            # No extractable statements
            return lines_for_lsp, {
                "lemma": lemma_name,
                "empty_body_sufficient": False,
                "statements_removed": [],
                "statements_kept": []
            }

        # Step 3: Greedy removal in reverse order
        current_lines = lines_for_lsp[:]
        removed_sites = []
        kept_sites = []

        # Process sites in reverse order (bottom to top)
        for site in reversed(sites):
            # Try removing this site
            test_lines = current_lines[:]

            # Remove lines from site.line_idx to site.end_idx (inclusive)
            del test_lines[site.line_idx:site.end_idx+1]

            # Write to temp file and verify
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dfy', delete=False, dir=path.parent) as tmp:
                tmp_test_path = Path(tmp.name)
                tmp.write("\n".join(test_lines) + ("\n" if text.endswith("\n") else ""))

            try:
                if verify_dafny_file(tmp_test_path, timeout):
                    # Removal successful! Keep the change
                    current_lines = test_lines
                    removed_sites.append({
                        "line": site.line_idx,
                        "kind": site.kind,
                        "text": site.original[:100]  # Truncate for report
                    })

                    # Update line indices for remaining sites
                    # Since we removed lines, we need to adjust indices of sites we haven't processed yet
                    num_lines_removed = site.end_idx - site.line_idx + 1
                    for other_site in sites:
                        if other_site.line_idx > site.line_idx:
                            other_site.line_idx -= num_lines_removed
                            other_site.end_idx -= num_lines_removed
                else:
                    # Removal failed, keep the statement
                    kept_sites.append({
                        "line": site.line_idx,
                        "kind": site.kind,
                        "text": site.original[:100]
                    })
            finally:
                tmp_test_path.unlink()

        report = {
            "lemma": lemma_name,
            "empty_body_sufficient": False,
            "total_statements": len(sites),
            "statements_removed": len(removed_sites),
            "statements_kept": len(kept_sites),
            "removed_details": removed_sites,
            "kept_details": kept_sites
        }

        return current_lines, report

    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


def minimize_file(
    input_path: Path,
    output_path: Path,
    lemmas: List[str] = None,
    modular: bool = False,
    extract_types: set[str] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """Minimize all lemmas in a Dafny file.

    Args:
        input_path: Path to input Dafny file
        output_path: Path to output minimized file
        lemmas: List of lemma names to minimize (if None, minimize all)
        modular: If True, axiomatize other lemmas
        extract_types: Set of types to extract
        timeout: Verification timeout in seconds

    Returns:
        Report dictionary with minimization statistics
    """
    if extract_types is None:
        extract_types = {'assert', 'lemma-call'}

    # Get list of lemmas to process
    if lemmas is None:
        lemmas = list_lemmas(input_path)

    if not lemmas:
        return {"error": "No lemmas found in file"}

    # Start with original file content
    current_lines = input_path.read_text(encoding="utf-8").splitlines()
    all_reports = []

    # Process each lemma
    for lemma_name in lemmas:
        # Write current state to a temp file for this lemma's processing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dfy', delete=False, dir=input_path.parent) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write("\n".join(current_lines) + "\n")

        try:
            minimized_lines, report = minimize_lemma(
                tmp_path,
                lemma_name,
                modular=modular,
                extract_types=extract_types,
                timeout=timeout
            )
            current_lines = minimized_lines
            all_reports.append(report)
        finally:
            tmp_path.unlink()

    # Write final minimized file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(current_lines) + "\n", encoding="utf-8")

    return {
        "input_file": str(input_path),
        "output_file": str(output_path),
        "lemmas_processed": len(lemmas),
        "lemma_reports": all_reports
    }
