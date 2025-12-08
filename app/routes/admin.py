from flask import request, jsonify, Blueprint
from datetime import datetime, timedelta
from ..models import Package, UserPackage, WithdrawalRequest
from ..extensions import db
import cloudinary.uploader
import logging

admin_bp = Blueprint('admin_bp', __name__, url_prefix='/admin')

def calculate_expiry_date(start_date, working_days):
    current_date = start_date
    days_added = 0
    while days_added < working_days:
        current_date += timedelta(days=1)
        if current_date.weekday() < 5:
            days_added += 1
    return current_date

@admin_bp.route('/packages', methods=['POST'])
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

@admin_bp.route('/pending', methods=['GET'])
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

@admin_bp.route('/history', methods=['GET'])
def get_admin_history():
    history = UserPackage.query.filter(UserPackage.status.in_(['paid', 'rejected', 'expired', 'withdrawn'])).order_by(UserPackage.purchase_date.desc()).all()
    result = [{"user_package_id": up.id, "user_name": up.user.first_name, "package_name": up.package.name, "status": up.status, "date": (up.activation_date or up.purchase_date).isoformat(), "reason": up.rejection_reason} for up in history]
    return jsonify(result)

@admin_bp.route('/approve/<int:user_package_id>', methods=['POST'])
def approve_payment(user_package_id):
    up = UserPackage.query.get_or_404(user_package_id)
    if up.status != 'pending':
        return jsonify({"error": "Package is not in a 'pending' state"}), 400
    
    up.status = 'paid'
    up.activation_date = datetime.utcnow()
    up.expiry_date = calculate_expiry_date(up.activation_date, up.package.duration_days)
    
    db.session.commit()
    return jsonify({"message": "Payment approved. Package activated."})

@admin_bp.route('/reject/<int:user_package_id>', methods=['POST'])
def reject_payment(user_package_id):
    data = request.json
    reason = data.get('reason', 'No reason provided.')
    up = UserPackage.query.get_or_404(user_package_id)
    if up.status != 'pending':
        return jsonify({"error": "Package is not in a 'pending' state"}), 400
    up.status, up.rejection_reason = 'rejected', reason
    db.session.commit()
    return jsonify({"message": "Payment rejected."})

@admin_bp.route('/withdrawals', methods=['GET'])
def get_pending_withdrawals():
    withdrawals = WithdrawalRequest.query.filter_by(status='pending').order_by(WithdrawalRequest.request_date.asc()).all()
    return jsonify([w.to_dict() for w in withdrawals])

@admin_bp.route('/withdrawals/<int:withdrawal_id>/approve', methods=['POST'])
def approve_withdrawal(withdrawal_id):
    withdrawal = WithdrawalRequest.query.get_or_404(withdrawal_id)
    if withdrawal.status != 'pending':
        return jsonify({"error": "This withdrawal request is not pending."}), 400

    user_package = withdrawal.user_package
    if not user_package:
        withdrawal.status = 'rejected'
        db.session.commit()
        return jsonify({"error": "Associated user package not found. Request rejected."}), 404

    withdrawal.status = 'approved'
    user_package.total_withdrawn += withdrawal.amount
    
    if user_package.total_withdrawn >= user_package.investment_amount:
        user_package.status = 'withdrawn'
    else:
        user_package.status = 'paid'
        user_package.activation_date = datetime.utcnow()
        user_package.expiry_date = calculate_expiry_date(
            user_package.activation_date, 
            user_package.package.duration_days
        )
    
    db.session.delete(withdrawal)
    db.session.commit()
    return jsonify({"message": "Withdrawal approved and package status updated."})