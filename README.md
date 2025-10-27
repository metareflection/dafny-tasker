# dafny-tasker

LSP-based extractor for Dafny proof/annotation tasks:
- `focus`: full program with exactly one `/*[CODE HERE]*/` per task in the target lemma.
- `focus --modular`: same, but **axiomatize other lemmas** by adding `{:axiom}` and **removing bodies**.
- `axiomatize`: transform a file to axiomatize all lemmas except the target, writing the result to a new file.

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
```bash
# Focus (regular): full program + one CODE_HERE_MARKER
python -m dafny_tasker.cli focus --file examples/bs_demo.dfy --lemma binarySearchCorrect --out focus.jsonl

# Focus (modular): axiomatized other lemmas
python -m dafny_tasker.cli focus --file examples/bs_demo.dfy --lemma binarySearchCorrect --out modular.jsonl --modular

# Axiomatize: transform file to axiomatize all lemmas except the target
python -m dafny_tasker.cli axiomatize --file examples/bs_demo.dfy --lemma binarySearchCorrect --out axiomatized.dfy

# Axiomatize: infer target lemma from CODE_HERE_MARKER location
python -m dafny_tasker.cli axiomatize --file examples/bs_demo.dfy --out axiomatized.dfy
```
