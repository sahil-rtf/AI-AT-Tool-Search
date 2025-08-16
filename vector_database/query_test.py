import argparse
from qdrant_client import QdrantClient
import ollama

def search_tools(query: str, client: QdrantClient, model_name: str, collection_name: str, score_threshold: float = 0.5, limit: int = 100):
    """
    Searches for tools in the Qdrant collection based on a text query.
    Retrieves all tools above a certain similarity score threshold.
    """
    # Generate embedding for the query using Ollama
    response = ollama.embeddings(model=model_name, prompt=query)
    query_vector = response["embedding"]

    # Perform the search using a score threshold
    search_result = client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        score_threshold=score_threshold,
        limit=limit
    )

    return search_result

def main():
    parser = argparse.ArgumentParser(description="Search for assistive tools in the Qdrant database.")
    parser.add_argument("query", type=str, help="The search query to find relevant tools.")
    parser.add_argument("--threshold", type=float, default=0.5, help="Similarity score threshold to return results.")
    args = parser.parse_args()

    # --- Configuration ---
    qdrant_client = QdrantClient(url="http://localhost:6333")
    embedding_model_name = 'nomic-embed-text'
    collection_name = "active_tools"
    # --- End Configuration ---

    print(f"Searching for '{args.query}' with a score threshold of {args.threshold}...")

    results = search_tools(
        query=args.query,
        client=qdrant_client,
        model_name=embedding_model_name,
        collection_name=collection_name,
        score_threshold=args.threshold
    )

    print(f"\n--- Found {len(results)} Results ---")
    if not results:
        print("No results found.")
    
    for i, result in enumerate(results):
        payload = result.payload
        print(f"\nResult {i+1}:")
        print(f"  Score: {result.score:.4f}")

        # Sanitize payload strings before printing to avoid terminal formatting issues
        tool_name = str(payload.get('product_feature_name', 'N/A')).replace('\n', ' ').replace('\r', '')
        company = str(payload.get('company', 'N/A')).replace('\n', ' ').replace('\r', '')
        description = str(payload.get('description', 'N/A')).replace('\n', ' ').replace('\r', '')

        print(f"  Tool: {tool_name}")
        print(f"  Company: {company}")
        print(f"  Description: {description}")
        print("-" * 20)

if __name__ == "__main__":
    main() 