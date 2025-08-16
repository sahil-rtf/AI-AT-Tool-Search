import pandas as pd
import os
import json
import time
from dotenv import load_dotenv
from google import genai

# Load environment variables from .env file (for API key)
load_dotenv()

# Configure the Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please create a .env file with your API key.")

def get_category_definitions():
    """Returns a dictionary of category definitions."""
    return {
        "Reading": "Tools designed to assist individuals who have difficulty reading text. This includes people with reading disabilities such as dyslexia, those with low vision who struggles to read standard text, and individuals who are blind. These tools may offer features like text-to-speech, screen magnification, high-contrast modes, or simplified text presentation.",
        "Cognitive": "Tools intended to support users with cognitive disabilities that affect reading, writing, memory, or comprehension. This includes individuals with dyslexia, dysgraphia, ADHD, or processing disorders. Such tools may provide simplified content, visual or auditory alternatives, or support for multimodal learning (e.g., listening to text instead of reading).",
        "Vision": "Tools that assist individuals who are blind, have low vision, or other vision-related impairments. This category also includes tools designed to prevent seizures triggered by visual stimuli, such as flashing lights. Examples include screen readers, Braille displays, high-contrast modes, and tools that reduce flickering or visual clutter.",
        "Physical": "Tools designed to help users with physical disabilities that limit their ability to interact with devices using standard input methods. This includes individuals with limited or no use of their hands, or those with conditions like paralysis or motor impairments. Examples include eye-tracking systems, head-controlled pointers, adaptive switches, and voice-controlled interfaces.",
        "Hearing": "Tools that assist individuals who are deaf or hard of hearing. These tools may include captioning, speech-to-text transcriptions, sign language support, amplification tools, and visual alerts. The goal is to provide accessible communication and information where audio would otherwise be a barrier.",
        "Speech/ Communication": "Tools that assist individuals who are non-verbal or have difficulty speaking or forming coherent verbal communication. This includes augmentative and alternative communication (AAC) devices like symbol-based communication boards, speech-generating apps (e.g., TD Snap), and sentence construction aids. It may also extend to language translation tools when language barriers create communication challenges.",
        "Training/ Therapy": "Tools that offer therapeutic or educational support for individuals with disabilities. These may include structured programs to build life skills, cognitive therapies, speech therapy tools, or physical rehabilitation platforms. The goal is to help users develop, maintain, or improve functional abilities.",
        "Executive Function": "Tools designed to assist individuals who have trouble with planning, organization, time management, and other executive functions. Examples include mind mapping software, task planners, and reminder apps."
    }

def filter_non_digital_tools(input_file, output_file):
    """
    Loads tools, filters out non-digital ones, and ensures verification columns exist.
    """
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found. Please run the discovery script first.")
        return None

    df = pd.read_csv(input_file)

    # Ensure verification columns exist for robustness
    if 'AI Verified' not in df.columns:
        df['AI Verified'] = False
    if 'Human Verified' not in df.columns:
        df['Human Verified'] = 'unverified'

    # Filter out non-digital tools
    original_count = len(df)
    df.dropna(subset=['Platforms'], inplace=True)
    df = df[df['Platforms'].str.strip() != '']
    df = df[df['Platforms'].str.strip() != '[]']
    
    removed_count = original_count - len(df)
    if removed_count > 0:
        print(f"Removed {removed_count} non-digital tools (with empty platforms).")

    df.to_csv(output_file, index=False)
    print(f"Filtered tools saved to {output_file}. Found {len(df)} digital tools.")
    return df

def verify_tool_categories(df_to_process):
    """
    Verifies the categories for the given DataFrame of tools.
    """
    if df_to_process.empty:
        print("No new tools to verify categories for.")
        return df_to_process

    print(f"Verifying categories for {len(df_to_process)} tools...")
    category_defs = get_category_definitions()
    category_defs_text = "\n".join([f"- **{name}**: {desc}" for name, desc in category_defs.items()])
    model = genai.Client(api_key=GEMINI_API_KEY)
    
    all_verified_categories = {}
    batch_size = 10

    for i in range(0, len(df_to_process), batch_size):
        batch = df_to_process[i:i+batch_size]
        
        tools_to_verify_text = ""
        for index, row in batch.iterrows():
            tools_to_verify_text += f"  - id_tag: {row['ID Tag']}\n    name: {row['Product Name']}\n    description: {row['Description']}\n"

        prompt = f"""
# Your Task
You are a meticulous data validator. Your task is to verify the functional categories for a batch of assistive technology tools based on their descriptions.

# Category Definitions
Here are the definitions for the available categories:
{category_defs_text}

# Tools to Verify
{tools_to_verify_text}

# Instructions
Based on each tool's description, identify all the categories it belongs to from the list above.

# Core Requirement
The categories should reflect direct use by a person with a disability. For example, if a tool is for a therapist to manage patient schedules, it is NOT a "Physical" or "Cognitive" tool for the end-user.

Return your answer as a single JSON object with a single key, "tools", which contains a list of objects. Each object must have two keys: "id_tag" and "categories".

Example Response:
```json
{{
  "tools": [
    {{
      "id_tag": "example_id_1",
      "categories": ["Vision", "Reading"]
    }},
    {{
      "id_tag": "example_id_2",
      "categories": ["Cognitive"]
    }}
  ]
}}
```
Provide only the JSON response.
"""
        
        try:
            print(f"Processing category verification batch {i//batch_size + 1}...")
            response = model.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            json_text = response.text.replace("```json", "").replace("```", "").strip()
            verified_data = json.loads(json_text)
            
            for tool in verified_data['tools']:
                all_verified_categories[tool['id_tag']] = tool['categories']
        except Exception as e:
            print(f"An error occurred during category verification for batch {i//batch_size + 1}: {e}")
            for _, row in batch.iterrows():
                all_verified_categories[row['ID Tag']] = row['Categories']
        time.sleep(5)

    df_to_process['Categories'] = df_to_process['ID Tag'].map(all_verified_categories).fillna(df_to_process['Categories'])
    return df_to_process

def refine_tool_descriptions(df_to_process):
    """
    Refines the descriptions for the given DataFrame of tools.
    """
    if df_to_process.empty:
        print("No new tools to refine descriptions for.")
        return df_to_process
        
    print(f"Refining descriptions for {len(df_to_process)} tools...")
    model = genai.Client(api_key=GEMINI_API_KEY)
    all_refined_descriptions = {}
    batch_size = 10

    for i in range(0, len(df_to_process), batch_size):
        batch = df_to_process[i:i+batch_size]
        tools_to_refine_text = ""
        for _, row in batch.iterrows():
            tools_to_refine_text += f"  - id_tag: {row['ID Tag']}\n    name: {row['Product Name']}\n    current_description: {row['Description']}\n"

        prompt = f"""
# Your Task
You are a technical writer specializing in assistive technology. Your task is to refine the descriptions for a batch of tools.

# Tools to Refine
{tools_to_refine_text}

# Instructions
- For each tool, review the current description for accuracy, clarity, and completeness.
- If a description is already high-quality and more than 90% correct, use it unchanged.
- Otherwise, provide a concise and improved description that accurately summarizes the tool's purpose and key features.
- New descriptions should be no more than 2-3 sentences.

# Core Requirement
The description MUST focus on how the tool is used directly by a person with a disability, not by a caregiver or assistant.

Return your answer as a single JSON object with a single key, "tools", which contains a list of objects. Each object must have two keys: "id_tag" and "description".

Example Response:
```json
{{
  "tools": [
    {{
      "id_tag": "example_id_1",
      "description": "This is the new, refined description."
    }},
    {{
      "id_tag": "example_id_2",
      "description": "This description was already good."
    }}
  ]
}}
```
Provide only the JSON response.
"""
        try:
            print(f"Processing description refinement batch {i//batch_size + 1}...")
            response = model.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            json_text = response.text.replace("```json", "").replace("```", "").strip()
            refined_data = json.loads(json_text)
            for tool in refined_data['tools']:
                all_refined_descriptions[tool['id_tag']] = tool['description']
        except Exception as e:
            print(f"An error occurred during description refinement for batch {i//batch_size + 1}: {e}")
            for _, row in batch.iterrows():
                all_refined_descriptions[row['ID Tag']] = row['Description']
        time.sleep(5)

    df_to_process['Description'] = df_to_process['ID Tag'].map(all_refined_descriptions).fillna(df_to_process['Description'])
    return df_to_process

def find_youtube_videos(df_to_process):
    """
    Finds YouTube videos for the given DataFrame of tools.
    """
    if df_to_process.empty:
        print("No new tools to find YouTube videos for.")
        return df_to_process

    print(f"Finding YouTube videos for {len(df_to_process)} tools...")
    model = genai.Client(api_key=GEMINI_API_KEY)
    all_youtube_urls = {}
    batch_size = 10

    for i in range(0, len(df_to_process), batch_size):
        batch = df_to_process[i:i+batch_size]
        tools_to_find_text = ""
        for _, row in batch.iterrows():
            tools_to_find_text += f"  - id_tag: {row['ID Tag']}\n    name: {row['Product Name']}\n"

        prompt = f"""
# Your Task
You are a research assistant. Your task is to find a relevant YouTube video for each assistive technology tool in the provided batch.

# Tools to Find Videos For
{tools_to_find_text}

# Instructions
- For each tool, use Google Search to find a high-quality YouTube video.
- The best videos are official product demos, in-depth reviews, or tutorials from reputable sources.
- Return the full YouTube URL for each tool. If you cannot find a relevant video, return an empty string.
Return your answer as a single JSON object with a single key, "tools", which contains a list of objects. Each object must have two keys: "id_tag" and "youtube_url".

Example Response:
```json
{{
  "tools": [
    {{
      "id_tag": "example_id_1",
      "youtube_url": "https://www.youtube.com/watch?v=example1"
    }},
    {{
      "id_tag": "example_id_2",
      "youtube_url": ""
    }}
  ]
}}
```
Provide only the JSON response.
"""
        try:
            print(f"Processing YouTube video search batch {i//batch_size + 1}...")
            response = model.models.generate_content(model="gemini-2.0-flash", contents=prompt, config={"tools": [{"google_search": {}}]})
            json_text = response.text.replace("```json", "").replace("```", "").strip()
            video_data = json.loads(json_text)
            for tool in video_data['tools']:
                all_youtube_urls[tool['id_tag']] = tool['youtube_url']
        except Exception as e:
            print(f"An error occurred during YouTube video search for batch {i//batch_size + 1}: {e}")
            for _, row in batch.iterrows():
                all_youtube_urls[row['ID Tag']] = ""
        time.sleep(5)

    df_to_process['YouTube URL'] = df_to_process['ID Tag'].map(all_youtube_urls)
    return df_to_process

def main():
    """
    Main function to run the second pass of data processing.
    """
    print("--- Starting Second Pass: Data Refinement and Enrichment ---")
    
    input_file = 'new_tools.csv'
    filtered_file = 'new_tools_filtered.csv'
    final_file = 'new_tools_final.csv'

    # Step 1: Filter tools and prepare the initial dataframe
    df_filtered = filter_non_digital_tools(input_file, filtered_file)
    if df_filtered is None:
        print("Halting execution due to missing input file.")
        return

    # Step 2: Separate tools that need verification from those already verified
    df_verified = df_filtered[df_filtered['AI Verified'] == True]
    df_unverified = df_filtered[df_filtered['AI Verified'] == False]

    print(f"Found {len(df_verified)} tools already AI-verified.")
    
    # Step 3: Process only the unverified tools
    if not df_unverified.empty:
        print(f"Processing {len(df_unverified)} new tools...")
        # Chain the processing steps
        df_processed = verify_tool_categories(df_unverified)
        df_processed = refine_tool_descriptions(df_processed)
        #df_processed = find_youtube_videos(df_processed)
        
        # Mark the processed tools as verified
        df_processed['AI Verified'] = True
        
        # Combine the newly verified tools with the ones that were already verified
        df_final = pd.concat([df_verified, df_processed], ignore_index=True)
        print("Finished processing new tools.")
    else:
        print("No new tools to process.")
        df_final = df_verified

    # Step 4: Save the final, combined DataFrame
    if not df_final.empty:
        df_final.to_csv(final_file, index=False)
        print(f"Final results saved to {final_file}")
    else:
        print("No tools to save in the final file.")

    print("--- Second Pass Complete ---")

if __name__ == "__main__":
    main() 