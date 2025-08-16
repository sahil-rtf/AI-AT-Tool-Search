import argparse
import json
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
    Generates a response using the gemma2:27b model based on the search results.
    """
    if not results or not results.points:
        return json.dumps({"answer": "I couldn't find any relevant tools for your query.", "id_tags": []}, indent=2)

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
        template="""You are an AI assistant. Your task is to generate a single, valid JSON object.
Do not output any text or markdown before or after the JSON object.

The JSON object must have two keys:
1. "answer": A string that answers the user's query based on the provided tool information.
2. "id_tags": A list of strings, where each string is the "id_tag" of a relevant tool.

User Query: "{query}"

Tool Information:
{context}"""
    )

    # Format the prompt using the template
    formatted_prompt = prompt_template.format(query=query, context=context)

    response = ollama.chat(
        model='mistral:7b',
        messages=[{'role': 'system', 'content': formatted_prompt}],
        format='json'
    )
    
    try:
        content = response['message']['content']
        # The 'format="json"' parameter should return a JSON string, but we parse it to be safe
        parsed_json = json.loads(content)
        return json.dumps(parsed_json, indent=2)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Error processing LLM response: {e}")
        # Provide the raw content for debugging if it's not valid JSON
        fallback_content = response.get('message', {}).get('content', '{}')
        return json.dumps({"answer": f"The model provided a malformed response: {fallback_content}", "id_tags": []}, indent=2)


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
        score_threshold=0.6
    )

    #print(search_results)
    
    response = generate_response(args.query, search_results if search_results else [])
    print(response)

if __name__ == "__main__":
    main() 