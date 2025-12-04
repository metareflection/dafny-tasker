from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import glob
from typing import List
from tqdm import tqdm

def _write_tasks(tasks, out_path, json_list=False):
    """Write tasks either as a JSON list (when json_list=True) or JSONL by default."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if json_list:
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(tasks, fh, ensure_ascii=False)
    else:
        with out_path.open("w", encoding="utf-8") as fh:
            for t in tasks:
                fh.write(json.dumps(t, ensure_ascii=False) + "\n")


from .focus import build_focus_tasks, build_sketch_task, build_empty_body_file


def cmd_focus(args: argparse.Namespace) -> int:
    from .focus import build_focus_tasks, list_lemmas
    files = []
    if getattr(args, "file", None):
        files.append(args.file)
    for pat in (getattr(args, "inputs", None) or []):
        matches = [Path(p) for p in glob.glob(str(pat), recursive=True)]
        if matches:
            files.extend(matches)
        else:
            files.append(Path(pat))
    # dedup .dfy files
    uniq = []
    seen = set()
    for f in files:
        if f.suffix != ".dfy":
            continue
        key = str(f.resolve())
        if key in seen:
            continue
        seen.add(key); uniq.append(f)
    if not uniq:
        print("no .dfy inputs provided (use --file or --inputs)", file=sys.stderr); return 2

    # Parse extract_types from command line
    extract_types_str = getattr(args, "extract_types", "assert,lemma-call")
    extract_types = set(t.strip() for t in extract_types_str.split(',') if t.strip())
    valid_types = {'assert', 'lemma-call', 'calc', 'forall'}
    invalid_types = extract_types - valid_types
    if invalid_types:
        print(f"error: invalid extract types: {invalid_types}. Valid types: {valid_types}", file=sys.stderr)
        return 2

    all_tasks = []
    for f in tqdm(uniq, desc="Processing files", unit="file"):
        if getattr(args, "lemma", None):
            lemmas = [args.lemma]
        else:
            lemmas = list_lemmas(f)
        if not lemmas:
            tqdm.write(f"[warn] no lemmas found in {f}")
            continue
        for lm in tqdm(lemmas, desc=f"  {f.name}", leave=False, unit="lemma"):
            tasks = build_focus_tasks(f, lm, modular=bool(args.modular), extract_types=extract_types)
            if tasks:
                all_tasks.extend(tasks)
    if not all_tasks:
        print("no tasks generated", file=sys.stderr); return 2
    # prefer --jsonl if both flags set
    jsonl = bool(getattr(args, "jsonl", False))
    json_list = bool(getattr(args, "json_list", False))
    use_jsonl = jsonl or not json_list  # default to JSONL if user didn't ask JSON list
    if not jsonl and not json_list:
        if str(args.out).endswith('.json'):
            use_jsonl = False
        elif str(args.out).endswith('.jsonl'):
            use_jsonl = True
    if json_list and not jsonl:
        use_jsonl = False
    _write_tasks(all_tasks, args.out, json_list=not use_jsonl)
    tqdm.write(f"wrote {len(all_tasks)} tasks -> {args.out}")
    return 0



def cmd_sketch(args: argparse.Namespace) -> int:
    from .focus import build_sketch_task, list_lemmas
    files = []
    if getattr(args, "file", None):
        files.append(args.file)
    for pat in (getattr(args, "inputs", None) or []):
        matches = [Path(p) for p in glob.glob(str(pat), recursive=True)]
        if matches:
            files.extend(matches)
        else:
            files.append(Path(pat))
    # dedup .dfy files
    uniq = []
    seen = set()
    for f in files:
        if f.suffix != ".dfy":
            continue
        key = str(f.resolve())
        if key in seen:
            continue
        seen.add(key); uniq.append(f)
    if not uniq:
        print("no .dfy inputs provided (use --file or --inputs)", file=sys.stderr); return 2

    # Parse extract_types from command line
    extract_types_str = getattr(args, "extract_types", "assert,lemma-call")
    extract_types = set(t.strip() for t in extract_types_str.split(',') if t.strip())
    valid_types = {'assert', 'lemma-call', 'calc', 'forall'}
    invalid_types = extract_types - valid_types
    if invalid_types:
        print(f"error: invalid extract types: {invalid_types}. Valid types: {valid_types}", file=sys.stderr)
        return 2

    all_tasks = []
    for f in tqdm(uniq, desc="Processing files", unit="file"):
        if getattr(args, "lemma", None):
            lemmas = [args.lemma]
        else:
            lemmas = list_lemmas(f)
        if not lemmas:
            tqdm.write(f"[warn] no lemmas found in {f}")
            continue
        for lm in tqdm(lemmas, desc=f"  {f.name}", leave=False, unit="lemma"):
            task = build_sketch_task(f, lm, modular=bool(args.modular), extract_types=extract_types)
            if task:
                all_tasks.append(task)
    if not all_tasks:
        print("no tasks generated", file=sys.stderr); return 2
    # prefer --jsonl if both flags set
    jsonl = bool(getattr(args, "jsonl", False))
    json_list = bool(getattr(args, "json_list", False))
    use_jsonl = jsonl or not json_list  # default to JSONL if user didn't ask JSON list
    if not jsonl and not json_list:
        if str(args.out).endswith('.json'):
            use_jsonl = False
        elif str(args.out).endswith('.jsonl'):
            use_jsonl = True
    if json_list and not jsonl:
        use_jsonl = False
    _write_tasks(all_tasks, args.out, json_list=not use_jsonl)
    tqdm.write(f"wrote {len(all_tasks)} sketch tasks -> {args.out}")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    """Extract programs from JSON tasks into separate .dfy files."""
    import json

    # Read input JSON
    input_path = args.input
    if not input_path.exists():
        print(f"error: input file not found: {input_path}", file=sys.stderr)
        return 2

    with input_path.open('r', encoding='utf-8') as f:
        # Try to load as JSON list first, then JSONL
        content = f.read()
        try:
            tasks = json.loads(content)
        except json.JSONDecodeError:
            # Try JSONL
            tasks = []
            for line in content.splitlines():
                if line.strip():
                    tasks.append(json.loads(line))

    if not tasks:
        print("error: no tasks found in input", file=sys.stderr)
        return 2

    # Create output directory
    output_dir = args.out
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract each program
    count = 0
    for task in tasks:
        task_id = task.get('id', f'task_{count}')
        program = task.get('program', '')
        output = task.get('output', '')

        if not program:
            print(f"[warn] task {task_id} has no program, skipping", file=sys.stderr)
            continue

        # Create filename from task ID
        filename = f"{task_id}.dfy"
        output_path = output_dir / filename

        # Write program to file
        output_path.write_text(program, encoding='utf-8')

        # Write output (solution) to separate file (even if empty)
        output_filename = f"{task_id}_output.dfy"
        output_file_path = output_dir / output_filename
        output_file_path.write_text(output, encoding='utf-8')

        count += 1

    print(f"Extracted {count} programs -> {output_dir}")
    return 0


def cmd_axiomatize(args: argparse.Namespace) -> int:
    from .focus import axiomatize_lemmas, find_lemma_containing_marker

    lemma_name = args.lemma

    # If no lemma specified, try to find it based on CODE_HERE_MARKER
    if not lemma_name:
        lemma_name = find_lemma_containing_marker(args.file)
        if not lemma_name:
            print(f"error: no lemma specified and could not find CODE_HERE_MARKER in {args.file}", file=sys.stderr)
            return 2
        print(f"Found lemma '{lemma_name}' containing CODE_HERE_MARKER")

    success = axiomatize_lemmas(args.file, lemma_name, args.out)
    if not success:
        print(f"error: could not find lemma '{lemma_name}' in {args.file}", file=sys.stderr)
        return 2
    print(f"wrote axiomatized file -> {args.out}")
    return 0


def cmd_empty(args: argparse.Namespace) -> int:
    """Create .dfy files with lemma bodies emptied (one file per lemma)."""
    from .focus import build_empty_body_file, list_lemmas

    files = []
    if getattr(args, "file", None):
        files.append(args.file)
    for pat in (getattr(args, "inputs", None) or []):
        matches = [Path(p) for p in glob.glob(str(pat), recursive=True)]
        if matches:
            files.extend(matches)
        else:
            files.append(Path(pat))

    # Deduplicate .dfy files
    uniq = []
    seen = set()
    for f in files:
        if f.suffix != ".dfy":
            continue
        key = str(f.resolve())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)

    if not uniq:
        print("no .dfy inputs provided (use --file or --inputs)", file=sys.stderr)
        return 2

    # Create output directory
    output_dir = args.out
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for f in tqdm(uniq, desc="Processing files", unit="file"):
        # Determine lemmas to process
        if getattr(args, "lemma", None):
            lemmas = [args.lemma]
        else:
            lemmas = list_lemmas(f)

        if not lemmas:
            tqdm.write(f"[warn] no lemmas found in {f}")
            continue

        for lemma in tqdm(lemmas, desc=f"  {f.name}", leave=False, unit="lemma"):
            content = build_empty_body_file(f, lemma, modular=bool(getattr(args, "modular", False)))
            if content is None:
                tqdm.write(f"[warn] could not find lemma '{lemma}' in {f}")
                continue

            # Write output file: <filestem>_<lemma>.dfy
            out_name = f"{f.stem}_{lemma}.dfy"
            out_path = output_dir / out_name
            out_path.write_text(content, encoding="utf-8")
            count += 1

    print(f"Created {count} emptied files -> {output_dir}")
    return 0


def cmd_minimize(args: argparse.Namespace) -> int:
    """Minimize lemma proofs by greedily removing unnecessary statements."""
    from .minimize import minimize_file
    from .focus import list_lemmas
    import json

    files = []
    if getattr(args, "file", None):
        files.append(args.file)
    for pat in (getattr(args, "inputs", None) or []):
        matches = [Path(p) for p in glob.glob(str(pat), recursive=True)]
        if matches:
            files.extend(matches)
        else:
            files.append(Path(pat))

    # Deduplicate .dfy files
    uniq = []
    seen = set()
    for f in files:
        if f.suffix != ".dfy":
            continue
        key = str(f.resolve())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)

    if not uniq:
        print("no .dfy inputs provided (use --file or --inputs)", file=sys.stderr)
        return 2

    # Parse extract_types from command line
    extract_types_str = getattr(args, "extract_types", "assert,lemma-call")
    extract_types = set(t.strip() for t in extract_types_str.split(',') if t.strip())
    valid_types = {'assert', 'lemma-call', 'calc', 'forall'}
    invalid_types = extract_types - valid_types
    if invalid_types:
        print(f"error: invalid extract types: {invalid_types}. Valid types: {valid_types}", file=sys.stderr)
        return 2

    # Create output directory
    output_dir = args.out
    output_dir.mkdir(parents=True, exist_ok=True)

    # Process each file
    all_reports = []
    timeout = getattr(args, "timeout", 30)

    for f in tqdm(uniq, desc="Minimizing files", unit="file"):
        # Determine lemmas to process
        if getattr(args, "lemma", None):
            lemmas = [args.lemma]
        else:
            lemmas = list_lemmas(f)

        if not lemmas:
            tqdm.write(f"[warn] no lemmas found in {f}")
            continue

        # Output file in the output directory
        output_file = output_dir / f.name

        try:
            report = minimize_file(
                input_path=f,
                output_path=output_file,
                lemmas=lemmas,
                modular=bool(getattr(args, "modular", False)),
                extract_types=extract_types,
                timeout=timeout
            )
            all_reports.append(report)
            tqdm.write(f"Minimized {f.name} -> {output_file}")

            # Print summary for this file
            if "lemma_reports" in report:
                for lr in report["lemma_reports"]:
                    if lr.get("empty_body_sufficient"):
                        tqdm.write(f"  {lr['lemma']}: empty body sufficient")
                    elif "error" in lr:
                        tqdm.write(f"  {lr['lemma']}: {lr['error']}")
                    else:
                        removed = lr.get("statements_removed", 0)
                        kept = lr.get("statements_kept", 0)
                        total = lr.get("total_statements", 0)
                        tqdm.write(f"  {lr['lemma']}: removed {removed}/{total} statements, kept {kept}")

        except Exception as e:
            tqdm.write(f"[error] failed to minimize {f}: {e}")
            continue

    # Write report JSON
    if all_reports:
        report_path = output_dir / "minimize_report.json"
        with report_path.open("w", encoding="utf-8") as fh:
            json.dump(all_reports, fh, ensure_ascii=False, indent=2)
        print(f"\nMinimized {len(all_reports)} files -> {output_dir}")
        print(f"Report written to {report_path}")
        return 0
    else:
        print("No files were successfully minimized", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dafny-tasker", description="LSP-only Dafny focus task generator")
    sub = p.add_subparsers(dest="cmd", required=True)
    p_focus = sub.add_parser("focus", help="Full-program tasks; one CODE_HERE per task in target lemma(s)")
    p_focus.add_argument("--file", dest="file", type=Path, required=False, help="Single .dfy file")
    p_focus.add_argument("--inputs", nargs="+", help="Files or globs (e.g., 'bench/*solution.dfy')")
    p_focus.add_argument("--lemma", dest="lemma", type=str, required=False, help="If omitted, process every lemma in each file")
    p_focus.add_argument("--out", dest="out", type=Path, required=True)
    p_focus.add_argument("--modular", action="store_true", help="Axiomatize other lemmas ({:axiom}; no bodies)")
    p_focus.add_argument("--extract-types", dest="extract_types", type=str, default="assert,lemma-call",
                        help="Comma-separated types to extract: assert,lemma-call,calc,forall (default: assert,lemma-call)")
    p_focus.add_argument("--json-list", action="store_true", help="Write a JSON list instead of JSONL")
    p_focus.add_argument("--jsonl", action="store_true", help="Write JSONL (default)")
    p_focus.set_defaults(func=cmd_focus)
    # sketch command
    p_sketch = sub.add_parser("sketch", help="Generate sketch tasks; one task per lemma with all statements masked")
    p_sketch.add_argument("--file", dest="file", type=Path, required=False, help="Single .dfy file")
    p_sketch.add_argument("--inputs", nargs="+", help="Files or globs (e.g., 'bench/*solution.dfy')")
    p_sketch.add_argument("--lemma", dest="lemma", type=str, required=False, help="If omitted, process every lemma in each file")
    p_sketch.add_argument("--out", dest="out", type=Path, required=True)
    p_sketch.add_argument("--modular", action="store_true", help="Axiomatize other lemmas ({:axiom}; no bodies)")
    p_sketch.add_argument("--extract-types", dest="extract_types", type=str, default="assert,lemma-call",
                        help="Comma-separated types to extract: assert,lemma-call,calc,forall (default: assert,lemma-call)")
    p_sketch.add_argument("--json-list", action="store_true", help="Write a JSON list instead of JSONL")
    p_sketch.add_argument("--jsonl", action="store_true", help="Write JSONL (default)")
    p_sketch.set_defaults(func=cmd_sketch)
    # extract command
    p_extract = sub.add_parser("extract", help="Extract programs from JSON tasks into separate .dfy files")
    p_extract.add_argument("--input", dest="input", type=Path, required=True, help="Input JSON/JSONL file with tasks")
    p_extract.add_argument("--out", dest="out", type=Path, required=True, help="Output directory for .dfy files")
    p_extract.set_defaults(func=cmd_extract)
    # axiomatize command
    p_axiomatize = sub.add_parser("axiomatize", help="Axiomatize all lemmas except the target lemma")
    p_axiomatize.add_argument("--file", dest="file", type=Path, required=True, help="Input .dfy file")
    p_axiomatize.add_argument("--lemma", dest="lemma", type=str, required=False, help="Target lemma to preserve (if omitted, inferred from CODE_HERE_MARKER location)")
    p_axiomatize.add_argument("--out", dest="out", type=Path, required=True, help="Output file path")
    p_axiomatize.set_defaults(func=cmd_axiomatize)
    # empty command
    p_empty = sub.add_parser("empty", help="Create .dfy files with lemma bodies emptied (one file per lemma)")
    p_empty.add_argument("--file", dest="file", type=Path, required=False, help="Single .dfy file")
    p_empty.add_argument("--inputs", nargs="+", help="Files or globs (e.g., 'bench/*solution.dfy')")
    p_empty.add_argument("--lemma", dest="lemma", type=str, required=False, help="If omitted, process every lemma in each file")
    p_empty.add_argument("--out", dest="out", type=Path, required=True, help="Output directory for emptied files")
    p_empty.add_argument("--modular", action="store_true", help="Axiomatize other lemmas ({:axiom}; no bodies)")
    p_empty.set_defaults(func=cmd_empty)
    # minimize command
    p_minimize = sub.add_parser("minimize", help="Minimize lemma proofs by removing unnecessary statements")
    p_minimize.add_argument("--file", dest="file", type=Path, required=False, help="Single .dfy file")
    p_minimize.add_argument("--inputs", nargs="+", help="Files or globs (e.g., 'bench/*solution.dfy')")
    p_minimize.add_argument("--lemma", dest="lemma", type=str, required=False, help="If omitted, process every lemma in each file")
    p_minimize.add_argument("--out", dest="out", type=Path, required=True, help="Output directory for minimized files")
    p_minimize.add_argument("--modular", action="store_true", help="Axiomatize other lemmas ({:axiom}; no bodies)")
    p_minimize.add_argument("--extract-types", dest="extract_types", type=str, default="assert,lemma-call",
                        help="Comma-separated types to extract: assert,lemma-call,calc,forall (default: assert,lemma-call)")
    p_minimize.add_argument("--timeout", dest="timeout", type=int, default=30, help="Verification timeout in seconds (default: 30)")
    p_minimize.set_defaults(func=cmd_minimize)
    # keep optional 'check' subcommand if present
    try:
        p_check = sub.add_parser("check", help="Sanity-check a JSON list of focus tasks")
        p_check.add_argument("--file", dest="file", type=Path, required=True)
        p_check.set_defaults(func=cmd_check)
    except Exception:
        pass
    return p


def main(argv: List[str] | None = None) -> int:
    p = build_parser(); args = p.parse_args(argv); return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
