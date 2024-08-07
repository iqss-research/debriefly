import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # OPENAI_API_KEY

client = OpenAI(
    organization=os.environ["OPENAI_ORG_ID"],
    project=os.environ["OPENAI_PROJECT_ID"],
)

completion = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You answer all questions in two words"},
        {
            "role": "assistant",
            "content": "Please ask me a question and I will reply in two words.",
        },
        {"role": "user", "content": "What is the capital of France?"},
    ],
)

print(completion.choices[0].message)
