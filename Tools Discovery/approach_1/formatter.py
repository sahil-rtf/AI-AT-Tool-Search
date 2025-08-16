import pandas as pd
import ast

def format_for_active_tools(input_file, output_file):
    """
    Formats the verified and completed tools to match the structure of active_tools.csv.
    """
    try:
        df = pd.read_csv(input_file)
    except FileNotFoundError:
        print(f"Error: The input file '{input_file}' was not found.")
        return

    # 1. Filter for tools that have been marked for import
    df_to_import = df[df['Human Verified'].str.lower() == 'verified'].copy()
    
    if df_to_import.empty:
        print("No tools marked as 'Verified' in 'Human Verified' column. Nothing to format.")
        return

    print(f"Found {len(df_to_import)} tools to format for final import.")

    # 2. Create the new DataFrame with the target structure
    # These are the columns from the image you provided
    final_columns = [
        'Built In', 'AT (Installed)', 'FREE', 'Free Trial', 'Lifetime License', 'Subscription',
        'Reading', 'Cognitive', 'Vision', 'Physical', 'Hearing', 'Speech/ Communication', 'Training/ Therapy', 'Executive Function',
        'Windows', 'Macintosh', 'Chromebook', 'iPad (iPadOS)', 'iPhone (iOS)', 'Android',
        'Works with which OS versions', 'ID TAG', 'COMPANY', 'PRODUCT/FEATURE\\nNAME', 'DESCRIPTION',
        'Data-Entry-Person \\nNOTES', "LINK TO DESCRIPTION ON VENDOR'S WEBSITE", 'YOUTUBE VIDEOS?\\n\\nFor multiple Videos \\nput each Video URL on new line in the same cell\\n by using CTRL-ENTER between video links)\\n\\n(On MAC use Command-Enter)',
        'AToD installer (short name)', 'INTERNAL NOTES', 'AUDITOR NOTES'
    ]
    final_df = pd.DataFrame(columns=final_columns)

    # 3. Map the data
    # Basic info
    final_df['ID TAG'] = df_to_import['ID Tag']
    final_df['COMPANY'] = df_to_import['Company']
    final_df['PRODUCT/FEATURE\\nNAME'] = df_to_import['Product Name']
    final_df['DESCRIPTION'] = df_to_import['Description']
    final_df["LINK TO DESCRIPTION ON VENDOR'S WEBSITE"] = df_to_import['Website']
    final_df['INTERNAL NOTES'] = df_to_import['AI Comments']

    # Type mapping
    final_df['Built In'] = df_to_import['Type'].apply(lambda x: 'B' if x == 'B' else '')
    final_df['AT (Installed)'] = df_to_import['Type'].apply(lambda x: 'I' if x == 'I' else '')

    # Pricing mapping
    def map_pricing(pricing_str):
        try:
            # The pricing data might be a string representation of a list
            pricing_list = ast.literal_eval(pricing_str)
            if not isinstance(pricing_list, list): return pd.Series()
        except (ValueError, SyntaxError):
            # Handle cases where it's just a string, not a list
            pricing_list = [p.strip() for p in pricing_str.split(',')]
            
        series = pd.Series(index=['FREE', 'Free Trial', 'Lifetime License', 'Subscription'], dtype=str)
        if 'Free' in pricing_list: series['FREE'] = 'F'
        if 'Free Trial' in pricing_list: series['Free Trial'] = 'F'
        if 'One-time purchase' in pricing_list: series['Lifetime License'] = 'L'
        if 'Subscription' in pricing_list: series['Subscription'] = 'S'
        return series

    pricing_mapped = df_to_import['Pricing'].apply(map_pricing)
    final_df.update(pricing_mapped)

    # Category and Platform mapping
    def map_multiselect(series, col_map):
        for col_name, letter in col_map.items():
            final_df[col_name] = series.apply(
                lambda x: letter if isinstance(x, str) and col_name in x else ''
            )

    try:
        # Categories
        category_map = {
            'Reading': 'R', 'Cognitive': 'C', 'Vision': 'V', 'Physical': 'P', 'Hearing': 'H',
            'Speech/ Communication': 'S', 'Training/ Therapy': 'T', 'Executive Function': 'E'
        }
        map_multiselect(df_to_import['Categories'], category_map)

        # Platforms - Corrected Logic to handle complex column names
        platform_map = {
            'Windows': ('Windows', 'W'),
            'Macintosh': ('Macintosh', 'M'),
            'Chromebook': ('Chromebook', 'C'),
            'iPad': ('iPad (iPadOS)', 'I'),
            'iPhone': ('iPhone (iOS)', 'I'),
            'Android': ('Android', 'A')
        }

        def process_platform_string(platform_str):
            """Processes a single platform string and returns a Series of columns to update."""
            updates = {}
            if not isinstance(platform_str, str):
                return pd.Series(updates, dtype='object')
            for search_term, (target_col, letter) in platform_map.items():
                if search_term in platform_str:
                    updates[target_col] = letter
            return pd.Series(updates)

        platform_updates_df = df_to_import['Platforms'].apply(process_platform_string)
        final_df.update(platform_updates_df)

    except Exception as e:
        print(f"Warning: Could not parse Categories or Platforms correctly. Error: {e}")

    # Fill NaNs with empty strings to match the desired output
    final_df.fillna('', inplace=True)

    # 4. Save to the output file
    final_df.to_csv(output_file, index=False)
    print(f"Successfully formatted {len(final_df)} tools. Output saved to '{output_file}'.")


def main():
    """Main function to run the formatting script."""
    print("--- Starting Final Formatting Pass ---")
    input_file = 'new_tools_complete.csv'
    output_file = 'ready_for_import.csv'
    format_for_active_tools(input_file, output_file)
    print("--- Formatting Complete ---")

if __name__ == "__main__":
    main() 