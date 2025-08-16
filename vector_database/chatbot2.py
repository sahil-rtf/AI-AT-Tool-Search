import argparse
import json
from qdrant_client import QdrantClient
import google.generativeai as genai
import ollama
import re
import os
from dotenv import load_dotenv
from langchain.prompts import PromptTemplate

load_dotenv()

def sanitize_text(text: str) -> str:
    """Removes excessive newlines, whitespace, and escapes quotes for JSON compatibility."""
    if not isinstance(text, str):
        return ""
    cleaned_text = re.sub(r'\s+', ' ', text).strip()
    cleaned_text = cleaned_text.replace('"', '\\"')
    return cleaned_text

def search_tools(query: str, client: QdrantClient, model_name: str, collection_name: str, score_threshold: float = 0.3, limit: int = 100):
    """
    Searches for tools in the Qdrant collection based on a text query.
    Retrieves all tools above a certain similarity score threshold.
    """
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
    Generates a response using the Gemini 2.0 Flash model based on the search results.
    """
    if not results or not results.points:
        return json.dumps({"answer": "I couldn't find any relevant tools for your query.", "id_tags": []}, indent=2)

    tool_contexts = []
    for result in results.points:
        payload = result.payload
        
        # Collect disability categories that are true
        disability_categories = []
        disability_fields = ['reading', 'cognitive', 'vision', 'physical', 'hearing', 'speech_communication', 'training_therapy', 'executive_function']
        for field in disability_fields:
            if payload.get(field) is True:
                # Convert field names to readable format
                readable_name = field.replace('_', ' ').replace('/', ' ').title()
                if field == 'speech_communication':
                    readable_name = 'Speech/Communication'
                elif field == 'training_therapy':
                    readable_name = 'Training/Therapy'
                elif field == 'executive_function':
                    readable_name = 'Executive Function'
                disability_categories.append(readable_name)
        
        # Collect platforms that are true
        platforms = []
        platform_fields = ['windows', 'macintosh', 'chromebook', 'ipad_ipados', 'iphone_ios', 'android']
        for field in platform_fields:
            if payload.get(field) is True:
                # Convert field names to readable format
                readable_name = field.replace('_', ' ').title()
                if field == 'ipad_ipados':
                    readable_name = 'iPad (iPadOS)'
                elif field == 'iphone_ios':
                    readable_name = 'iPhone (iOS)'
                elif field == 'macintosh':
                    readable_name = 'macOS'
                platforms.append(readable_name)
        
        # Collect pricing options that are true
        pricing_options = []
        pricing_fields = ['free', 'free_trial', 'lifetime_license', 'subscription']
        for field in pricing_fields:
            if payload.get(field) is True:
                # Convert field names to readable format
                readable_name = field.replace('_', ' ').title()
                if field == 'free_trial':
                    readable_name = 'Free Trial'
                elif field == 'lifetime_license':
                    readable_name = 'Lifetime License'
                pricing_options.append(readable_name)
        
        tool_info = {
            "tool_name": sanitize_text(payload.get('product_feature_name', '')),
            "company": sanitize_text(payload.get('company', '')),
            "description": sanitize_text(payload.get('description', '')),
            "auditor_notes": sanitize_text(payload.get('auditor_notes', '')),
            "id_tag": sanitize_text(payload.get('id_tag', '')),
            "disability_categories": disability_categories,
            "platforms": platforms,
            "pricing": pricing_options,
            "website": sanitize_text(payload.get('link_to_description_on_vendor_s_website', '') or payload.get('website', ''))
        }
        tool_contexts.append(tool_info)

    context = json.dumps(tool_contexts, indent=2)

    # Define the prompt template using LangChain
    prompt_template = PromptTemplate(
        input_variables=["query", "context"],
        template="""You are an AI assistant. Your task is to generate a single, valid JSON object.
Do not output any text or markdown before or after the JSON object.

The JSON object must have three keys:
1. "answer": A string that answers the user's query based on the provided tool information.
2. "id_tags": A list of strings, where each string is the "id_tag" of a relevant tool.
3. "search_filters": An object containing suggested search parameters based on the user's query.

User Query: "{query}"

Tool Information:
{context}

For the "search_filters" object, analyze the user's query and suggest relevant filters:

Structure:
{{
  "disability_categories": ["reading", "cognitive", "vision", "physical", "hearing", "speech_communication", "training_therapy", "executive_function"],
  "platforms": ["windows", "macintosh", "chromebook", "ipad_ipados", "iphone_ios", "android"],
  "pricing": ["free", "free_trial", "lifetime_license", "subscription"],
  "installation_type": ["built_in", "requires_installation"]
}}

Guidelines for search_filters:
- Only include categories that are relevant to the user's query
- If user mentions a specific disability (e.g., "I am blind"), include relevant categories (e.g., ["vision"])
- If user mentions specific platforms (e.g., "iPhone app"), include only those platforms
- If no platform is mentioned, include ALL platforms
- If user mentions pricing preferences (e.g., "free tools"), include relevant pricing options
- If no pricing is mentioned, include ALL pricing options
- If user mentions installation preferences, include relevant installation_type
- If no installation preference is mentioned, include ALL installation types

Examples:
- Query: "I am blind" → disability_categories: ["vision"], platforms: all, pricing: all, installation_type: all
- Query: "Free iPhone apps for dyslexia" → disability_categories: ["reading", "cognitive"], platforms: ["iphone_ios"], pricing: ["free"], installation_type: all
- Query: "Windows tools for hearing impaired" → disability_categories: ["hearing"], platforms: ["windows"], pricing: all, installation_type: all

When answering, consider all the available information including:
- Tool name, company, and description
- Disability categories the tool supports
- Platforms/devices the tool works on
- Pricing options available
- Official website for more information
- Any auditor notes that provide additional context"""
    )

    # Format the prompt using the template
    formatted_prompt = prompt_template.format(query=query, context=context)

    try:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(formatted_prompt)
        
        # Clean the response to extract only the JSON part
        cleaned_response = re.search(r'```json\n({.*?})\n```', response.text, re.DOTALL)
        if cleaned_response:
            content = cleaned_response.group(1)
        else:
            # Fallback if the response is not in the expected format
            content = response.text

        parsed_json = json.loads(content)
        return json.dumps(parsed_json, indent=2)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        print(f"Error processing LLM response: {e}")
        # Provide the raw content for debugging if it's not valid JSON
        return json.dumps({"answer": f"The model provided a malformed or unexpected response: {response.text}", "id_tags": []}, indent=2)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return json.dumps({"answer": "An unexpected error occurred while generating the response.", "id_tags": []}, indent=2)


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
    
    response = generate_response(args.query, search_results if search_results else [])
    print(response)

if __name__ == "__main__":
    main() 