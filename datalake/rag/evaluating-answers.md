# Evaluating RAG answers

A RAG pipeline can fail in two places: retrieval brought back the wrong chunks, or generation did something wrong with the right ones. Measuring them separately tells you which to fix.

For retrieval, build a small set of questions with the source that should answer each one. Then check:

- **Hit rate at k**: is the expected source in the top k results?
- **Scores**: what similarity do relevant chunks get compared to irrelevant ones? This is how the minimum score threshold is calibrated.

For generation, check whether the answer uses only the context (faithfulness), whether it answers the question (relevance), and whether it says "I don't know" when the context is empty instead of inventing something.

In production, cheap signals come from telemetry:

- the share of questions that hit the fallback route, meaning nothing scored above the threshold;
- the distribution of the best retrieval score per question;
- how often the question had to be rewritten before retrieval found something;
- tokens per answer, which drift when prompts or chunk sizes change.

A sudden rise of the fallback ratio after a deployment usually means the index and the embedding model no longer match, or the threshold was tuned for another model.

Keep the evaluation set in the repository and run it when the model, the chunk size or the prompt changes. Twenty good questions catch most regressions.
