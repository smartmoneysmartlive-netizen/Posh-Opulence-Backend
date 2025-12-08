from flask import request, jsonify, Blueprint
from datetime import datetime
from ..models import User, Package, UserPackage, WithdrawalRequest
from ..extensions import db
import cloudinary.uploader

main_bp = Blueprint('main_bp', __name__)

@main_bp.route('/packages', methods=['GET'])
def get_packages():
    packages = Package.query.all()
    return jsonify([p.to_dict() for p in packages])

@main_bp.route('/user/packages', methods=['POST'])
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

@main_bp.route('/user/package/<int:user_package_id>', methods=['DELETE'])
def cancel_package_selection(user_package_id):
    user_package = UserPackage.query.get_or_404(user_package_id)
    if user_package.status == 'pending' and user_package.payment_proof_url is None and user_package.depositor_name is None:
        db.session.delete(user_package)
        db.session.commit()
        return jsonify({"message": "Selection cancelled successfully."}), 200
    return jsonify({"error": "Cannot cancel this package. It may have already been processed or paid for."}), 400

@main_bp.route('/user/package/<int:user_package_id>/upload_proof', methods=['POST'])
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

@main_bp.route('/user/package/<int:user_package_id>/submit_bank_details', methods=['POST'])
def submit_bank_details(user_package_id):
    data = request.json
    user_package = UserPackage.query.get_or_404(user_package_id)

    user_package.depositor_name = data.get('depositor_name')
    user_package.depositor_bank = data.get('depositor_bank')
    user_package.deposited_amount = data.get('deposited_amount')
    user_package.payment_method = 'bank_transfer'
    
    db.session.commit()
    return jsonify({"message": "Payment details submitted. Awaiting admin confirmation."})

@main_bp.route('/user/<int:user_id>/dashboard', methods=['GET'])
def get_user_dashboard(user_id):
    user_packages = UserPackage.query.filter_by(user_id=user_id)\
        .filter(UserPackage.status.in_(['pending', 'paid', 'expired', 'rejected', 'withdrawn']))\
        .order_by(UserPackage.purchase_date.desc()).all()
    
    return jsonify([up.to_dict() for up in user_packages])

@main_bp.route('/user/<int:user_id>/history', methods=['GET'])
def get_user_history(user_id):
    user_packages = UserPackage.query.filter_by(user_id=user_id).order_by(UserPackage.purchase_date.desc()).all()
    return jsonify([up.to_dict() for up in user_packages])

@main_bp.route('/user/<int:user_id>/referrals', methods=['GET'])
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

@main_bp.route('/user/withdrawals', methods=['POST'])
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
    
    existing_request = WithdrawalRequest.query.filter_by(user_package_id=user_package_id, status='pending').first()
    if existing_request:
        return jsonify({"error": "A pending withdrawal request for this package already exists."}), 400

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
            return jsonify({"error": "Bank details are required."}), 400
    elif withdrawal_method == 'crypto':
        withdrawal_data['wallet_address'] = data.get('wallet_address')
        withdrawal_data['crypto_network'] = data.get('crypto_network')
        if not all([withdrawal_data['wallet_address'], withdrawal_data['crypto_network']]):
            return jsonify({"error": "Wallet address and network are required."}), 400
    else:
        return jsonify({"error": "Invalid withdrawal method."}), 400

    new_withdrawal = WithdrawalRequest(**withdrawal_data)
    user_package.status = 'expired'
    db.session.add(new_withdrawal)
    db.session.commit()
    return jsonify({"message": "Withdrawal will be processed within 0-5 working days."}), 201