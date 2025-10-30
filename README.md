# dafny-tasker

LSP-based extractor for Dafny proof/annotation tasks:
- `focus`: full program with exactly one `/*[CODE HERE]*/` per task in the target lemma.
- `focus --modular`: same, but **axiomatize other lemmas** by adding `{:axiom}` and **removing bodies**.
- `sketch`: full program with all extractable statements in the target lemma removed (deleted). Output is the complete lemma body. One task per lemma.
- `extract`: convert JSON tasks to individual `.dfy` files (extracts `program` field only, removing solutions).
- `axiomatize`: transform a file to axiomatize all lemmas except the target, writing the result to a new file.

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/metareflection/dafny-tasker)

## Install
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## LSP (required)
```bash
export DAFNY_LSP_CMD="dafny server"
# or: export DAFNY_LSP_CMD="dotnet /path/to/DafnyLanguageServer.dll"
```

## Commands

### Focus: Generate tasks with one statement per task
```bash
# Focus (regular): full program + one CODE_HERE_MARKER per task
python -m dafny_tasker.cli focus --file examples/bs_demo.dfy --lemma binarySearchCorrect --out focus.jsonl

# Focus (modular): axiomatized other lemmas
python -m dafny_tasker.cli focus --file examples/bs_demo.dfy --lemma binarySearchCorrect --out modular.jsonl --modular

# Focus (multiple files): process all lemmas in all files
python -m dafny_tasker.cli focus --inputs 'bench/*_solution.dfy' --out focus_all.json --json-list
```

### Sketch: Generate structural skeleton tasks
```bash
# Sketch: full program with all statements removed (one task per lemma)
python -m dafny_tasker.cli sketch --file examples/bs_demo.dfy --lemma binarySearchCorrect --out sketch.jsonl

# Sketch (multiple files): process all lemmas in all files
python -m dafny_tasker.cli sketch --inputs 'bench/*_solution.dfy' --out sketches.json --json-list

# Sketch (modular): with axiomatized other lemmas
python -m dafny_tasker.cli sketch --inputs 'bench/*_solution.dfy' --out sketches_modular.json --json-list --modular
```

### Extract: Convert JSON tasks to individual .dfy files
```bash
# Extract programs from tasks (removes solutions, keeps only the program field)
python -m dafny_tasker.cli extract --input sketches.json --out programs_dir/

# Works with both JSON and JSONL formats
python -m dafny_tasker.cli extract --input focus_tasks.jsonl --out focus_programs/
```

### Axiomatize: Transform files for modular verification
```bash
# Axiomatize: transform file to axiomatize all lemmas except the target
python -m dafny_tasker.cli axiomatize --file examples/bs_demo.dfy --lemma binarySearchCorrect --out axiomatized.dfy

# Axiomatize: infer target lemma from CODE_HERE_MARKER location
python -m dafny_tasker.cli axiomatize --file examples/bs_demo.dfy --out axiomatized.dfy
```
