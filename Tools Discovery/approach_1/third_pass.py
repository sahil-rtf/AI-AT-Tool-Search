import pandas as pd
import os
import json
import time
from dotenv import load_dotenv
from google import genai
import ast

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables.")

def get_gemini_client():
    """Initializes and returns the Gemini API client."""
    return genai.Client(api_key=GEMINI_API_KEY)

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

def get_valid_categories():
    """Returns a list of the only valid categories."""
    return [
        "Reading", "Cognitive", "Vision", "Physical", "Hearing", 
        "Speech/ Communication", "Training/ Therapy", "Executive Function"
    ]

def get_valid_platforms():
    """Returns a list of the only valid platforms."""
    return [
        "Windows", "Macintosh", "Chromebook", "iPad (iPadOS)", "iPhone (iOS)", "Android"
    ]

def get_valid_pricing():
    """Returns a list of the only valid pricing models."""
    return ["Free", "Free Trial", "Subscription", "One-time purchase"]

def get_missing_fields(row):
    """Identifies fields in a row that are empty or represent an empty list."""
    missing = []
    fields_to_check = ['Categories', 'Platforms', 'Pricing', 'Target Audience', 'Company']
    for field in fields_to_check:
        value = row.get(field)
        if pd.isna(value) or value == '' or str(value).strip() == '[]':
            missing.append(field)
    return missing

def create_completion_prompt(tool_info, missing_fields):
    """Creates the prompt for the Gemini API to complete missing information."""
    
    missing_fields_str = ", ".join(missing_fields)
    
    # --- Instructions for constrained fields ---
    field_instructions = ""
    if "Categories" in missing_fields:
        category_defs = get_category_definitions()
        category_defs_text = "\\n".join([f"- **{name}**: {desc}" for name, desc in category_defs.items()])
        valid_categories = ", ".join(get_valid_categories())
        field_instructions += f"""
# Category Definitions
Here are the definitions for the available categories:
{category_defs_text}

# Category Selection
For the 'Categories' field, you MUST choose one or more values from this exact list: [{valid_categories}].
"""
    
    if "Platforms" in missing_fields:
        valid_platforms = ", ".join(get_valid_platforms())
        field_instructions += f"\n- For the 'Platforms' field, you MUST choose one or more values from this exact list: [{valid_platforms}]."
        
    if "Pricing" in missing_fields:
        valid_pricing = ", ".join(get_valid_pricing())
        field_instructions += f"\n- For the 'Pricing' field, you MUST choose one or more values from this exact list: [{valid_pricing}]."
    
    # --- Main Prompt ---
    prompt = f"""
# Your Task
You are a meticulous data researcher. Your task is to find missing information for an assistive technology tool.

# Tool Information
- Name: {tool_info.get('Product Name', 'N/A')}
- Description: {tool_info.get('Description', 'N/A')}
- Website: {tool_info.get('Website', 'N/A')}

# Missing Information
I need you to find the following missing piece(s) of information: {missing_fields_str}

# Core Requirement
All information, especially the 'Target Audience', must be focused on the person with the disability who directly uses the tool, not on caregivers, therapists, or educators.

# Instructions
1.  Carefully examine the tool's website and use Google Search to find the information for the missing fields.
2.  **IMPORTANT**: If you cannot find the information or are unsure, DO NOT MAKE ANYTHING UP.{field_instructions}
3.  Return your answer as a single JSON object with two keys: "filled_data" and "ai_comment".
    - "filled_data": An object where keys are the field names (e.g., "Pricing") and values are the information you found. If you found nothing for a field, omit it.
    - "ai_comment": If you cannot find information for one or more fields, provide a brief comment for each, explaining why (e.g., "Pricing is not listed on the official website."). If you found everything, leave this as an empty string.

# Example Response (if some data is found)
```json
{{
  "filled_data": {{
    "Pricing": ["Free Trial", "Subscription"],
    "Platforms": ["Windows", "macOS"]
  }},
  "ai_comment": "Could not determine the specific Target Audience from the website."
}}
```

# Example Response (if no data is found)
```json
{{
  "filled_data": {{}},
  "ai_comment": "Pricing and Platform information could not be located on the vendor's website or through search."
}}
```

Provide only the JSON response.
"""
    return prompt

def complete_missing_data(df):
    """
    Identifies tools with missing data and uses Gemini to fill them in or add comments.
    """
    model = get_gemini_client()
    tools_to_process = df[df.apply(lambda row: len(get_missing_fields(row)) > 0, axis=1)]

    if tools_to_process.empty:
        print("No tools with missing data to process.")
        # Ensure AI Comments column exists even if there's nothing to do
        if 'AI Comments' not in df.columns:
            df['AI Comments'] = ''
        return df

    print(f"Found {len(tools_to_process)} tools with missing information to process.")
    
    # Initialize the comments column if it doesn't exist
    if 'AI Comments' not in df.columns:
        df['AI Comments'] = ''
    
    for index, row in tools_to_process.iterrows():
        missing_fields = get_missing_fields(row)
        if not missing_fields:
            continue

        print(f"Processing tool: {row['Product Name']} (Missing: {', '.join(missing_fields)})")
        prompt = create_completion_prompt(row, missing_fields)

        try:
            response = model.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={"tools": [{"google_search": {}}]}
            )
            
            json_text = response.text.replace("```json", "").replace("```", "").strip()
            api_response = json.loads(json_text)
            
            filled_data = api_response.get('filled_data', {})
            ai_comment = api_response.get('ai_comment', '')

            # Update the DataFrame with the filled data
            for field, value in filled_data.items():
                if field in df.columns:
                    print(f"  - Filling {field} with: {value}")
                    # Gemini might return a list, so we store it as a string
                    df.loc[index, field] = str(value)

            # Add any comments from the AI
            if ai_comment:
                print(f"  - Adding AI comment: {ai_comment}")
                # Append comment, handling existing comments
                existing_comment = df.loc[index, 'AI Comments']
                if pd.isna(existing_comment) or existing_comment == '':
                    df.loc[index, 'AI Comments'] = ai_comment
                else:
                    df.loc[index, 'AI Comments'] += f"; {ai_comment}"
            
            time.sleep(5) # Rate limit

        except Exception as e:
            print(f"An error occurred while processing {row['Product Name']}: {e}")
            df.loc[index, 'AI Comments'] = f"Error during AI processing: {e}"

    return df

def main():
    """Main function to run the third pass for data completion."""
    print("--- Starting Third Pass: Data Completion and Commenting ---")
    
    input_file = 'new_tools_with_validation.csv'
    output_file = 'new_tools_complete.csv'

    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found. Please run the URL checker first.")
        return

    df = pd.read_csv(input_file)
    
    df_completed = complete_missing_data(df)
    
    df_completed.to_csv(output_file, index=False)
    print(f"Data completion finished. Results saved to {output_file}")
    
    print("--- Third Pass Complete ---")

if __name__ == "__main__":
    main() 