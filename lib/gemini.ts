import { GoogleGenerativeAI } from "@google/generative-ai";

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY || "");

export function getModel(modelName = "gemini-2.0-flash") {
  return genAI.getGenerativeModel({ model: modelName });
}

export async function generateContent(prompt: string): Promise<string> {
  const model = getModel();
  const result = await model.generateContent(prompt);
  return result.response.text();
}

export async function discoverToolsForCategory(
  category: string,
  existingTools: string[] = []
): Promise<string> {
  const prompt = `You are an expert in Assistive Technology (AT) tools. Search for AT tools in the category: "${category}"

${existingTools.length > 0 ? `IMPORTANT: Skip these tools that have already been found:\n${existingTools.join(", ")}\n` : ""}

Find 5-10 NEW assistive technology tools that help people with disabilities.

For each tool found, provide ONLY a JSON array with the following structure (no markdown, no explanation, just the JSON array):
[
  {
    "name": "Tool Name",
    "description": "Brief description of what the tool does and who it helps",
    "category": "${category}",
    "website": "https://example.com",
    "pricing": "Free" | "Paid" | "Freemium",
    "platforms": ["iOS", "Android", "Web", "Windows", "Mac"]
  }
]

Requirements:
- Only include real, currently available tools
- Verify the website URL is correct
- Include a mix of free and paid options
- Focus on tools that are actually helpful for people with disabilities
- Return ONLY the JSON array, no additional text`;

  return generateContent(prompt);
}

export async function validateAndEnrichTool(tool: {
  name: string;
  description: string;
  category: string;
  website: string;
  pricing: string;
  platforms: string[];
}): Promise<string> {
  const prompt = `Verify and enrich this assistive technology tool information:

Tool: ${tool.name}
Website: ${tool.website}
Current Description: ${tool.description}
Category: ${tool.category}
Pricing: ${tool.pricing}
Platforms: ${tool.platforms.join(", ")}

Please verify:
1. Is this a real assistive technology tool?
2. Is the category correct?
3. Is the pricing information accurate?
4. What platforms does it actually support?

Return ONLY a JSON object (no markdown, no explanation):
{
  "isValid": true/false,
  "name": "Corrected name if needed",
  "description": "Improved 2-3 sentence description",
  "category": "Corrected category if needed",
  "website": "Corrected URL if needed",
  "pricing": "Free" | "Paid" | "Freemium",
  "platforms": ["iOS", "Android", "Web", "Windows", "Mac"],
  "reason": "Brief explanation if invalid"
}`;

  return generateContent(prompt);
}

export async function findYouTubeVideo(toolName: string, category: string): Promise<string> {
  const prompt = `Find a YouTube tutorial or demo video for the assistive technology tool "${toolName}" (category: ${category}).

Search for videos that:
- Demonstrate how to use the tool
- Show accessibility features
- Are from official channels or reputable sources

Return ONLY a JSON object (no markdown):
{
  "found": true/false,
  "videoUrl": "https://youtube.com/watch?v=...",
  "videoTitle": "Video title"
}

If no relevant video is found, return:
{
  "found": false,
  "videoUrl": null,
  "videoTitle": null
}`;

  return generateContent(prompt);
}
