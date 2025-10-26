# dafny-tasker

LSP-based extractor for Dafny proof/annotation tasks:
- `focus`: full program with exactly one `/*[CODE HERE]*/` per task in the target lemma.
- `focus --modular`: same, but **axiomatize other lemmas** by adding `{:axiom}` and **removing bodies** (signatures end with `;`).

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
# Focus (regular): full program + one CODE_HERE
python -m dafny_tasker.cli focus --file examples/bs_demo.dfy --lemma binarySearchCorrect --out focus.jsonl

# Focus (modular): axiomatized other lemmas
python -m dafny_tasker.cli focus --file examples/bs_demo.dfy --lemma binarySearchCorrect --out modular.jsonl --modular
```
