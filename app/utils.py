from flask_mail import Message
from .extensions import mail
from flask import current_app
import threading
import cloudinary
import os

def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)

def send_email(to, subject, template):
    app = current_app._get_current_object()
    msg = Message(subject, recipients=[to], html=template, sender=app.config['MAIL_DEFAULT_SENDER'])
    thr = threading.Thread(target=send_async_email, args=[app, msg])
    thr.start()
    return thr

def setup_cloudinary():
    cloudinary.config(
        cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key=os.environ.get('CLOUDINARY_API_KEY'),
        api_secret=os.environ.get('CLOUDINARY_API_SECRET')
    )