from flask import Flask
from .config import Config
from .extensions import db, migrate, cors, mail
from .routes import api
from . import models
from .utils import setup_cloudinary
from .seed import seed_packages  # <-- IMPORT THE SEED FUNCTION
import os

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    
    FRONTEND_URL = os.environ.get('FRONTEND_URL') or "http://localhost:5173"
    cors(app, resources={r"/api/*": {"origins": FRONTEND_URL}})

    mail.init_app(app)

    setup_cloudinary()

    app.register_blueprint(api, url_prefix='/api')

    # === ADD THIS COMMAND REGISTRATION BLOCK ===
    @app.cli.command("db-seed")
    def db_seed():
        """Seeds the database with initial data."""
        seed_packages()
    # ==========================================

    return app