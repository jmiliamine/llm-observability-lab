# Cosine similarity in vector search

An embedding model maps a piece of text to a vector. Texts with similar meaning end up close to each other. Vector search ranks stored chunks by how close they are to the embedding of the question.

Cosine similarity measures the angle between two vectors and ignores their length:

    cos(a, b) = (a . b) / (|a| * |b|)

It ranges from -1 to 1. With most text embedding models, useful matches score well above unrelated text, and the absolute values depend on the model: a score of 0.6 means different things for two models. That is why a minimum score threshold has to be calibrated per model, on real questions, by looking at the scores of relevant and irrelevant chunks.

When vectors are normalized to length 1, cosine similarity equals the dot product, which is cheaper to compute. Many vector stores normalize at insert time for that reason.

Other distances exist. Euclidean distance on normalized vectors gives the same ranking as cosine. Inner product without normalization favours long vectors, which some models are trained for.

Exact search compares the query with every vector. That is fine up to tens of thousands of chunks. Beyond that, approximate nearest neighbour indexes (HNSW, IVF) trade a little recall for a large speedup.

Vectors from two different embedding models are not comparable. Changing the model means rebuilding the index.
