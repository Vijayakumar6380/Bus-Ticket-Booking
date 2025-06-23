from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    source = db.Column(db.String(100))
    destination = db.Column(db.String(100))
    vehicle = db.Column(db.String(50))
    distance = db.Column(db.String(50))
    duration = db.Column(db.String(50))
    cost = db.Column(db.String(50))
    arrival_time = db.Column(db.String(50))
    qr_filename = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
