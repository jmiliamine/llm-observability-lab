# samples

`notes/` is the demo corpus: 20 short notes on Kubernetes, observability and RAG, written for
this repository. They are what the lab indexes and answers from when you have not pointed it at
your own notes.

The questions sent by `task load` are answered by these notes, and a test keeps the two in sync
(`tests/unit/test_sample_corpus.py`).

To use your own folder of `.md` or `.txt` files instead:

```bash
task app NOTES=/path/to/your/notes
```
