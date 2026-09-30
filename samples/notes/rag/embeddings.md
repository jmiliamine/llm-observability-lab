# Embedding models

An embedding model turns text into a fixed-length vector. Retrieval quality depends on it more than on the vector store.

Things to check when picking one:

- **Dimension**: 384, 768 or 1024 are common. Larger vectors cost more memory and compute per query, and are not always better.
- **Context length**: text beyond the limit is truncated silently. Chunks must fit.
- **Language**: many small models are trained mostly on English.
- **Asymmetric prefixes**: some models expect a prefix such as `search_query:` for questions and `search_document:` for chunks. Forgetting them lowers scores.
- **Licence**: open weights do not always mean commercial use is allowed.

Local models such as `nomic-embed-text` (768 dimensions) run on a laptop CPU at a few hundred chunks per minute, which is enough to index a few thousand notes in minutes.

The index must record which model built it. Querying an index built with model A using embeddings from model B returns garbage without any error, because both are just lists of floats. A simple guard is to store the model name next to the index and refuse to serve when it does not match the configuration.

Embedding calls are worth instrumenting like chat calls: duration, number of inputs per batch and errors. On large re-indexing jobs they are the slowest part.
