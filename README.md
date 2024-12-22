# PollApp

PollApp is a simple polling application built with Flask and SQLAlchemy. Create polls with multiple options, allow users to vote, and share results quickly.

## Features

- Create polls with multiple options.
- Optional expiration date for polls.
- Real-time vote counting.
- Lightweight & easy to set up.

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/PawiX25/PollApp.git
   ```
2. Change into the project directory:
   ```
   cd PollApp
   ```
3. Install dependencies (consider using a virtual environment):
   ```
   pip install -r requirements.txt
   ```
4. (Optional) Create a .env file and set the FLASK_SECRET_KEY:
   ```
   FLASK_SECRET_KEY='<your_secret_key>'
   ```

## Usage

1. Initialize the database:
   ```bash
   flask shell
   >>> from app import db
   >>> db.create_all()
   >>> exit()
   ```
2. Run the development server:
   ```
   flask run
   ```
3. Access the app at:
   ```
   http://127.0.0.1:5000/
   ```
4. Visit /polls for the list of polls or /create to create a new poll.

## Contact

For suggestions or inquiries, please open an issue on GitHub:
[PollApp Issues](https://github.com/PawiX25/PollApp/issues)