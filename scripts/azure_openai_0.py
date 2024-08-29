import os
import requests
from dotenv import load_dotenv

if __name__ == "__main__":

    load_dotenv()

    AZURE_OPENAI_API_KEY = os.environ["AZURE_OPENAI_API_KEY"]
    AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]

    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_API_KEY,
    }

    # Payload for the request
    payload = {
        "messages": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": "You are an AI assistant that answers all questions in two words.",
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Why did the chicken cross the road?"}
                ],
            },
        ]
    }

    try:
        response = requests.post(AZURE_OPENAI_ENDPOINT, headers=headers, json=payload)
        response.raise_for_status()
    except requests.RequestException as e:
        raise SystemExit(f"Failed to make the request. Error: {e}")

    response_dict = response.json()
    message = response_dict["choices"][0]["message"]["content"]

    print(message)
