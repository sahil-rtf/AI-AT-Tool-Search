import pandas as pd
from qdrant_client import QdrantClient, models
import ollama
import re
import time
import os

# 1. Load data
def load_data(file_path):
    """Loads data from a CSV file."""
    return pd.read_csv(file_path)

# 2. Clean column names
def clean_column_names(df):
    """Cleans DataFrame column names to be valid identifiers."""
    cleaned_cols = []
    for col in df.columns:
        # Replace sequences of non-alphanumeric characters with a single underscore
        cleaned_col = re.sub(r'[^a-zA-Z0-9]+', '_', col)
        cleaned_col = cleaned_col.lower().strip('_')
        cleaned_cols.append(cleaned_col)
    df.columns = cleaned_cols
    return df

# 3. Convert flag-like columns to boolean
def convert_flags_to_bool(df, flag_columns):
    """Converts specified DataFrame columns to boolean based on presence of data."""
    for col in flag_columns:
        if col in df.columns:
            # True if not NaN/None and not an empty/whitespace string
            df[col] = df[col].notna() & (df[col].astype(str).str.strip() != '')
    return df

# 4. Generate embeddings
def get_embeddings(texts, model_name='nomic-embed-text'):
    """Generates embeddings for a list of texts using Ollama."""
    # Ollama's embeddings API is often called per-item
    embeddings = []
    for i, text in enumerate(texts):
        response = ollama.embeddings(model=model_name, prompt=text)
        embeddings.append(response["embedding"])
        # Simple progress indicator
        print(f"Generated embedding {i+1}/{len(texts)}", end='\\r')
        time.sleep(0.1) # Add a small delay to avoid overwhelming the Ollama server
    print("\\nEmbeddings generated.")
    return embeddings

# 5. Setup Qdrant
def setup_qdrant_collection(client, collection_name, vector_size, flag_columns):
    """Creates a new collection in Qdrant, re-creating it if it exists, and sets up payload indexes."""
    if client.collection_exists(collection_name=collection_name):
        client.delete_collection(collection_name=collection_name)
        print(f"Collection '{collection_name}' deleted and will be re-created.")

    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
    )
    print(f"Collection '{collection_name}' created.")

    # Create payload indexes for faster filtering
    for col in flag_columns:
        client.create_payload_index(collection_name=collection_name, field_name=col, field_schema=models.PayloadSchemaType.BOOL)
    
    client.create_payload_index(collection_name=collection_name, field_name="company", field_schema=models.PayloadSchemaType.KEYWORD)

    print("Payload indexes created for all boolean flags and the company field.")

# 6. Upsert data
def upsert_data(client, collection_name, embeddings, payloads):
    """Upserts data into a Qdrant collection."""
    client.upsert(
        collection_name=collection_name,
        points=models.Batch(
            ids=list(range(len(payloads))),
            vectors=embeddings,
            payloads=payloads
        ),
        wait=True
    )
    print("Data upserted successfully.")

# 7. Prepare rich text for embedding
def get_texts_to_embed(df):
    """Combines multiple columns to create a single descriptive text for embedding."""
    texts = []
    # Define columns for disability categories and platforms
    disability_cols = ['reading', 'cognitive', 'vision', 'physical', 'hearing', 'speech_communication', 'training_therapy', 'executive_function']
    platform_cols = ['windows', 'macintosh', 'chromebook', 'ipad_ipados', 'iphone_ios', 'android']
    pricing_cols = ['free', 'free_trial', 'lifetime_license', 'subscription']

    for _, row in df.iterrows():
        # Start with the core information
        text_parts = [
            str(row.get('product_feature_name', '')),
            str(row.get('description', '')),
            str(row.get('company', ''))
        ]

        # Add disability categories
        categories = [col.replace('_', ' ').title() for col in disability_cols if row.get(col) is True]
        if categories:
            text_parts.append(f"Disability Categories: {', '.join(categories)}")

        # Add platforms
        platforms = [col.replace('_', ' ').title() for col in platform_cols if row.get(col) is True]
        if platforms:
            text_parts.append(f"Supports: {', '.join(platforms)}")
        
        # Add pricing information
        pricing = [col.replace('_', ' ').title() for col in pricing_cols if row.get(col) is True]
        if pricing:
            text_parts.append(f"Pricing: {', '.join(pricing)}")

        texts.append(" - ".join(filter(None, text_parts)))
    return texts

def main():
    qdrant_client = QdrantClient(url="http://localhost:6333")
    collection_name = "active_tools"
    
    # Correctly locate the CSV file relative to this script's location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_file_path = os.path.join(script_dir, '..', 'Tools Discovery', 'approach_1', 'active_tools.csv')

    vector_size = 768  # nomic-embed-text model produces 768-dimensional vectors

    df = load_data(csv_file_path)
    df = clean_column_names(df)

    # Remove unwanted columns before processing
    columns_to_drop = [
        'unnamed_6',
        'data_entry_person_notes',
        'atod_installer_short_name',
        'internal_notes'
    ]
    df = df.drop(columns=columns_to_drop, errors='ignore')

    flag_columns = [
        'built_in', 'at_installed', 'free', 'free_trial', 'lifetime_license', 'subscription',
        'reading', 'cognitive', 'vision', 'physical', 'hearing', 'speech_communication', 'training_therapy',
        'windows', 'macintosh', 'chromebook', 'ipad_ipados', 'iphone_ios', 'android'
    ]
    df = convert_flags_to_bool(df, flag_columns)

    # Create the rich text for embedding
    texts_to_embed = get_texts_to_embed(df)
    
    # Generate embeddings
    embeddings = get_embeddings(texts_to_embed)

    # Setup Qdrant collection
    setup_qdrant_collection(qdrant_client, collection_name, vector_size, flag_columns)

    # Prepare payloads
    # The payload will be all the data from the CSV row, filling NaN with None
    payloads = df.where(pd.notna(df), None).to_dict(orient='records')

    # Upsert data into Qdrant
    upsert_data(qdrant_client, collection_name, embeddings, payloads)

    print("All tools have been embedded and stored in Qdrant with cleaned, boolean-flagged data.")

if __name__ == "__main__":
    main() 