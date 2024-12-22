from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
from dotenv import load_dotenv
import os
import uuid

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///polls.db'
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@app.template_filter('timestamp')
def timestamp_filter(user_id):
    user = User.query.get(user_id)
    return user.created_at.strftime('%B %Y') if hasattr(user, 'created_at') else 'Unknown'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    polls = db.relationship('Poll', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

class Poll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    question = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    options = db.relationship('Option', backref='poll', lazy=True, cascade='all, delete-orphan')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    private = db.Column(db.Boolean, default=False)
    access_token = db.Column(db.String(16), unique=True)

    def reset_votes(self):
        for option in self.options:
            option.votes = 0
        Vote.query.filter(Vote.option_id.in_([opt.id for opt in self.options])).delete()

    def generate_slug(self):
        return str(uuid.uuid4())[:8]

    def generate_access_token(self):
        return os.urandom(8).hex()

    def get_share_url(self, _external=True):
        if self.private:
            return url_for('view_poll', slug=self.slug, token=self.access_token, _external=_external)
        return url_for('view_poll', slug=self.slug, _external=_external)

    @property
    def is_expired(self):
        if self.expires_at is None:
            return False
        if self.expires_at.tzinfo is None:
            aware_expires_at = self.expires_at.replace(tzinfo=timezone.utc)
        else:
            aware_expires_at = self.expires_at
        return datetime.now(timezone.utc) > aware_expires_at

class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(200), nullable=False)
    votes = db.Column(db.Integer, default=0)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey('option.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    session_id = db.Column(db.String(100), nullable=False)

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/polls')
def index():
    if current_user.is_authenticated:
        polls = Poll.query.filter(
            (Poll.private == False) | (Poll.user_id == current_user.id)
        ).order_by(Poll.created_at.desc()).all()
    else:
        polls = Poll.query.filter_by(private=False).order_by(Poll.created_at.desc()).all()
    return render_template('index.html', polls=polls)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('register.html')
        
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful!', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        
        flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        question = request.form['question'].strip()
        options = [opt.strip() for opt in request.form.getlist('options') if opt.strip()]
        expiration = request.form.get('expires_at')
        private = request.form.get('private') == 'on'
        
        if len(question) < 5:
            flash('Question must be at least 5 characters long', 'error')
            return render_template('create.html')
        
        if len(options) < 2:
            flash('You must provide at least 2 options', 'error')
            return render_template('create.html')
            
        try:
            if expiration:
                expires_at = datetime.fromisoformat(expiration).astimezone(timezone.utc)
            else:
                expires_at = None

            poll = Poll(
                question=question, 
                slug=Poll().generate_slug(),
                expires_at=expires_at,
                user_id=current_user.id,
                private=private
            )
            if private:
                poll.access_token = poll.generate_access_token()
            db.session.add(poll)
            
            for option_text in options:
                option = Option(text=option_text, poll=poll)
                db.session.add(option)
            
            db.session.commit()
            flash('Poll created successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating the poll', 'error')
            return render_template('create.html')
    
    return render_template('create.html')

@app.route('/delete/<int:poll_id>', methods=['POST'])
@login_required
def delete_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    if poll.user_id != current_user.id:
        flash('You are not authorized to delete this poll', 'error')
        return redirect(url_for('index'))
    try:
        # First delete all votes associated with this poll's options
        Vote.query.filter(Vote.option_id.in_([opt.id for opt in poll.options])).delete(synchronize_session=False)
        # Then delete the poll (will cascade delete options)
        db.session.delete(poll)
        db.session.commit()
        flash('Poll deleted successfully!', 'success')
    except Exception as e:
        print(f"Error deleting poll: {str(e)}")  # For debugging
        db.session.rollback()
        flash('An error occurred while deleting the poll', 'error')
    return redirect(url_for('index'))

@app.route('/reset/<int:poll_id>', methods=['POST'])
@login_required
def reset_votes(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    if poll.user_id != current_user.id:
        flash('You are not authorized to reset votes for this poll', 'error')
        return redirect(url_for('index'))
    try:
        poll.reset_votes()
        db.session.commit()
        flash('Votes reset successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while resetting votes', 'error')
    return redirect(url_for('index'))

@app.route('/vote/<int:poll_id>', methods=['POST'])
def vote(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    if poll.is_expired:
        flash('This poll has expired', 'error')
        return redirect(url_for('index'))

    if 'session_id' not in session:
        session['session_id'] = os.urandom(16).hex()

    option_id = request.form.get('option')
    
    if not option_id:
        flash('Please select an option to vote', 'error')
        return redirect(url_for('index'))
    
    existing_vote = Vote.query.filter_by(
        poll_id=poll_id,
        session_id=session['session_id']
    ).first()
    
    if existing_vote:
        flash('You have already voted in this poll', 'error')
        return redirect(url_for('index'))
    
    try:
        option = Option.query.get_or_404(option_id)
        option.votes += 1
        
        vote = Vote(poll_id=poll_id, option_id=option_id, session_id=session['session_id'])
        db.session.add(vote)
        
        db.session.commit()
        flash('Vote recorded successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while recording your vote', 'error')
    
    return redirect(url_for('index'))

@app.route('/poll/<string:slug>')
def view_poll(slug):
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    token = request.args.get('token')
    
    if poll.private:
        if not current_user.is_authenticated or (current_user.id != poll.user_id):
            if not token or token != poll.access_token:
                flash('This is a private poll. Please use the correct access link.', 'error')
                return redirect(url_for('index'))
    
    return render_template('poll.html', poll=poll)

@app.route('/poll/<int:poll_id>/details')
@login_required
def poll_details(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    total_votes = sum(option.votes for option in poll.options)
    return render_template('poll_details.html', poll=poll, total_votes=total_votes)

@app.route('/profile')
@login_required
def profile():
    user_polls = Poll.query.filter_by(user_id=current_user.id).order_by(Poll.created_at.desc()).all()
    active_polls = [poll for poll in user_polls if not poll.is_expired]
    
    total_votes = 0
    for poll in user_polls:
        for option in poll.options:
            total_votes += option.votes
            
    return render_template('profile.html', 
                         user_polls=user_polls,
                         active_polls=active_polls,
                         total_votes=total_votes)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run()
