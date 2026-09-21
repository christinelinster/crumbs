import os

from openai import OpenAI

from app.db.connection import pool
from app.query import process_query


def main():
    print("\nWelcome to crumbs!")
    print("You can get recipe recommendations tailored to your unique taste.")
    print("Type 'quit' at any time to exit.\n")
    print("What would you like to make today?\n")
    history = []

    with OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        timeout=60.0,
        max_retries=2,
    ) as client, pool:
        while True:
            question = input("\nUser: ")
            if question.strip().lower() == "quit":
                print("\nThanks for using crumbs. Happy eating!")
                return
            try:
                response = process_query(
                    question,
                    history,
                    client=client,
                )
            except (OSError, RuntimeError, ValueError) as error:
                print(f"\nUnable to answer: {error}")
                continue
            print("\nCrumbs:")
            print(response)

if __name__ == "__main__":
    main()
