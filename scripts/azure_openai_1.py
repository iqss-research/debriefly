import os
from dotenv import load_dotenv
from openai import AzureOpenAI


if __name__ == "__main__":

    load_dotenv()

    # gets the API Key from environment variable AZURE_OPENAI_API_KEY
    client = AzureOpenAI(
        # https://learn.microsoft.com/azure/ai-services/openai/reference#rest-api-versioning
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        # https://learn.microsoft.com/azure/cognitive-services/openai/how-to/create-resource?pivots=web-portal#create-a-resource
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    )

    completion = client.chat.completions.create(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_MODEL"],
        messages=[
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
        ],
        stream=True,
    )

    for chunk in completion:
        if chunk.choices:
            delta = chunk.choices[0].delta.content
            if delta:
                print(delta, end="")

    print("\ndone")
