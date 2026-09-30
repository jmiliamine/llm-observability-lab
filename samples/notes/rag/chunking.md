# Chunking and chunk overlap

Documents are split into chunks before they are embedded. The chunk is the unit that gets retrieved and pasted into the prompt, so its size shapes the answers.

Small chunks (200 to 400 characters) match precise questions well but lose context: a sentence about "it" without the paragraph that says what "it" is. Large chunks (1,500 characters and more) keep context but dilute the embedding, so a relevant sentence inside a long chunk scores lower, and they use more of the context window.

Chunk overlap repeats the end of one chunk at the start of the next. It protects ideas that straddle a boundary: without overlap, a definition split in the middle may not be retrievable from either half. An overlap of 10 to 20 percent of the chunk size is a common default. More overlap means more chunks, a larger index and more near-duplicates in the results.

Recursive splitters try separators in order (blank lines, then line breaks, then sentences, then words), so chunks tend to end at natural boundaries. Splitting Markdown by headings first keeps sections together.

Keep the source file and position in the chunk metadata. It lets you show citations and debug a bad answer by reading exactly what the model was given.

The only reliable way to choose sizes is to test them: a small set of questions with known good sources, and a check of whether the right chunk comes back in the top results.
