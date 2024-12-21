from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///polls.db'
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
db = SQLAlchemy(app)

class Poll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    options = db.relationship('Option', backref='poll', lazy=True)

class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(200), nullable=False)
    votes = db.Column(db.Integer, default=0)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)

@app.route('/')
def index():
    polls = Poll.query.order_by(Poll.created_at.desc()).all()
    return render_template('index.html', polls=polls)

@app.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        question = request.form['question'].strip()
        options = [opt.strip() for opt in request.form.getlist('options') if opt.strip()]
        
        if len(question) < 5:
            flash('Question must be at least 5 characters long', 'error')
            return render_template('create.html')
        
        if len(options) < 2:
            flash('You must provide at least 2 options', 'error')
            return render_template('create.html')
            
        try:
            poll = Poll(question=question)
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

@app.route('/vote/<int:poll_id>', methods=['POST'])
def vote(poll_id):
    option_id = request.form.get('option')
    
    if not option_id:
        flash('Please select an option to vote', 'error')
        return redirect(url_for('index'))
    
    try:
        option = Option.query.get_or_404(option_id)
        option.votes += 1
        db.session.commit()
        flash('Vote recorded successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while recording your vote', 'error')
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
