import os
if os.path.exists(".env"):
    # if we see the .env file, load it
    from dotenv import load_dotenv
    load_dotenv()

LOGIN = os.getenv('LOGIN')
PASSWORD = os.getenv('PASSWORD')
