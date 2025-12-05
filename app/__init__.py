from flask import Flask
from .config import Config
from .extensions import db, migrate, cors, mail
from .routes import api
from . import models
from .utils import setup_cloudinary

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app)
    mail.init_app(app)

    setup_cloudinary()

    app.register_blueprint(api, url_prefix='/api')

    return app