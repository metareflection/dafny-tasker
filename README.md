# dafny-tasker

LSP-based extractor for Dafny proof/annotation tasks:
- `focus`: full program with exactly one `/*[CODE HERE]*/` per task in the target lemma.
- `focus --modular`: same, but **axiomatize other lemmas** by adding `{:axiom}` and **removing bodies**.
- `sketch`: full program with all extractable statements in the target lemma removed (deleted). Output is the complete lemma body. One task per lemma.
- `extract`: convert JSON tasks to individual `.dfy` files (creates `<id>.dfy` for program and `<id>_output.dfy` for solution).
- `axiomatize`: transform a file to axiomatize all lemmas except the target, writing the result to a new file.
- `minimize`: minimize lemma proofs by greedily removing unnecessary statements while maintaining verification.
- `empty`: create `.dfy` files with lemma bodies emptied (one file per lemma) for training proof synthesis systems.

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
# Extract programs from tasks
# Creates <id>.dfy (program) and <id>_output.dfy (solution) for each task
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

### Minimize: Reduce lemma proofs to minimal necessary statements
The `minimize` command reduces lemma proofs to their minimal form by greedily removing unnecessary statements while maintaining verification. It processes each lemma by:
1. First attempting to verify with an empty body
2. If that fails, trying to remove each extractable statement one-by-one in reverse order (bottom-up)
3. Keeping removals that maintain successful verification
4. Generating a JSON report with detailed statistics

```bash
# Minimize: remove unnecessary statements from lemma proofs
python -m dafny_tasker.cli minimize --file examples/bs_demo.dfy --out minimized/

# Minimize (multiple files): process all lemmas in all files
python -m dafny_tasker.cli minimize --inputs 'bench/*_solution.dfy' --out minimized_bench/

# Minimize (specific lemma): only minimize a specific lemma
python -m dafny_tasker.cli minimize --file examples/bs_demo.dfy --lemma binarySearchHelperCorrect --out minimized/

# Minimize (modular): with axiomatized other lemmas
python -m dafny_tasker.cli minimize --file examples/bs_demo.dfy --out minimized/ --modular

# Minimize (custom timeout): adjust verification timeout per attempt (default: 30s)
python -m dafny_tasker.cli minimize --file examples/bs_demo.dfy --out minimized/ --timeout 60

# Minimize (specific statement types): only consider assert statements for removal
python -m dafny_tasker.cli minimize --file examples/bs_demo.dfy --out minimized/ --extract-types assert
```

**Output:**
- Minimized `.dfy` files written to output directory (one per input file)
- `minimize_report.json` with detailed statistics about what was removed from each lemma

### Empty: Create .dfy files with emptied lemma bodies
The `empty` command creates standalone `.dfy` files where a specific lemma's body is emptied, while all other lemmas remain intact. This is useful for training proof synthesis systems like [dafny-zero](https://github.com/metareflection/dafny-zero) to fill in proofs one at a time.

```bash
# Empty: create one file per lemma with that lemma's body emptied
python -m dafny_tasker.cli empty --file examples/bs_demo.dfy --out emptied/

# Empty (multiple files): process all lemmas in all files
python -m dafny_tasker.cli empty --inputs 'bench/*_solution.dfy' --out emptied_bench/

# Empty (specific lemma): only empty a specific lemma
python -m dafny_tasker.cli empty --file examples/bs_demo.dfy --lemma binarySearchCorrect --out emptied/

# Empty (modular): axiomatize other lemmas while emptying the target
python -m dafny_tasker.cli empty --file examples/bs_demo.dfy --out emptied/ --modular
```

**Output:**
- Creates `<filestem>_<lemmaname>.dfy` for each lemma
- Each file has the target lemma's body emptied (`{ }`) while other lemmas remain intact
