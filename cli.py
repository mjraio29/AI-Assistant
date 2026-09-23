"""
Terminal chat client. Run:
    python cli.py
"""
import sys
import uuid

from app.groq_client import chat


def main():
    session_id = str(uuid.uuid4())
    print("Robert is ready. Type 'exit' to quit.\n")
    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_input.lower() in ("exit", "quit"):
            break
        if not user_input:
            continue
        try:
            reply = chat(session_id, user_input)
        except RuntimeError as e:
            print(f"[config error] {e}")
            sys.exit(1)
        print(f"assistant> {reply}\n")


if __name__ == "__main__":
    main()
