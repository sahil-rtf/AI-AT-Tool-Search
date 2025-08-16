# AI Tool Discovery

## Prerequisites

### 1. Google Sheets API Setup

You will need to use the **Google Sheets API** to extract data from and append data to the main database.

**Setup Steps:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing project
3. Search for "Google Sheets API" and enable it
4. Head over to OAuth Consent screen and click on "Get started"
5. Fill in the details and click on "Create" to create a new app 
6. You will be redirected to the "Clients" tab automatically. If not, simply go to the "Clients" tab
7. Pick the application type as "Desktop app", keep the name as it shows by default and click on "Create"
8. A popup saying "OAuth client created" will appear on the screen, scroll down and click on the "Download JSON" option
9. Open the folder, go to the recently downloaded JSON file, and rename it to `credentials.json`
10. Copy the `credentials.json` into the `Tools Discovery/approach_1` directory

### 2. Gemini API Key Setup

You will need to obtain a **Gemini API key** to use the AI-powered tool discovery features.

**Setup Steps:**
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click on "Create API Key" to generate a new API key
4. Copy the generated API key
5. Create a `.env` file in the `Tools Discovery/approach_1` directory
6. Add your Gemini API key to the `.env` file: `GEMINI_API_KEY=your_api_key_here`
7. If you need help with the format, refer to the `.env.example` file in the same directory

### 3. Qdrant Database Setup

You will need to set up the **Qdrant** vector database running on port 6333 to store and query the discovered tools.

**Setup Steps:**

**Using Docker (Recommended):**

1. Install Docker Desktop for your operating system:
   - **Windows:** Download from [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
   - **macOS:** Download from [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
   - **Linux:** Follow the [Docker Engine installation guide](https://docs.docker.com/engine/install/)

2. Start Docker Desktop and ensure it's running

3. Open your terminal/command prompt and run the following command:

```bash
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

**Alternative Setup (Manual):**

If you prefer not to use Docker, you can download Qdrant directly:
1. Go to [Qdrant Downloads](https://qdrant.tech/documentation/guides/installation/)
2. Download the appropriate version for your operating system
3. Extract and run the Qdrant binary
4. Ensure it's configured to run on port 6333

**Verification:**
- Once running, you should be able to access the Qdrant dashboard at `http://localhost:6333/dashboard`
- The API will be available at `http://localhost:6333`

### 4. Database Access Configuration

Now we need to make sure that the email address you used in the Google Cloud Console or added while creating the app should have access to the main database.

**Access Setup:**
1. If you have access to the database with your organization's email address, you most probably won't be able to use that to create projects in Google Console or add it to the list of email addresses while creating the app. Hence, share the Google Sheet with another account which is not restricted.

2. Make sure to give "Editor" access so that we can programmatically make edits.

## Step-by-Step Guide

### Step 1: Install Dependencies

Run the requirements.txt file to download the libraries:

```bash
pip install -r requirements.txt
```

### Step 2: Run the Main Discovery Process

Execute the `run_all.ps1` script:

```powershell
.\run_all.ps1
```

This will run the following files in sequence:

#### 2.1 Data Extraction (`load_google_sheets_with_formatting.py`)

This file extracts data from the main database using the **Google Sheets API**. This should work if the prerequisites were followed correctly.

**First Time Setup:**
1. A popup window will appear asking you to log in to your Google account
2. Use the Google account that you have added to the email list or simply the one which you used for the Google Cloud Console
3. After this, a `token.json` file will be created

**Subsequent Runs:**
1. If the token expires, it will automatically generate a new token

**Functionality:**
1. Detect the rows that are struck out (i.e., no longer under consideration)
2. Generate 2 files:
   - `active_tools.csv` - contains tools that are relevant
   - `removed_tools.csv` - consists of tools that are not under consideration

#### 2.2 Web Search Discovery (`gemini_search_with_web.py`)

Once the above file is successfully run, `run_all.ps1` will automatically run this script, which does the following:

1. Uses the Gemini web search feature, where we give the model:
   - **Category** (we find tools for each category, considering it as a primary category)
   - **Definitions** for each disability category
   - **List of all tools** - this includes tools in `active_tools.csv`, `removed_tools.csv`, and `new_tools.csv` (this file would not be created when running this for the first time, but it is essential when we run this tool multiple times to find more tools, so that we don't repeat the tools we have already found)

2. Creates unique identifiers for existing tools which can help in finding duplicates and thus removing them at the start before further processing

**Output:**
- A `results` folder will be created in this directory
- A folder for each disability category will also be created
- Once Gemini finds the tools in each category, all results will be collectively stored in `new_tools.csv`

**New Columns Added:**
- `AI Verified` - set to `False` by default
- `Human Verified` - set to `unverified` by default

#### 2.3 Second Pass Processing (`second_pass.py`)

The first pass was a simple one that was to remove duplicates and hence was merged with the previous step.

**In this pass, we check/do the following:**
1. Remove all tools for which the platforms list is empty (`[]`). This is because they were non-digital products and hence are not AT tools and need to be removed. *(Note: For now there is no check for this and we are assuming this, but would like to add a check for this in the future.)*

   **Output:** `new_tools_filtered.csv`

2. Verify the categories of the tools again by doing a focused search on just the categories by providing the definition again
3. Ask Gemini to refine the descriptions if it thinks the quality of description is below 90% (we just trust Gemini for this one)
4. Request YouTube video(s) for each tool

**Output:** `new_tools_final.csv` - which changes the status of the `AI Verified` column to `True` from the previously `False` state

#### 2.4 URL Validation (`url_checker.py`)

This is like a 2.5 pass, where we are just checking the status of:
- Website links
- YouTube links (the code for YouTube links is commented out as it's broken and doesn't work correctly)

**Output:** `new_tools_with_validation.csv`

*Note: We are generating files after each process to diagnose errors later if any.*

#### 2.5 Final Processing (`third_pass.py`)

We run a final pass to:

1. Check if the model has initially added correct categories, platforms, and pricing to the format we want. For example, if the platform list in a tool consists of "FireOS", then this would be handled in this pass as we don't have any such category.
   
   *Note: We are already asking the model to give output in the supported format, but it could make errors when the input size is long and hence this pass is necessary.*

2. Fill in any missing values. We strictly ask Gemini not to make up things and write a comment when not sure.

**New Column Added:**
- `AI Comments` - comments are added, for example: "The pricing data was not found on vendor's website."

**Output:** `new_tools_complete.csv`

**End of `run_all.ps1`:** Now we need a human to manually audit each tool. Make sure to make changes only in `new_tools_complete.csv`. We have to change the status of tools in the `Human Verified` column from `unverified` to `verified` for the tools that they think are ready to be put in the main database.

**Quick Note:** When running `run_all.ps1`, we copy the contents of `new_tools_complete.csv` to `new_tools.csv`

### Step 3: Formatting and Import

Once we have made changes in `new_tools_complete.csv`, we can run the formatter.

**Execute the formatter:**
```powershell
.\formatter.ps1
```

#### 3.1 Data Formatting (`formatter.py`)

Here we simply convert the data into the format which is used by the main database (e.g., "Windows" getting mapped to "W", etc.)

**Output:** `ready_for_import.csv` - which includes only the list of tools that are both AI verified and Human verified

#### 3.2 Database Import (`append_to_google_sheets.py`)

We then simply append the tools in `ready_for_import.csv` programmatically into the main database, again by using the Google Sheets API.

The newly discovered tools are also appended to `active_tools.csv`.

#### 3.3 Vector Database Update

The script will automatically change the directory from `Tools Discovery` to `vector_database` and run `main.py`.

Now all the tools in `active_tools.csv` will be added to the Qdrant database running on port 6333.