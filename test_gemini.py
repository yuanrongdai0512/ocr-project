import json
from google import genai
from google.genai import types

def test_gemini():
    api_key = "AIzaSyDWIR4d3HxlL-ADdgjYhDJHckz41udT4pQ"
    client = genai.Client(api_key=api_key)
    
    # We will use gemini-2.5-flash as it is fast and supports JSON response mime type natively
    # If 2.5 is not available, 1.5 is also okay, let's use gemini-1.5-flash
    model = 'gemini-1.5-flash'
    
    system_prompt = "You are a helpful assistant. Reply strictly in JSON format with a single key 'message'."
    user_prompt = "Say hello to the user."
    
    try:
        response = client.models.generate_content(
            model=model,
            contents=system_prompt + "\n\n" + user_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        print("Success!")
        print("Response:", response.text)
        print("Parsed JSON:", json.loads(response.text))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_gemini()
