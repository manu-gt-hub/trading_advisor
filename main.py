import os

def main():
    secret = os.getenv("SECRET_TEST")
    print(f"El secret es: {secret}")

if __name__ == "__main__":
    main()
