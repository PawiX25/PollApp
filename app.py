from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
from dotenv import load_dotenv
import os
import uuid
from werkzeug.utils import secure_filename
from pathlib import Path
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import json
from sqlalchemy.orm import validates

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///polls.db'
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
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
    surveys = db.relationship('Survey', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_extension(filename):
    return Path(filename).suffix

def generate_image_filename(original_filename):
    """Generate a clean filename while preserving the original extension"""
    clean_filename = str(Path(f"{uuid.uuid4()}{get_file_extension(original_filename)}")).replace('\\', '/')
    return clean_filename

class Survey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    start_date = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    private = db.Column(db.Boolean, default=False)
    access_token = db.Column(db.String(16), unique=True)
    password_hash = db.Column(db.String(200), nullable=True)
    image_path = db.Column(db.String(200))
    questions = db.relationship('Poll', backref='survey', lazy=True, cascade='all, delete-orphan')

    def generate_slug(self):
        return str(uuid.uuid4())[:8]

    def generate_access_token(self):
        return os.urandom(8).hex()

    def get_share_url(self, _external=True):
        if self.private:
            return url_for('view_survey', slug=self.slug, token=self.access_token, _external=_external)
        return url_for('view_survey', slug=self.slug, _external=_external)

class Poll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    question = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    start_date = db.Column(db.DateTime, nullable=True)
    options = db.relationship('Option', backref='poll', lazy=True, cascade='all, delete-orphan')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    private = db.Column(db.Boolean, default=False)
    access_token = db.Column(db.String(16), unique=True)
    password_hash = db.Column(db.String(200), nullable=True)
    multiple_votes = db.Column(db.Boolean, default=False)
    image_path = db.Column(db.String(200))
    question_type = db.Column(db.String(20), default='mcq')
    rating_scale = db.Column(db.Integer, default=5)
    survey_id = db.Column(db.Integer, db.ForeignKey('survey.id'), nullable=True)
    order = db.Column(db.Integer, default=0)

    @validates('slug')
    def validate_slug(self, key, slug):
        if not slug:
            return self.generate_slug()
        return slug

    @property
    def is_mcq(self):
        return self.question_type == 'mcq'
    
    @property
    def is_rating(self):
        return self.question_type == 'rating'
    
    @property
    def is_text(self):
        return self.question_type == 'text'

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

    def set_password(self, password):
        if password:
            self.password_hash = generate_password_hash(password)
        else:
            self.password_hash = None

    def check_password(self, password):
        if not self.password_hash:
            return True
        return check_password_hash(self.password_hash, password)

    @property
    def is_expired(self):
        if self.expires_at is None:
            return False
        if self.expires_at.tzinfo is None:
            aware_expires_at = self.expires_at.replace(tzinfo=timezone.utc)
        else:
            aware_expires_at = self.expires_at
        return datetime.now(timezone.utc) > aware_expires_at

    def delete_image(self):
        if self.image_path:
            try:
                file_path = Path(app.root_path) / 'static' / self.image_path
                if file_path.exists():
                    file_path.unlink()
                self.image_path = None
            except OSError:
                pass

    @property
    def active_state(self):
        now = datetime.now(timezone.utc)
        
        if self.start_date and self.start_date.replace(tzinfo=timezone.utc) > now:
            return 'scheduled'
        elif self.is_expired:
            return 'expired'
        else:
            return 'active'

    @property
    def is_active(self):
        now = datetime.now(timezone.utc)
        if self.start_date and self.start_date.replace(tzinfo=timezone.utc) > now:
            return False
        return not self.is_expired

class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(200), nullable=False)
    votes = db.Column(db.Integer, default=0)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
    text_answers = db.relationship('TextAnswer', backref='option', lazy=True, cascade='all, delete-orphan')
    rating_votes = db.relationship('RatingVote', backref='option', lazy=True, cascade='all, delete-orphan')

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey('option.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    session_id = db.Column(db.String(100), nullable=False)

class TextAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey('option.id'), nullable=False)
    session_id = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class RatingVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rating = db.Column(db.Integer, nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey('option.id'), nullable=False)
    session_id = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    if current_user.is_authenticated:
        polls = Poll.query.filter_by(user_id=current_user.id, survey_id=None).order_by(Poll.created_at.desc()).all()
        surveys = Survey.query.filter_by(user_id=current_user.id).order_by(Survey.created_at.desc()).all()
        return render_template('index.html', polls=polls, surveys=surveys)
    return redirect(url_for('login'))

@app.route('/polls')
def landing():
    return render_template('landing.html')

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
        question_type = request.form.get('question_type', 'mcq')
        rating_scale = int(request.form.get('rating_scale', 5))
        expiration = request.form.get('expires_at')
        private = request.form.get('private') == 'on'
        password = request.form.get('password')
        start_date = request.form.get('start_date')
        
        options = []
        if question_type == 'mcq':
            options = [opt.strip() for opt in request.form.getlist('options') if opt.strip()]
            if len(options) < 2:
                flash('You must provide at least 2 options for multiple choice questions', 'error')
                return render_template('create.html')

        multiple_votes = (
            question_type == 'mcq' and 
            request.form.get('selection_type') == 'multiple'
        )

        try:
            if expiration:
                expires_at = datetime.fromisoformat(expiration).astimezone(timezone.utc)
            else:
                expires_at = None

            if start_date:
                start_date = datetime.fromisoformat(start_date).astimezone(timezone.utc)
            else:
                start_date = None

            image = request.files.get('image')
            image_path = None
            if image and allowed_file(image.filename):
                filename = generate_image_filename(image.filename)
                upload_path = Path(app.root_path) / 'static' / 'uploads'
                upload_path.mkdir(exist_ok=True)
                image.save(upload_path / filename)
                image_path = f'uploads/{filename}'

            poll = Poll(
                question=question, 
                slug=Poll().generate_slug(),
                expires_at=expires_at,
                start_date=start_date,
                user_id=current_user.id,
                private=private,
                multiple_votes=multiple_votes,
                image_path=image_path,
                question_type=question_type,
                rating_scale=rating_scale
            )
            
            if question_type == 'mcq':
                for option_text in options:
                    option = Option(text=option_text, poll=poll)
                    db.session.add(option)
            else:
                option = Option(text='Responses', poll=poll)
                db.session.add(option)

            db.session.add(poll)
            db.session.commit()
            flash('Poll created successfully!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            print(f"Error creating poll: {str(e)}")
            db.session.rollback()
            flash('An error occurred while creating the poll', 'error')
            return render_template('create.html')
    
    return render_template('create.html')

@app.route('/create/survey', methods=['GET', 'POST'])
@login_required
def create_survey():
    if request.method == 'POST':
        try:
            title = request.form['title'].strip()
            description = request.form.get('description', '').strip()
            questions_data = json.loads(request.form['questions'])
            
            for q_data in questions_data:
                if q_data['type'] == 'mcq':
                    valid_options = [opt for opt in q_data['options'] if opt.strip()]
                    if len(valid_options) < 2:
                        flash('Multiple choice questions must have at least 2 options', 'error')
                        return render_template('create_survey.html')
            
            survey = Survey(
                title=title,
                description=description,
                slug=Survey().generate_slug(),
                user_id=current_user.id
            )

            for i, q_data in enumerate(questions_data):
                poll = Poll(
                    question=q_data['question'],
                    user_id=current_user.id,
                    question_type=q_data['type'],
                    rating_scale=q_data.get('rating_scale', 5),
                    multiple_votes=q_data.get('multiple_votes', False),
                    order=i,
                    slug=str(uuid.uuid4())[:8]
                )

                if q_data['type'] == 'mcq':
                    valid_options = [opt for opt in q_data['options'] if opt.strip()]
                    for option_text in valid_options:
                        option = Option(text=option_text)
                        poll.options.append(option)
                else:
                    option = Option(text='Responses')
                    poll.options.append(option)

                survey.questions.append(poll)

            db.session.add(survey)
            db.session.commit()
            flash('Survey created successfully!', 'success')
            return redirect(url_for('survey_details', survey_id=survey.id))

        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating the survey', 'error')
            print(f"Error: {str(e)}")
            return render_template('create_survey.html')

    return render_template('create_survey.html')

@app.route('/delete/<int:poll_id>', methods=['POST'])
@login_required
def delete_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    if poll.user_id != current_user.id:
        flash('You are not authorized to delete this poll', 'error')
        return redirect(url_for('index'))
    try:
        poll.delete_image()
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

    try:
        if poll.is_mcq:
            if poll.multiple_votes:
                option_ids = request.form.getlist('options[]')
            else:
                option_id = request.form.get('options')
                option_ids = [option_id] if option_id else []
                
            if not option_ids:
                flash('Please select an option', 'error')
                return redirect(url_for('poll', slug=poll.slug))
            
            if not poll.multiple_votes and len(option_ids) > 1:
                flash('This poll only allows voting for one option', 'error')
                return redirect(url_for('index'))
            
            existing_vote = Vote.query.filter_by(
                poll_id=poll_id,
                session_id=session['session_id']
            ).first()
            
            if existing_vote:
                flash('You have already voted in this poll', 'error')
                return redirect(url_for('index'))
            
            for option_id in option_ids:
                option = Option.query.get_or_404(option_id)
                if option.poll_id != poll_id:
                    raise ValueError("Invalid option for this poll")
                option.votes += 1
                
                vote = Vote(poll_id=poll_id, option_id=option_id, session_id=session['session_id'])
                db.session.add(vote)
        elif poll.is_rating:
            rating = int(request.form.get('rating'))
            option = poll.options[0]
            vote = RatingVote(rating=rating, option=option, session_id=session['session_id'])
            db.session.add(vote)
        elif poll.is_text:
            text_answer = request.form.get('text_answer').strip()
            if text_answer:
                option = poll.options[0]
                answer = TextAnswer(text=text_answer, option=option, session_id=session['session_id'])
                db.session.add(answer)
        
        db.session.commit()
        flash('Response recorded successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while recording your response', 'error')
    
    return redirect(url_for('index'))

@app.route('/poll/<string:slug>')
def view_poll(slug):
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    
    if not poll.is_active:
        if poll.active_state == 'scheduled':
            flash('This poll has not started yet.', 'error')
        else:
            flash('This poll has expired.', 'error')
        return redirect(url_for('index'))
    
    token = request.args.get('token')
    
    if poll.private:
        if not current_user.is_authenticated or (current_user.id != poll.user_id):
            if not token or token != poll.access_token:
                flash('This is a private poll. Please use the correct access link.', 'error')
                return redirect(url_for('index'))
    
    if poll.password_hash and 'poll_access_' + str(poll.id) not in session:
        return redirect(url_for('verify_poll_password', slug=slug))
    
    return render_template('poll.html', poll=poll)

@app.route('/poll/<string:slug>/verify', methods=['GET', 'POST'])
def verify_poll_password(slug):
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    
    if request.method == 'POST':
        password = request.form.get('password')
        if poll.check_password(password):
            session['poll_access_' + str(poll.id)] = True
            return redirect(url_for('view_poll', slug=slug))
        flash('Incorrect password', 'error')
    
    return render_template('verify_password.html', poll=poll)

@app.route('/poll/<int:poll_id>/details')
@login_required
def poll_details(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    total_votes = sum(option.votes for option in poll.options)
    return render_template('poll_details.html', poll=poll, total_votes=total_votes)

@app.route('/poll/<int:poll_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    if poll.user_id != current_user.id:
        flash('You are not authorized to edit this poll', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        question = request.form['question'].strip()
        options = [opt.strip() for opt in request.form.getlist('options') if opt.strip()]
        expiration = request.form.get('expires_at')
        private = request.form.get('private') == 'on'
        password = request.form.get('password')
        multiple_votes = request.form.get('multiple_votes') == 'true'
        
        if len(question) < 5:
            flash('Question must be at least 5 characters long', 'error')
            return render_template('edit_poll.html', poll=poll)
        
        if len(options) < 2:
            flash('You must provide at least 2 options', 'error')
            return render_template('edit_poll.html', poll=poll)
            
        try:
            if expiration:
                expires_at = datetime.fromisoformat(expiration).astimezone(timezone.utc)
            else:
                expires_at = None

            poll.question = question
            poll.expires_at = expires_at
            poll.private = private
            poll.multiple_votes = multiple_votes
            poll.set_password(password)

            image = request.files.get('image')
            if image and allowed_file(image.filename):
                poll.delete_image()
                
                filename = generate_image_filename(image.filename)
                upload_path = Path(app.root_path) / 'static' / 'uploads'
                upload_path.mkdir(exist_ok=True)
                image.save(upload_path / filename)
                poll.image_path = f'uploads/{filename}'
            elif request.form.get('remove_image'):
                poll.delete_image()
            
            if private and not poll.access_token:
                poll.access_token = poll.generate_access_token()
            
            existing_options = {opt.id: opt for opt in poll.options}
            option_ids = request.form.getlist('option_ids')
            
            for i, text in enumerate(options):
                if i < len(option_ids) and option_ids[i]:
                    opt_id = int(option_ids[i])
                    if opt_id in existing_options:
                        existing_options[opt_id].text = text
                else:
                    new_option = Option(text=text, poll=poll)
                    db.session.add(new_option)
            
            for opt_id, option in existing_options.items():
                if str(opt_id) not in option_ids:
                    db.session.delete(option)
            
            db.session.commit()
            flash('Poll updated successfully!', 'success')
            return redirect(url_for('poll_details', poll_id=poll.id))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the poll', 'error')
            return render_template('edit_poll.html', poll=poll)
    
    return render_template('edit_poll.html', poll=poll)

@app.route('/poll/<int:poll_id>/duplicate')
@login_required
def duplicate_poll(poll_id):
    original_poll = Poll.query.get_or_404(poll_id)
    
    try:
        new_poll = Poll(
            question=f"Copy of {original_poll.question}",
            slug=Poll().generate_slug(),
            user_id=current_user.id,
            private=original_poll.private
        )
        
        if new_poll.private:
            new_poll.access_token = new_poll.generate_access_token()
        
        for option in original_poll.options:
            new_option = Option(text=option.text, votes=0)
            new_poll.options.append(new_option)
        
        db.session.add(new_poll)
        db.session.commit()
        
        flash('Poll duplicated successfully! You can now edit it.', 'success')
        return redirect(url_for('edit_poll', poll_id=new_poll.id))
    
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while duplicating the poll', 'error')
        return redirect(url_for('poll_details', poll_id=poll_id))

@app.route('/profile')
@login_required
def profile():
    polls = Poll.query.filter_by(user_id=current_user.id, survey_id=None).order_by(Poll.created_at.desc()).all()
    surveys = Survey.query.filter_by(user_id=current_user.id).order_by(Survey.created_at.desc()).all()
    active_polls = [poll for poll in polls if not poll.is_expired]
    
    total_votes = sum(sum(option.votes for option in poll.options) for poll in polls)
    
    return render_template('profile.html',
                         user_polls=polls,
                         active_polls=active_polls,
                         surveys=surveys,
                         total_votes=total_votes)

@app.route('/poll/<int:poll_id>/download')
@login_required
def download_results(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    if poll.user_id != current_user.id:
        flash('You are not authorized to download these results', 'error')
        return redirect(url_for('index'))

    return download_pdf(poll)

def download_pdf(poll):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    elements.append(Paragraph(f"Poll Results: {poll.question}", styles['Title']))
    elements.append(Paragraph(f"Created: {poll.created_at.strftime('%Y-%m-%d %H:%M UTC')}", styles['Normal']))
    elements.append(Paragraph(f"Status: {'Expired' if poll.is_expired else 'Active'}", styles['Normal']))
    
    total_votes = sum(option.votes for option in poll.options)
    
    data = [['Option', 'Votes', 'Percentage']]
    for option in poll.options:
        percentage = (option.votes / total_votes * 100) if total_votes > 0 else 0
        data.append([option.text, str(option.votes), f'{percentage:.1f}%'])
    
    data.append(['Total', str(total_votes), '100%'])
    
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.black),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'poll_results_{poll.id}.pdf'
    )

def create_preview_poll(form_data):
    """Creates a temporary poll object for preview without saving to database"""
    question = form_data['question'].strip()
    question_type = form_data.get('question_type', 'mcq')
    rating_scale = int(form_data.get('rating_scale', 5))
    multiple_votes = (
        question_type == 'mcq' and 
        form_data.get('selection_type') == 'multiple'
    )
    
    poll = Poll(
        question=question,
        slug='preview',
        user_id=current_user.id if current_user.is_authenticated else None,
        private=form_data.get('private') == 'on',
        multiple_votes=multiple_votes,
        question_type=question_type,
        rating_scale=rating_scale
    )
    
    if question_type == 'mcq':
        options = [opt.strip() for opt in form_data.getlist('options') if opt.strip()]
        for option_text in options:
            option = Option(text=option_text, poll=poll)
            poll.options.append(option)
    else:
        option = Option(text='Responses', poll=poll)
        poll.options.append(option)
    
    image = request.files.get('image')
    if image and allowed_file(image.filename):
        filename = generate_image_filename(image.filename)
        upload_path = Path(app.root_path) / 'static' / 'uploads' / 'preview'
        upload_path.mkdir(exist_ok=True)
        image.save(upload_path / filename)
        poll.image_path = f'uploads/preview/{filename}'
    
    return poll

@app.route('/preview', methods=['POST'])
def preview_poll():
    try:
        poll = create_preview_poll(request.form)
        if not poll:
            flash('Invalid poll data', 'error')
            return redirect(url_for('create'))
        
        session['preview_poll'] = {
            'question': poll.question,
            'question_type': poll.question_type,
            'rating_scale': poll.rating_scale,
            'multiple_votes': poll.multiple_votes,
            'options': [opt.text for opt in poll.options],
            'image_path': poll.image_path
        }
        
        return render_template('poll.html', poll=poll, preview_mode=True)
        
    except Exception as e:
        flash('An error occurred while generating preview', 'error')
        return redirect(url_for('create'))

@app.route('/survey/<string:slug>')
def view_survey(slug):
    survey = Survey.query.filter_by(slug=slug).first_or_404()
     questions = sorted(survey.questions, key=lambda x: x.order)
    return render_template('survey.html', survey=survey, questions=questions)

@app.route('/survey/<string:slug>/submit', methods=['POST'])
def submit_survey(slug):
    survey = Survey.query.filter_by(slug=slug).first_or_404()
    questions = sorted(survey.questions, key=lambda x: x.order)
    
    if 'session_id' not in session:
        session['session_id'] = os.urandom(16).hex()
    
    try:
        for question in questions:
            answer_data = request.form.get(f'answers[{question.id}]')
            if not answer_data and not isinstance(answer_data, list):
                answer_data = request.form.getlist(f'answers[{question.id}][]')
            
            if question.is_mcq:
                option_ids = answer_data if isinstance(answer_data, list) else [answer_data]
                for option_id in option_ids:
                    option = Option.query.get_or_404(option_id)
                    option.votes += 1
                    vote = Vote(
                        poll_id=question.id,
                        option_id=option_id,
                        session_id=session['session_id']
                    )
                    db.session.add(vote)
                    
            elif question.is_rating:
                rating = int(answer_data)
                vote = RatingVote(
                    rating=rating,
                    option_id=question.options[0].id,
                    session_id=session['session_id']
                )
                db.session.add(vote)
                
            elif question.is_text:
                text = answer_data.strip()
                if text:
                    answer = TextAnswer(
                        text=text,
                        option_id=question.options[0].id,
                        session_id=session['session_id']
                    )
                    db.session.add(answer)
        
        db.session.commit()
        flash('Thank you for completing the survey!', 'success')
        return redirect(url_for('view_survey', slug=survey.slug))
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while submitting your responses', 'error')
        print(f"Error submitting survey: {str(e)}")
        return redirect(url_for('view_survey', slug=survey.slug))

@app.route('/survey/<int:survey_id>/details')
@login_required
def survey_details(survey_id):
    survey = Survey.query.get_or_404(survey_id)
    if survey.user_id != current_user.id:
        flash('You are not authorized to view these results', 'error')
        return redirect(url_for('index'))
    
    questions = sorted(survey.questions, key=lambda x: x.order)
    
    total_responses = 0
    questions_stats = []
    
    for question in questions:
        if question.is_mcq:
            responses = sum(option.votes for option in question.options)
            total_votes = responses
            options_data = [{
                'text': option.text,
                'votes': option.votes,
                'percentage': (option.votes / total_votes * 100) if total_votes > 0 else 0
            } for option in question.options]
            
        elif question.is_rating:
            ratings = [vote.rating for vote in question.options[0].rating_votes]
            responses = len(ratings)
            avg_rating = sum(ratings) / len(ratings) if ratings else 0
            options_data = {
                'average': avg_rating,
                'total_ratings': responses,
                'distribution': {i: ratings.count(i) for i in range(1, question.rating_scale + 1)}
            }
            
        elif question.is_text:
            responses = len(question.options[0].text_answers)
            options_data = [{
                'text': answer.text,
                'timestamp': answer.timestamp
            } for answer in question.options[0].text_answers]
        
        total_responses = max(total_responses, responses)
        questions_stats.append({
            'question': question,
            'responses': responses,
            'data': options_data
        })
    
    completion_rate = round((sum(q['responses'] for q in questions_stats) / 
                           (len(questions) * total_responses) * 100) if total_responses > 0 else 0)
    
    return render_template('survey_details.html',
                         survey=survey,
                         questions=questions_stats,
                         total_responses=total_responses,
                         completion_rate=completion_rate)

@app.route('/survey/<int:survey_id>/results')
@login_required
def survey_results(survey_id):
    survey = Survey.query.get_or_404(survey_id)
    if survey.user_id != current_user.id:
        flash('You are not authorized to view these results', 'error')
        return redirect(url_for('index'))
    
    questions = sorted(survey.questions, key=lambda x: x.order)
    
    total_responses = 0
    completed_responses = 0
    
    if questions:
        for question in questions:
            if question.is_mcq:
                responses = sum(option.votes for option in question.options)
            elif question.is_rating:
                responses = len(question.options[0].rating_votes)
            else:
                responses = len(question.options[0].text_answers)
            total_responses = max(total_responses, responses)
            completed_responses += responses
        
        completion_rate = round((completed_responses / (len(questions) * total_responses)) * 100 if total_responses > 0 else 0)
    else:
        total_responses = 0
        completion_rate = 0
    
    return render_template('survey_results.html', 
                         survey=survey, 
                         questions=questions,
                         total_responses=total_responses,
                         completion_rate=completion_rate)

@app.route('/survey/<int:survey_id>/download')
@login_required
def download_survey_results(survey_id):
    survey = Survey.query.get_or_404(survey_id)
    if survey.user_id != current_user.id:
        flash('You are not authorized to download these results', 'error')
        return redirect(url_for('index'))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    elements.append(Paragraph(f"Survey Results: {survey.title}", styles['Title']))
    if survey.description:
        elements.append(Paragraph(survey.description, styles['Normal']))
    elements.append(Spacer(1, 12))
    
    for i, question in enumerate(sorted(survey.questions, key=lambda x: x.order), 1):
        elements.append(Paragraph(f"Question {i}: {question.question}", styles['Heading2']))
        
        if question.is_mcq:
            data = [['Option', 'Votes', 'Percentage']]
            total_votes = sum(opt.votes for opt in question.options)
            
            for option in question.options:
                percentage = (option.votes / total_votes * 100) if total_votes > 0 else 0
                data.append([option.text, str(option.votes), f'{percentage:.1f}%'])
            
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
            
        elif question.is_rating:
            ratings = [vote.rating for vote in question.options[0].rating_votes]
            if ratings:
                avg_rating = sum(ratings) / len(ratings)
                elements.append(Paragraph(f"Average Rating: {avg_rating:.1f}", styles['Normal']))
                
                data = [['Rating', 'Count', 'Percentage']]
                for i in range(1, question.rating_scale + 1):
                    count = ratings.count(i)
                    percentage = (count / len(ratings) * 100) if ratings else 0
                    data.append([str(i), str(count), f'{percentage:.1f}%'])
                
                table = Table(data)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                elements.append(table)
            else:
                elements.append(Paragraph("No ratings yet", styles['Normal']))
                
        elif question.is_text:
            answers = question.options[0].text_answers
            if answers:
                elements.append(Paragraph(f"Total Responses: {len(answers)}", styles['Normal']))
                for answer in answers:
                    elements.append(Paragraph(f"• {answer.text}", styles['Normal']))
            else:
                elements.append(Paragraph("No text responses yet", styles['Normal']))
        
        elements.append(Spacer(1, 12))
    
    doc.build(elements)
    buffer.seek(0)
    
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'survey_results_{survey.id}.pdf'
    )

@app.route('/survey/<int:survey_id>/delete', methods=['POST'])
@login_required
def delete_survey(survey_id):
    survey = Survey.query.get_or_404(survey_id)
    if survey.user_id != current_user.id:
        flash('You are not authorized to delete this survey', 'error')
        return redirect(url_for('index'))
    
    try:
        db.session.delete(survey)
        db.session.commit()
        flash('Survey deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the survey', 'error')
    
    return redirect(url_for('profile'))

if __name__ == '__main__':
    app.run()
