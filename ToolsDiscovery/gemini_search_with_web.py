import os
import random
import pandas as pd
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


# Maps the internal category label used in prompts/logic → actual column name in active_tools.csv
CATEGORY_COLUMN_MAP = {
    "Vision":               "Vision",
    "Reading":              "Reading",
    "Cognitive":            "Cognitive",
    "Physical":             "Physical",
    "Hearing":              "Hearing",
    "Speech/ Communication":"Speech/Comm",
    "Training/ Therapy":    "Training / Therapy",
    "Executive Function":   "Exec / Focus",
}

# Column names to try (in order) when looking up a tool's product name
PRODUCT_NAME_COLS = [
    'PRODUCT/FEATURE NAME',   # current sheet format (space, no newline)
    'PRODUCT/FEATURE\nNAME',  # legacy format (literal newline)
    'PRODUCT NAME',
    'Product Name',
]


def load_tools_data():
    """Load active and removed tools data from CSV files"""
    active_tools = pd.read_csv('active_tools.csv')
    removed_tools = pd.read_csv('removed_tools.csv')
    return active_tools, removed_tools

def load_new_tools():
    """Load previously discovered new tools"""
    if os.path.exists('new_tools.csv'):
        return pd.read_csv('new_tools.csv')
    else:
        return pd.DataFrame()

def filter_tools_by_category(df, category):
    """Filter tools by a specific category (Vision, Reading, etc.)"""
    col = CATEGORY_COLUMN_MAP.get(category, category)
    if col in df.columns:
        return df[df[col].notna() & (df[col] != '')]
    else:
        print(f"Warning: Category column '{col}' not found in DataFrame columns")
        return pd.DataFrame()

def get_all_categories_for_tools(df, categories):
    """Get all categories that each tool belongs to"""
    tool_categories = {}

    for _, row in df.iterrows():
        product_name = None
        for col in PRODUCT_NAME_COLS:
            if col in row and pd.notna(row[col]) and row[col] != '':
                product_name = row[col]
                break

        if not product_name:
            continue

        # Find all categories this tool belongs to, using the column map
        tool_cats = []
        for category in categories:
            col = CATEGORY_COLUMN_MAP.get(category, category)
            if col in row and pd.notna(row[col]) and row[col] != '':
                tool_cats.append(category)

        if tool_cats:
            tool_categories[product_name] = tool_cats

    return tool_categories

def get_category_description(category):
    """Get the description for a specific executive function category"""
    descriptions = {
        "Reading": "Tools designed to assist individuals who have difficulty reading text. This includes people with reading disabilities such as dyslexia, those with low vision who struggles to read standard text, and individuals who are blind. These tools may offer features like text-to-speech, screen magnification, high-contrast modes, or simplified text presentation.",
        
        "Cognitive": "Tools intended to support users with cognitive disabilities that affect reading, writing, memory, or comprehension. This includes individuals with dyslexia, dysgraphia, ADHD, or processing disorders. Such tools may provide simplified content, visual or auditory alternatives, or support for multimodal learning (e.g., listening to text instead of reading).",
        
        "Vision": "Tools that assist individuals who are blind, have low vision, or other vision-related impairments. This category also includes tools designed to prevent seizures triggered by visual stimuli, such as flashing lights. Examples include screen readers, Braille displays, high-contrast modes, and tools that reduce flickering or visual clutter.",
        
        "Physical": "Tools designed to help users with physical disabilities that limit their ability to interact with devices using standard input methods. This includes individuals with limited or no use of their hands, or those with conditions like paralysis or motor impairments. Examples include eye-tracking systems, head-controlled pointers, adaptive switches, and voice-controlled interfaces.",
        
        "Hearing": "Tools that assist individuals who are deaf or hard of hearing. These tools may include captioning, speech-to-text transcriptions, sign language support, amplification tools, and visual alerts. The goal is to provide accessible communication and information where audio would otherwise be a barrier.",
        
        "Speech/ Communication": "Tools that assist individuals who are non-verbal or have difficulty speaking or forming coherent verbal communication. This includes augmentative and alternative communication (AAC) devices like symbol-based communication boards, speech-generating apps (e.g., TD Snap), and sentence construction aids. It may also extend to language translation tools when language barriers create communication challenges.",
        
        "Training/ Therapy": "Tools that offer therapeutic or educational support for individuals with disabilities. These may include structured programs to build life skills, cognitive therapies, speech therapy tools, or physical rehabilitation platforms. The goal is to help users develop, maintain, or improve functional abilities.",
        "Executive Function": "Tools designed to assist individuals who have trouble with planning, organization, time management, and other executive functions. Examples include mind mapping software, task planners, and reminder apps."
    }
    
    return descriptions.get(category, "No description available for this category")

def format_tools_for_prompt(tools_df, category_name, all_categories):
    """Format the tools data for inclusion in the prompt"""
    if tools_df.empty:
        return "No tools found in this category."
    
    # Get tool categories mapping
    tool_categories_map = get_all_categories_for_tools(tools_df, all_categories)
    
    formatted_tools = []
    for _, row in tools_df.iterrows():
        # Handle potential issues with column names and missing values
        product_name = "Unknown"
        company = "Unknown"
        description = "No description"
        
        # Try different possible column names for product name
        for col in PRODUCT_NAME_COLS:
            if col in row and pd.notna(row[col]) and row[col] != '':
                product_name = row[col]
                break
        
        # Get company name
        for col in ['COMPANY', 'Company']:
            if col in row and pd.notna(row[col]) and row[col] != '':
                company = row[col]
                break
        
        # Get description
        for col in ['DESCRIPTION', 'Description']:
            if col in row and pd.notna(row[col]) and row[col] != '':
                description = row[col]
                break
        
        # Get all categories this tool belongs to
        categories = tool_categories_map.get(product_name, [])
        categories_str = ", ".join([cat for cat in categories if cat != category_name])
        
        # Add categories info if the tool belongs to multiple categories
        if categories_str:
            tool_info = f"- {product_name} by {company}: {description} (Also in categories: {categories_str})"
        else:
            tool_info = f"- {product_name} by {company}: {description}"
            
        formatted_tools.append(tool_info)
    
    return "\n".join(formatted_tools)

def load_pipeline_config():
    """
    Load per-category tool counts written by run_pipeline.py.
    Returns a dict like {"Vision": 10, "Hearing": 5, ...} or None if no config file.
    """
    if os.path.exists("pipeline_config.json"):
        import json
        with open("pipeline_config.json", "r") as f:
            config = json.load(f)
        return config.get("tools_per_category", None)
    return None


def generate_search_prompt(category, tools_list, category_description, all_categories, iteration=1, target_count=10):
    """Generate a prompt for Gemini to search for new tools"""
    
    # Create a persona based on the category
    #Change : I am to Looking for
    if category == "Vision":
        persona = "I am a person who is looking for assistive technology tools that help people who are blind or have low vision."
    elif category == "Hearing":
        persona = "I am a person who is looking for assistive technology tools that help people who are deaf or hard of hearing."
    elif category == "Physical":
        persona = "I am a person who is looking for assistive technology tools that would help a person who has trouble using standrad keyboards and mouse and needs adaptations for keyboards, mouse or alternate ways to generate text or isssue pointing commands on a computer" 
    elif category == "Cognitive":
        persona = "I am a person who is looking for assistive technology tools that would help a person who has cognitive disabilities and has trouble understanding written text, handlling complex things, remembering, carrying out multi step processes"
    elif category == "Reading":
        persona = "I am a person who is looking for assistive technology tools that would help a person who has trouble reading, including trouble seeing the text, having dyslexia, handling complex language, dealing with idioms, trouble tracking across lines, etc"
    elif category == "Speech/ Communication":
        persona = "I am a person who is looking for assistive technology tools that would help a person who has trouble speaking, and who needs tools to make speech clear or provide an alternate way of communicating. Also include tools that help change sign language to tetx or vice versa"
    elif category == "Training/ Therapy":
        persona = "I am a person who is looking for assistive technology tools that would help a person learn/develop skills, including things that help with reading, writing, using a computer, memory, attention, focus etc."
    elif category == "Executive Function":
        persona = "I am a person who is looking for assistive technology tools that would help a person who has trouble with executive functions such as planning, organization, staying on task, working on proper priorities, not missing appointments, and other things that help a person with executive functions."
    else:
        persona = "I am a person who is looking for assistive technology tools that would help a person who has trouble with a disability."
    
    # List all categories to consider for multi-category tools
    other_categories = [c for c in all_categories if c != category]
    other_categories_str = ", ".join(other_categories)
    
    prompt = f"""
# Persona #
{persona}

# Existing Tools #
I'm already familiar with the following tools in the {category} category and don't show me these again:
{tools_list}

# Category Definition #
Category description: {category_description}

# Core Requirement #
The tools you find MUST be directly usable by a person with the disability. Do NOT include tools that are designed for caregivers, therapists, or educators to assist a person with a disability. The end-user must be the person with the disability.

# Your Task #
Can you search the web for {target_count if iteration == 1 else 5} new, innovative digital assistive technology tools (software, apps, browser extensions, etc.) in the {category} category that are NOT in my list above? Do not include physical hardware or devices. Please search for the most current and up-to-date tools available.

Important: Assistive technology tools often serve multiple purposes. For each tool, please indicate ALL categories it belongs to from this list: {category} (primary), {other_categories_str}.

# Output Format #
For each tool, provide the information in JSON format with the following structure:
```json
[
  {{
    "id_tag": "example_id_tag",
    "product_name": "Name of the tool",
    "company": "Company/developer name",
    "description": "Brief description of features and benefits",
    "type": "I",
    "categories": ["Primary category", "Other category 1", "Other category 2"],
    "target_audience": "Specific users within the {category} category who would benefit most",
    "platforms": ["Windows", "Chromebook", "Macintosh/Mac", "iPad", "iPhone", "Android"],
    "pricing": ["Free", "Subscription", "One-time purchase", "Free Trial"],
    "website": "https://official-website.com"
  }},
  ...
]
```

# Formatting Rules #
**ID Tag Instructions:**
- Create the `id_tag` from the company and product name. It should be lowercase with underscores instead of spaces.
- If both names are short, combine them (e.g., if company is "Apple" and product is "Live Caption", the tag is "apple_live_caption").
- If one name is long, use the shorter name as the tag (e.g., if company is "Sensus and RoboBraille Outreach" and product is "RoboBraille", the tag is "robo_braille").
- If both are long, choose the most recognizable one and shorten it to create the tag.
- The `id_tag` should be a unique, readable identifier for the tool.

**Type Instructions:**
- Set the "type" field to "B" if the tool is a built-in feature of an operating system or a larger platform.
- Otherwise, set the "type" field to "I" for any tool that requires separate installation (like an app or browser extension).

**Platform Instructions:**
- The "platforms" field must only contain values from this list: "Windows", "Chromebook", "Macintosh/Mac", "iPad", "iPhone", "Android".
- If a tool is a Chrome extension, list all the platforms that support Chrome extensions from the allowed list.
- Do not include any other platform names.

**Pricing Instructions:**
- The "pricing" field must be an array and only contain values from this list: "Free", "Subscription", "One-time purchase", "Free Trial".
- If a tool has multiple pricing models (e.g., a free tier and a subscription), include all applicable categories in the array. For example: ["Free", "Subscription"].
- Do not add any explanatory text, just the categories.

# Final Instruction #
After providing the JSON response, please also indicate whether there are more tools available that could be added to the list (True/False). If True, I'll ask you for more tools in this category.

Please provide ONLY the JSON response followed by a line with "More tools available: True/False", with no additional text before or after.
"""
    return prompt

def search_new_tools(category, all_categories, iteration=1, target_count=10):
    """Use Gemini API with Google Search to find new tools in a specific category"""
    # Load all tools data
    active_tools, removed_tools = load_tools_data()
    new_tools_df = load_new_tools()
    
    # Combine all tools
    all_tools_df = pd.concat([
        active_tools,
        removed_tools,
        new_tools_df
    ], ignore_index=True)
    
    # Filter tools by category
    category_tools = filter_tools_by_category(all_tools_df, category)
    
    # Get category description
    category_desc = get_category_description(category)
    
    # Format the tools for the prompt
    tools_list = format_tools_for_prompt(category_tools, category, all_categories)
    
    # Generate the prompt
    prompt = generate_search_prompt(category, tools_list, category_desc, all_categories, iteration, target_count)


    model = genai.Client(api_key=GEMINI_API_KEY)

    # Retryable HTTP status codes (transient server-side errors)
    RETRYABLE_CODES = {429, 500, 503}
    MAX_RETRIES = 6
    BASE_DELAY  = 5   # seconds — first wait before retry 1

    print(f"Searching for new tools in {category} category (iteration {iteration})...")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = model.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={"tools": [{"google_search": {}}]},
            )

            # Parse response
            response_text = response.text
            parts = response_text.split("More tools available:")

            json_text = parts[0].strip().replace("```json", "").replace("```", "").strip()

            more_available = False
            if len(parts) > 1:
                more_available = parts[1].strip().lower() == "true"

            return json_text, more_available

        except Exception as e:
            error_str = str(e)

            # Check whether the error looks retryable
            is_retryable = any(str(code) in error_str for code in RETRYABLE_CODES)

            if is_retryable and attempt < MAX_RETRIES:
                # Exponential backoff with full jitter:
                #   wait = random(0, BASE_DELAY * 2^(attempt-1))
                # e.g. caps: 5s, 10s, 20s, 40s, 80s
                cap     = BASE_DELAY * (2 ** (attempt - 1))
                wait    = random.uniform(cap / 2, cap)   # lower half avoids clustering
                print(f"  API error (attempt {attempt}/{MAX_RETRIES}): {error_str}")
                print(f"  Retrying in {wait:.1f}s...")
                time.sleep(wait)
            else:
                # Non-retryable error, or retries exhausted
                print(f"Error calling Gemini API (attempt {attempt}): {error_str}")
                return None, False

    return None, False

def parse_json_response(json_text, category):
    """Parse the JSON response from Gemini"""
    try:
        # Parse the JSON
        tools = json.loads(json_text)
        
        # Ensure the primary category is included
        for tool in tools:
            if "categories" in tool and isinstance(tool["categories"], list):
                if category not in tool["categories"]:
                    tool["categories"].insert(0, category)
        
        return tools
    except Exception as e:
        print(f"Error parsing JSON response: {str(e)}")
        print(f"JSON text: {json_text}")
        return []

def save_results(category, tools, iteration=1):
    """Save the search results to a file"""
    os.makedirs("results", exist_ok=True)
    filename = f"results/{category.replace('/', '_').replace(' ', '_')}_tools_{iteration}.json"
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(tools, f, indent=2)
    
    print(f"Results saved to {filename}")

def update_new_tools_csv(tools):
    """Update the new_tools.csv file with new tools, avoiding duplicates."""
    
    # Define the CSV file path
    csv_file = 'new_tools.csv'
    
    # Check if the CSV file exists, if not create it with a header
    try:
        df_existing = pd.read_csv(csv_file)
    except FileNotFoundError:
        df_existing = pd.DataFrame(columns=['ID Tag', 'Product Name', 'Company', 'Description', 'Type', 'Categories', 'Target Audience', 'Platforms', 'Pricing', 'Website'])

    # Get existing tools from both active_tools and new_tools to check for duplicates
    active_tools_df = pd.read_csv('active_tools.csv')
    
    # Resolve the actual product-name column (handles both old \n and new space variants)
    product_col = next(
        (c for c in PRODUCT_NAME_COLS if c in active_tools_df.columns),
        None
    )
    if product_col is None:
        print("Warning: Could not find product name column in active_tools.csv — skipping duplicate check against active tools.")
        product_col_series = pd.Series([''] * len(active_tools_df))
    else:
        product_col_series = active_tools_df[product_col]

    # Create a unique identifier for existing tools
    active_tools_df['unique_id'] = (
        active_tools_df['COMPANY'].fillna('').astype(str).str.lower().str.replace(r'\s+', '', regex=True)
        + '_'
        + product_col_series.fillna('').astype(str).str.lower().str.replace(r'\s+', '', regex=True)
    )
    
    df_existing['unique_id'] = (df_existing['Company'].fillna('').astype(str).str.lower().str.replace(r'\s+', '', regex=True) + 
                                '_' + 
                                df_existing['Product Name'].fillna('').astype(str).str.lower().str.replace(r'\s+', '', regex=True))

    existing_unique_ids = set(active_tools_df['unique_id']).union(set(df_existing['unique_id']))
    
    # Convert new tools to a DataFrame
    new_tools_df = pd.DataFrame(tools)
    
    # Create a unique identifier for new tools
    new_tools_df['unique_id'] = (new_tools_df['company'].fillna('').astype(str).str.lower().str.replace(r'\s+', '', regex=True) + 
                                 '_' + 
                                 new_tools_df['product_name'].fillna('').astype(str).str.lower().str.replace(r'\s+', '', regex=True))
    
    # Filter out tools that are already in the existing lists
    deduplicated_new_tools_df = new_tools_df[~new_tools_df['unique_id'].isin(existing_unique_ids)]
    
    # If there are no new tools to add, return 0
    if deduplicated_new_tools_df.empty:
        return 0
    
    # Rename columns to match the CSV file
    deduplicated_new_tools_df = deduplicated_new_tools_df.rename(columns={
        'id_tag': 'ID Tag',
        'product_name': 'Product Name',
        'company': 'Company',
        'description': 'Description',
        'type': 'Type',
        'categories': 'Categories',
        'target_audience': 'Target Audience',
        'platforms': 'Platforms',
        'pricing': 'Pricing',
        'website': 'Website'
    })
    
    # Add verification columns
    deduplicated_new_tools_df['AI Verified'] = False
    deduplicated_new_tools_df['Human Verified'] = 'unverified'

    # Select and save the new tools
    final_tools_to_add = deduplicated_new_tools_df[['ID Tag', 'Product Name', 'Company', 'Description', 'Type', 'Categories', 'Target Audience', 'Platforms', 'Pricing', 'Website', 'AI Verified', 'Human Verified']]
    
    # Append the new data to the CSV file
    final_tools_to_add.to_csv(csv_file, mode='a', header=not os.path.exists(csv_file), index=False)
    
    return len(final_tools_to_add)

def main():
    all_categories = [
        "Vision",
        "Reading",
        "Cognitive",
        "Physical",
        "Hearing",
        "Speech/ Communication",
        "Training/ Therapy",
        "Executive Function"
    ]

    # Read per-category targets from run_pipeline.py if available,
    # otherwise default to 10 tools per category for every category.
    pipeline_config = load_pipeline_config()
    if pipeline_config:
        # Only process categories where the user asked for > 0 tools
        categories_to_run = {cat: cnt for cat, cnt in pipeline_config.items() if cnt > 0}
        print(f"Pipeline config loaded: {categories_to_run}")
    else:
        categories_to_run = {cat: 10 for cat in all_categories}

    os.makedirs("results", exist_ok=True)

    for category, target_count in categories_to_run.items():
        print(f"\nProcessing category: {category}  (target: {target_count} tools)")

        iteration = 1
        more_available = True
        total_tools_added = 0

        # Keep iterating until target reached, AI says no more, or 5-iteration safety cap
        while more_available and iteration <= 5 and total_tools_added < target_count:
            json_text, more_available = search_new_tools(
                category, all_categories, iteration, target_count
            )

            if json_text:
                tools = parse_json_response(json_text, category)

                if tools:
                    save_results(category, tools, iteration)
                    tools_added = update_new_tools_csv(tools)
                    total_tools_added += tools_added
                    print(f"Iteration {iteration}: Added {tools_added} new tools "
                          f"(total so far: {total_tools_added}/{target_count})")

                    if tools_added == 0:
                        more_available = False
                else:
                    print(f"No valid tools found in iteration {iteration}")
                    more_available = False
            else:
                print(f"Failed to get a valid response in iteration {iteration}")
                more_available = False

            iteration += 1

            if more_available and total_tools_added < target_count:
                print("Waiting 5 seconds before next API call...")
                time.sleep(5)

        print(f"Completed: {category} — {total_tools_added} tools added.")

    print("\nAll categories processed successfully!")

if __name__ == "__main__":
    main() 