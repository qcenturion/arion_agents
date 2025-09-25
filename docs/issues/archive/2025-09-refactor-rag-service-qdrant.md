# Refactor RAG Service with Qdrant and BGE Embeddings

**Status:** To Do
**Workstream:** RAG Hybrid Search
**Epic:** [Link to Epic if applicable]

## Summary
The current local RAG service (`tools/rag_service/service.py`) uses an in-memory, keyword-based search for development purposes. This issue tracks the work to replace this mock implementation with a production-grade backend using Qdrant as the vector store and a BGE model for text embeddings.

## Acceptance Criteria
1.  The `rag-service` container is updated to use the `qdrant/qdrant` and a relevant BGE embedding model (e.g., `BAAI/bge-small-en-v1.5`).
2.  The `POST /index` endpoint chunks incoming documents, generates embeddings using the BGE model, and upserts the resulting vectors into a Qdrant collection.
3.  The `POST /search` endpoint generates an embedding for the incoming query and performs a vector search against the Qdrant collection to retrieve the top_k results.
4.  The existing `docker-compose.yml` is updated to include the Qdrant service, or a new `docker-compose.rag.yml` is created.
5.  The `rag:hybrid` tool continues to function correctly with the new service without requiring changes to the core agent runtime.
6.  The `tools/rag_index.py` and `tools/rag_search.py` scripts work with the new service.

## Test Plan
1.  Start the updated `rag-service` and its Qdrant dependency.
2.  Run `python3 tools/rag_index.py` to index the `city_activities.md` corpus. Verify that vectors are created in the Qdrant collection.
3.  Run `python3 tools/rag_search.py` with a query like "things to do in London" and confirm that relevant, vector-scored results are returned.
4.  Run the full `locations_demo` smoke test (`bash tools/serve_and_run.sh...`) to ensure the agent flow works end-to-end.
