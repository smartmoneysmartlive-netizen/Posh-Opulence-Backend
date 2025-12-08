from flask import request, jsonify, Blueprint
from ..models import User
from ..extensions import db
import secrets

auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route('/auth', methods=['POST'])
def authenticate():
    data = request.json
    tg_user = data.get('user')
    referral_code = data.get('referral_code')

    if not tg_user or not tg_user.get('id'):
        return jsonify({"error": "User data not provided"}), 400
    
    telegram_id = tg_user.get('id')
    user = User.query.filter_by(telegram_id=telegram_id).first()
    is_new_user = False

    if not user:
        is_new_user = True
        referrer = None
        if referral_code:
            referrer = User.query.filter_by(referral_code=referral_code).first()
        
        user = User(
            telegram_id=telegram_id, 
            first_name=tg_user.get('first_name', 'N/A'), 
            username=tg_user.get('username'),
            referred_by_id=referrer.id if referrer else None,
            referral_code=secrets.token_hex(5)
        )
        db.session.add(user)
        db.session.commit()
        
    user_data = user.to_dict()
    user_data['is_new_user'] = is_new_user
    return jsonify(user_data)