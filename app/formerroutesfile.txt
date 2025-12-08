from flask import request, jsonify, Blueprint
from datetime import datetime, timedelta
from .models import User, Package, UserPackage, WithdrawalRequest
from .extensions import db
from .utils import send_email
import cloudinary.uploader
import secrets
import logging

api = Blueprint('api', __name__)

def calculate_expiry_date(start_date, working_days):
    """Calculates the expiry date by adding only working days (Mon-Fri)."""
    current_date = start_date
    days_added = 0
    while days_added < working_days:
        current_date += timedelta(days=1)
        if current_date.weekday() < 5:  # Monday is 0, Sunday is 6
            days_added += 1
    return current_date

@api.route('/auth', methods=['POST'])
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

@api.route('/packages', methods=['GET'])
def get_packages():
    packages = Package.query.all()
    return jsonify([p.to_dict() for p in packages])

@api.route('/user/packages', methods=['POST'])
def purchase_package():
    data = request.json
    user_id = data.get('user_id')
    package_id = data.get('package_id')
    investment_amount = data.get('investment_amount')

    if not all([user_id, package_id, investment_amount]):
        return jsonify({"error": "User ID, Package ID, and Investment Amount are required"}), 400
    
    try:
        investment_amount = float(investment_amount)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid investment amount"}), 400

    package = Package.query.get_or_404(package_id)
    
    if investment_amount < package.min_price:
        return jsonify({"message": f"Investment must be at least ₦{package.min_price:,.0f}"}), 400
    
    if package.max_price and investment_amount > package.max_price:
        return jsonify({"message": f"Investment cannot exceed ₦{package.max_price:,.0f}"}), 400
    
    new_purchase = UserPackage(
        user_id=user_id, 
        package_id=package_id,
        investment_amount=investment_amount
    )
    db.session.add(new_purchase)
    db.session.commit()
    return jsonify({"message": "Package selected. Please make your payment.", "user_package_id": new_purchase.id, "package_name": new_purchase.package.name}), 201

@api.route('/user/package/<int:user_package_id>', methods=['DELETE'])
def cancel_package_selection(user_package_id):
    user_package = UserPackage.query.get_or_404(user_package_id)
    if user_package.status == 'pending' and user_package.payment_proof_url is None and user_package.depositor_name is None:
        db.session.delete(user_package)
        db.session.commit()
        return jsonify({"message": "Selection cancelled successfully."}), 200
    return jsonify({"error": "Cannot cancel this package. It may have already been processed or paid for."}), 400

@api.route('/user/package/<int:user_package_id>/upload_proof', methods=['POST'])
def upload_payment_proof(user_package_id):
    if 'proof' not in request.files:
        return jsonify({"error": "No proof file provided"}), 400
    file = request.files['proof']
    user_package = UserPackage.query.get_or_404(user_package_id)
    try:
        upload_result = cloudinary.uploader.upload(file, folder="payment_proofs")
        user_package.payment_proof_url = upload_result['secure_url']
        user_package.payment_method = 'crypto'
        db.session.commit()
        return jsonify({"message": "Payment proof submitted. Awaiting admin confirmation."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api.route('/user/package/<int:user_package_id>/submit_bank_details', methods=['POST'])
def submit_bank_details(user_package_id):
    data = request.json
    user_package = UserPackage.query.get_or_404(user_package_id)

    user_package.depositor_name = data.get('depositor_name')
    user_package.depositor_bank = data.get('depositor_bank')
    user_package.deposited_amount = data.get('deposited_amount')
    user_package.payment_method = 'bank_transfer'
    
    db.session.commit()
    return jsonify({"message": "Payment details submitted. Awaiting admin confirmation."})

@api.route('/user/<int:user_id>/dashboard', methods=['GET'])
def get_user_dashboard(user_id):
    user_packages = UserPackage.query.filter_by(user_id=user_id)\
        .filter(UserPackage.status.in_(['pending', 'paid', 'expired', 'rejected']))\
        .order_by(UserPackage.purchase_date.desc()).all()
    
    return jsonify([up.to_dict() for up in user_packages])

@api.route('/user/<int:user_id>/history', methods=['GET'])
def get_user_history(user_id):
    user_packages = UserPackage.query.filter_by(user_id=user_id).order_by(UserPackage.purchase_date.desc()).all()
    return jsonify([up.to_dict() for up in user_packages])

@api.route('/user/<int:user_id>/referrals', methods=['GET'])
def get_user_referrals(user_id):
    user = User.query.get_or_404(user_id)
    referrals = user.referrals.all()
    referral_list = [{"id": r.id, "first_name": r.first_name} for r in referrals]
    
    commission = 0
    for r in referrals:
        first_paid_package = UserPackage.query.filter_by(user_id=r.id, status='paid').order_by(UserPackage.activation_date.asc()).first()
        if first_paid_package:
            commission += first_paid_package.investment_amount * 0.02

    return jsonify({
        "referral_code": user.referral_code,
        "referrals": referral_list,
        "commission_earned": commission
    })

@api.route('/user/withdrawals', methods=['POST'])
def request_withdrawal():
    data = request.json
    user_package_id = data.get('user_package_id')
    user_package = UserPackage.query.get_or_404(user_package_id)

    if user_package.status != 'paid' or not user_package.expiry_date or user_package.expiry_date > datetime.utcnow():
        return jsonify({"error": "Withdrawal is not yet available for this package."}), 400

    try:
        requested_amount = float(data.get('amount'))
        if requested_amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid withdrawal amount provided."}), 400

    dividend_earned = user_package.investment_amount * (user_package.package.dividend_percentage / 100)

    if requested_amount > dividend_earned:
        return jsonify({"error": f"Withdrawal amount cannot exceed the earned dividend of {dividend_earned:,.2f}."}), 400
    
    existing_request = WithdrawalRequest.query.filter_by(user_package_id=user_package_id).first()
    if existing_request:
        return jsonify({"error": "A withdrawal request for this package already exists."}), 400

    withdrawal_method = data.get('withdrawal_method')
    
    withdrawal_data = {
        "user_id": user_package.user_id,
        "user_package_id": user_package_id,
        "amount": requested_amount,
        "withdrawal_method": withdrawal_method
    }

    if withdrawal_method == 'bank_transfer':
        withdrawal_data['account_name'] = data.get('account_name')
        withdrawal_data['account_number'] = data.get('account_number')
        withdrawal_data['bank_name'] = data.get('bank_name')
        if not all([withdrawal_data['account_name'], withdrawal_data['account_number'], withdrawal_data['bank_name']]):
            return jsonify({"error": "Bank details are required for this withdrawal method."}), 400
    elif withdrawal_method == 'crypto':
        withdrawal_data['wallet_address'] = data.get('wallet_address')
        withdrawal_data['crypto_network'] = data.get('crypto_network')
        if not all([withdrawal_data['wallet_address'], withdrawal_data['crypto_network']]):
            return jsonify({"error": "Wallet address and network are required for this withdrawal method."}), 400
    else:
        return jsonify({"error": "Invalid withdrawal method specified."}), 400

    new_withdrawal = WithdrawalRequest(**withdrawal_data)
    user_package.status = 'expired'
    db.session.add(new_withdrawal)
    db.session.commit()
    return jsonify({"message": "Your withdrawal request has been received, kindly wait for 7 working days."}), 201

@api.route('/admin/packages', methods=['POST'])
def create_package():
    try:
        data = request.form
        if 'image' not in request.files:
            return jsonify({"error": "No image file provided"}), 400
        
        file = request.files['image']
        
        required_fields = ['name', 'min_price', 'min_price_usd', 'duration_days', 'dividend_percentage']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required form data"}), 400

        upload_result = cloudinary.uploader.upload(file, folder="package_images")
        
        new_package = Package(
            name=data['name'], 
            min_price=float(data['min_price']),
            max_price=float(data['max_price']) if data.get('max_price') else None,
            min_price_usd=float(data['min_price_usd']),
            max_price_usd=float(data['max_price_usd']) if data.get('max_price_usd') else None,
            duration_days=int(data['duration_days']),
            dividend_percentage=float(data['dividend_percentage']),
            image_url=upload_result['secure_url']
        )
        db.session.add(new_package)
        db.session.commit()
        return jsonify(new_package.to_dict()), 201
    except Exception as e:
        logging.error(f"Error creating package: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred."}), 500

@api.route('/admin/pending', methods=['GET'])
def get_pending_packages():
    pending_packages = UserPackage.query.filter(
        UserPackage.status == 'pending',
        (UserPackage.payment_proof_url != None) | (UserPackage.depositor_name != None)
    ).order_by(UserPackage.purchase_date.asc()).all()
    
    result = []
    for up in pending_packages:
        details = {
            "user_package_id": up.id,
            "user_name": up.user.first_name,
            "telegram_id": up.user.telegram_id,
            "package_name": up.package.name,
            "investment_amount": up.investment_amount,
            "purchase_date": up.purchase_date.isoformat(),
            "payment_method": up.payment_method
        }
        if up.payment_method == 'crypto':
            details["payment_proof_url"] = up.payment_proof_url
        elif up.payment_method == 'bank_transfer':
            details["depositor_name"] = up.depositor_name
            details["depositor_bank"] = up.depositor_bank
            details["deposited_amount"] = up.deposited_amount
        
        result.append(details)
        
    return jsonify(result)

@api.route('/admin/history', methods=['GET'])
def get_admin_history():
    history = UserPackage.query.filter(UserPackage.status.in_(['paid', 'rejected', 'expired', 'withdrawn'])).order_by(UserPackage.purchase_date.desc()).all()
    result = [{"user_package_id": up.id, "user_name": up.user.first_name, "package_name": up.package.name, "status": up.status, "date": (up.activation_date or up.purchase_date).isoformat(), "reason": up.rejection_reason} for up in history]
    return jsonify(result)

@api.route('/admin/approve/<int:user_package_id>', methods=['POST'])
def approve_payment(user_package_id):
    up = UserPackage.query.get_or_404(user_package_id)
    if up.status != 'pending':
        return jsonify({"error": "Package is not in a 'pending' state"}), 400
    
    up.status = 'paid'
    up.activation_date = datetime.utcnow()
    up.expiry_date = calculate_expiry_date(up.activation_date, up.package.duration_days)
    
    db.session.commit()
    return jsonify({"message": "Payment approved. Package activated."})

@api.route('/admin/reject/<int:user_package_id>', methods=['POST'])
def reject_payment(user_package_id):
    data = request.json
    reason = data.get('reason', 'No reason provided.')
    up = UserPackage.query.get_or_404(user_package_id)
    if up.status != 'pending':
        return jsonify({"error": "Package is not in a 'pending' state"}), 400
    up.status, up.rejection_reason = 'rejected', reason
    db.session.commit()
    return jsonify({"message": "Payment rejected."})

@api.route('/admin/withdrawals', methods=['GET'])
def get_pending_withdrawals():
    withdrawals = WithdrawalRequest.query.filter_by(status='pending').order_by(WithdrawalRequest.request_date.asc()).all()
    return jsonify([w.to_dict() for w in withdrawals])

@api.route('/admin/withdrawals/<int:withdrawal_id>/approve', methods=['POST'])
def approve_withdrawal(withdrawal_id):
    withdrawal = WithdrawalRequest.query.get_or_404(withdrawal_id)
    withdrawal.status = 'approved'
    user_package = withdrawal.user_package
    user_package.status = 'withdrawn'
    db.session.commit()
    return jsonify({"message": "Withdrawal approved."})