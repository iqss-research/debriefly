from dotenv import load_dotenv
from debriefly.openai import chat


if __name__ == "__main__":
    load_dotenv()

    completion = chat(
        user_input="Why did the chicken cross the road?",
        chat_history=[],
        system_message="You are an AI assistant that answers all questions in two words.",
    )
    for chunk in completion:
        print(chunk, end="")
