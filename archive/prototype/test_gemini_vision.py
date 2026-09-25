import os
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

with open("limca.png", "rb") as f:
    image_bytes = f.read()

prompt = """
Look at this food product label.

Extract ONLY the complete ingredient list exactly as written on the package.

Do not analyze the ingredients.
Do not give a health verdict.
Do not summarize.
Do not include the nutrition table.

Return only:
INGREDIENTS: <ingredient list>
"""

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[
        types.Part.from_bytes(
            data=image_bytes,
            mime_type="image/png",
        ),
        prompt,
    ],
)

print(response.text)
