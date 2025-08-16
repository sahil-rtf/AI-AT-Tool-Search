import argparse
import json
import sys
from qdrant_client import QdrantClient
import ollama
import re
from langchain.prompts import PromptTemplate

def sanitize_text(text: str) -> str:
    """Removes excessive newlines, whitespace, and escapes quotes for JSON compatibility."""
    if not isinstance(text, str):
        return ""
    # Replace multiple whitespace characters (including newlines) with a single space
    cleaned_text = re.sub(r'\s+', ' ', text).strip()
    # Escape double quotes to prevent breaking JSON structure
    cleaned_text = cleaned_text.replace('"', '\\"')
    return cleaned_text

def search_tools(query: str, client: QdrantClient, model_name: str, collection_name: str, score_threshold: float = 0.3, limit: int = 100):
    """
    Searches for tools in the Qdrant collection based on a text query.
    Retrieves all tools above a certain similarity score threshold.
    """
    # Note: client.search is deprecated. Consider switching to client.query_points in the future.
    response = ollama.embeddings(model=model_name, prompt=query)
    query_vector = response["embedding"]

    search_result = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        score_threshold=score_threshold,
        limit=limit,
        with_payload=True
    )

    return search_result

def generate_response(query: str, results):
    """
    Generates a response using the Llama3 model based on the search results.
    """
    if not results or not results.points:
        return "I couldn't find any relevant tools for your query."

    tool_contexts = []
    for result in results.points:
        payload = result.payload
        tool_info = {
            "tool_name": sanitize_text(payload.get('product_feature_name', '')),
            "company": sanitize_text(payload.get('company', '')),
            "description": sanitize_text(payload.get('description', '')),
            "id_tag": sanitize_text(payload.get('id_tag', ''))
        }
        tool_contexts.append(tool_info)

    context = json.dumps(tool_contexts, indent=2)

    # Define the prompt template using LangChain
    prompt_template = PromptTemplate(
        input_variables=["query", "context"],
        template="""You must analyze the user's query and provide ONLY the most relevant assistive technology tools from the provided context.

STRICT REQUIREMENTS:
- Review each tool in the context below
- Select ONLY tools that directly address the user's specific need
- For each relevant tool, provide: tool name, company, and description
- Do NOT include generic responses like "What would you like to know?"
- Do NOT include tools that are not directly relevant
- If no tools match, say "No tools found for this specific need"

User Query: {query}

Available Tools:
{context}

Response format: List only the relevant tools with their details."""
    )

    # Format the prompt using the template
    formatted_prompt = prompt_template.format(query=query, context=context)
    
    # Debug: Print first 500 chars of the context to see what's being sent
    print(f"Context preview: {context[:500]}...", file=sys.stderr)

    response = ollama.chat(
        model='llama3:instruct',
        messages=[{'role': 'system', 'content': formatted_prompt}]
    )
    
    try:
        content = response['message']['content']
        return content
    except (KeyError, TypeError) as e:
        print(f"Error processing LLM response: {e}")
        return "I apologize, but I encountered an error processing the response."


def main():
    parser = argparse.ArgumentParser(description="Chat with a bot about assistive tools.")
    parser.add_argument("query", type=str, help="Your query for the chatbot.")
    args = parser.parse_args()

    qdrant_client = QdrantClient(url="http://localhost:6333")
    embedding_model_name = 'nomic-embed-text'
    collection_name = "active_tools"

    search_results = search_tools(
        query=args.query,
        client=qdrant_client,
        model_name=embedding_model_name,
        collection_name=collection_name,
        score_threshold=0.55
    )
    
    # Debug: Print number of results found
    if search_results and search_results.points:
        print(f"Found {len(search_results.points)} relevant tools", file=sys.stderr)
    else:
        print("No relevant tools found", file=sys.stderr)
    
    response = generate_response(args.query, search_results if search_results else [])
    print(response)

if __name__ == "__main__":
    main() 