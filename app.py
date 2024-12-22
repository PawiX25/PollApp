from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
from dotenv import load_dotenv
import os
import uuid

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///polls.db'
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
db = SQLAlchemy(app)

class Poll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    question = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    options = db.relationship('Option', backref='poll', lazy=True, cascade='all, delete-orphan')

    def reset_votes(self):
        for option in self.options:
            option.votes = 0
        Vote.query.filter(Vote.option_id.in_([opt.id for opt in self.options])).delete()

    def generate_slug(self):
        return str(uuid.uuid4())[:8]

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
    option_id = db.Column(db.Integer, db.ForeignKey('option.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    session_id = db.Column(db.String(100), nullable=False)

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/polls')
def index():
    polls = Poll.query.order_by(Poll.created_at.desc()).all()
    return render_template('index.html', polls=polls)

@app.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        question = request.form['question'].strip()
        options = [opt.strip() for opt in request.form.getlist('options') if opt.strip()]
        expiration = request.form.get('expires_at')
        
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
                expires_at=expires_at
            )
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
def delete_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
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
def reset_votes(poll_id):
    poll = Poll.query.get_or_404(poll_id)
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
        option_id=option_id,
        session_id=session['session_id']
    ).first()
    
    if existing_vote:
        flash('You have already voted in this poll', 'error')
        return redirect(url_for('index'))
    
    try:
        option = Option.query.get_or_404(option_id)
        option.votes += 1
        
        vote = Vote(option_id=option_id, session_id=session['session_id'])
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
    return render_template('poll.html', poll=poll)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run()
