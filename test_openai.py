import os
from dotenv import load_dotenv
from openai import OpenAI

# --- Step 1: Load environment variables from .env file ---
print("Attempting to load .env file...")
load_dotenv()
print(".env file loaded.")

# --- Step 2: Get the API Key ---
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("\n--- ❌ ERROR ---")
    print("Could not find the OPENAI_API_KEY in your .env file.")
    print("Please make sure the variable is set correctly.")
    exit()

print(f"API Key found, starting with: {api_key[:7]}...")

# --- Step 3: Try to use the API Key ---
try:
    print("Initializing OpenAI client...")
    client = OpenAI(api_key=api_key)
    
    print("Sending a test request to OpenAI...")
    completion = client.chat.completions.create(
      model="gpt-4o-mini",
      messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
      ]
    )
    
    print("\n--- ✅ SUCCESS! ---")
    print("Your OpenAI API key is working correctly.")
    print("Test response received:", completion.choices[0].message.content)

except Exception as e:
    print("\n--- ❌ ERROR ---")
    print("The test request to OpenAI failed.")
    print("This is the error message from OpenAI:")
    print("-" * 20)
    print(e)
    print("-" * 20)
    print("\nCommon reasons for this error include:")
    print("1. Your API key is incorrect or has been revoked.")
    print("2. Your OpenAI account has no payment method or has run out of credits.")

