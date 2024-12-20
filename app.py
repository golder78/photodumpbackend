from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_cors import CORS
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import uvicorn
from threading import Thread

# Set up Flask app
app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///photo_dump.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
db = SQLAlchemy(app)

# Enable CORS for the entire Flask app
CORS(app, supports_credentials=True)

# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize FastAPI instance
fastapi_app = FastAPI()

# Enable CORS for FastAPI (for React to communicate with it)
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Database Models (Flask/SQLAlchemy)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String(128), nullable=False)

class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_path = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(200))
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_name = db.Column(db.String(100), nullable=False)

# Pydantic model for FastAPI response
class PhotoModel(BaseModel):
    id: int
    file_path: str
    description: str
    upload_date: datetime
    user_id: int
    category_id: int

class CategoryModel(BaseModel):
    id: int
    category_name: str

# Initialize database and create default admin user
def initialize_database():
    with app.app_context():
        db.create_all()
        print("Database tables created successfully!")
        if not User.query.filter_by(email="admin@example.com").first():
            new_user = User(
                name="Admin",
                email="admin@example.com",
                password_hash=generate_password_hash("admin")
            )
            db.session.add(new_user)
            db.session.commit()
            print("Default admin user created.")

# Flask routes (web interface)
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')
    user = User.query.filter_by(email=email).first()
    if user and check_password_hash(user.password_hash, password):
        session['user_id'] = user.id
        return redirect(url_for('dashboard'))
    return "Invalid Credentials", 401

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

@app.route('/dashboard', methods=['GET'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    category_id = request.args.get('category_id')  # Get the selected category ID from the query parameters
    if category_id:
        photos = Photo.query.filter_by(user_id=session['user_id'], category_id=category_id).all()
    else:
        photos = Photo.query.filter_by(user_id=session['user_id']).all()

    categories = Category.query.all()

    for photo in photos:
        photo.filename = os.path.basename(photo.file_path)

    return render_template('dashboard.html', photos=photos, categories=categories)

@app.route('/delete/<int:photo_id>', methods=['POST'])
def delete(photo_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    photo = Photo.query.filter_by(id=photo_id, user_id=session['user_id']).first()
    if not photo:
        return "Photo not found or access denied", 404
    file_path = photo.file_path
    if os.path.exists(file_path):
        os.remove(file_path)
    db.session.delete(photo)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# New route for uploading photos with category
@app.route('/upload', methods=['POST'])
def upload_photo():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    file = request.files.get('photo')
    description = request.form.get('description')
    category_id = request.form.get('category_id')
    
    if file and description and category_id:
        filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filename)

        new_photo = Photo(
            file_path=filename,
            description=description,
            user_id=session['user_id'],
            category_id=category_id
        )
        
        db.session.add(new_photo)
        db.session.commit()

        return redirect(url_for('dashboard'))
    return "Invalid form data", 400

# FastAPI routes (API for React frontend)
@fastapi_app.get("/api/photos", response_model=List[PhotoModel])
def get_photos():
    photos = Photo.query.all()
    return photos

@fastapi_app.get("/api/categories", response_model=List[CategoryModel])
def get_categories():
    categories = Category.query.all()
    return categories

# Running Flask and FastAPI together
if __name__ == '__main__':
    initialize_database()

    def run_flask():
        app.run(debug=True, use_reloader=False)

    def run_fastapi():
        uvicorn.run(fastapi_app, host="0.0.0.0", port=8000)

    Thread(target=run_flask).start()
    Thread(target=run_fastapi).start()
