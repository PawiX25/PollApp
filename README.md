# PollApp

PollApp is a simple polling application built with Flask and SQLAlchemy. Create polls with multiple options, allow users to vote, and share results quickly.

## Features

- Create polls with multiple options.
- Optional expiration date for polls.
- Real-time vote counting.
- Lightweight & easy to set up.
- Password protection for individual polls
- Private polls with special access links
- User authentication and profiles
- Vote tracking to prevent multiple votes
- Real-time vote statistics and charts
- Mobile-responsive design using Tailwind CSS
- Poll management (reset votes, delete polls)
- Poll expiration system
- Detailed poll analytics for creators
- Detailed analytics with Chart.js visualizations
- Duplicate polls as templates
- Custom poll URLs
- Session-based voting system
- Password protection for individual polls
- Poll expiration settings
- Multiple choice voting option
- Mobile-responsive navigation
- Toast notifications system
- Animated UI elements
- Rich poll management interface
- User profile with statistics

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

### Creating Polls

- Visit `/create` to create a new poll
- Add multiple options (2-10 choices)
- Optional settings:
  - Set an expiration date/time
  - Make poll private with special access link
  - Add password protection
  - Track votes per session

### Managing Polls

- View your polls in the profile dashboard
- See total votes and active polls
- Reset votes or delete polls
- Share polls via generated links
- View detailed poll statistics with charts

### Security Features

- Session-based voting prevention
- Password protection for sensitive polls
- Private polls accessible only via special links
- User authentication for poll management

## Dependencies

- Flask
- SQLAlchemy
- Flask-Login
- Werkzeug
- python-dotenv
- Chart.js (for visualizations)
- Tailwind CSS (for styling)

## Contact

For suggestions or inquiries, please open an issue on GitHub:
[PollApp Issues](https://github.com/PawiX25/PollApp/issues)