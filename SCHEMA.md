# Task JSON schema

Each JSONL line:
{
  "id": "<file_stem>_<lemma>_<index>",
  "type": "assert" | "call",
  "program": "<whole file with exactly one /*[CODE HERE]*/>",
  "output": "<original masked statement>"
}
