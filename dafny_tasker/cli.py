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


from .focus import build_focus_tasks


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
            tasks = build_focus_tasks(f, lm, modular=bool(args.modular))
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



def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dafny-tasker", description="LSP-only Dafny focus task generator")
    sub = p.add_subparsers(dest="cmd", required=True)
    p_focus = sub.add_parser("focus", help="Full-program tasks; one CODE_HERE per task in target lemma(s)")
    p_focus.add_argument("--file", dest="file", type=Path, required=False, help="Single .dfy file")
    p_focus.add_argument("--inputs", nargs="+", help="Files or globs (e.g., 'bench/*solution.dfy')")
    p_focus.add_argument("--lemma", dest="lemma", type=str, required=False, help="If omitted, process every lemma in each file")
    p_focus.add_argument("--out", dest="out", type=Path, required=True)
    p_focus.add_argument("--modular", action="store_true", help="Axiomatize other lemmas ({:axiom}; no bodies)")
    p_focus.add_argument("--json-list", action="store_true", help="Write a JSON list instead of JSONL")
    p_focus.add_argument("--jsonl", action="store_true", help="Write JSONL (default)")
    p_focus.set_defaults(func=cmd_focus)
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
