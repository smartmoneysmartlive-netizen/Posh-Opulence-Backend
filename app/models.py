from .extensions import db
from datetime import datetime
import secrets

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=False)
    username = db.Column(db.String(80), nullable=True)
    first_name = db.Column(db.String(80), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    referral_code = db.Column(db.String(10), unique=True, nullable=False, default=lambda: secrets.token_hex(5))
    referred_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    packages = db.relationship('UserPackage', backref='user', lazy=True)
    referrals = db.relationship('User', backref=db.backref('referrer', remote_side=[id]), lazy='dynamic')
    withdrawal_requests = db.relationship('WithdrawalRequest', backref='user', lazy=True)

    def to_dict(self):
        return {
            "id": self.id, 
            "telegram_id": self.telegram_id, 
            "first_name": self.first_name, 
            "is_admin": self.is_admin,
            "referral_code": self.referral_code
        }

class Package(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    min_price = db.Column(db.Float, nullable=False)
    max_price = db.Column(db.Float, nullable=True)
    min_price_usd = db.Column(db.Float, nullable=False)
    max_price_usd = db.Column(db.Float, nullable=True)
    duration_days = db.Column(db.Integer, nullable=False)
    dividend_percentage = db.Column(db.Float, nullable=False, default=10.0)
    image_url = db.Column(db.String(255), nullable=True)

    def to_dict(self):
        return {
            "id": self.id, 
            "name": self.name, 
            "min_price": self.min_price,
            "max_price": self.max_price,
            "min_price_usd": self.min_price_usd,
            "max_price_usd": self.max_price_usd,
            "duration_days": self.duration_days, 
            "dividend_percentage": self.dividend_percentage,
            "image_url": self.image_url
        }

class UserPackage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    package_id = db.Column(db.Integer, db.ForeignKey('package.id'), nullable=False)
    investment_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    purchase_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    activation_date = db.Column(db.DateTime, nullable=True)
    expiry_date = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(255), nullable=True)
    
    total_withdrawn = db.Column(db.Float, nullable=False, default=0.0)

    package = db.relationship('Package')
    withdrawal_request = db.relationship('WithdrawalRequest', backref='user_package', uselist=False, cascade="all, delete-orphan")
    
    payment_method = db.Column(db.String(50), nullable=True)
    payment_proof_url = db.Column(db.String(255), nullable=True)
    depositor_name = db.Column(db.String(120), nullable=True)
    depositor_bank = db.Column(db.String(120), nullable=True)
    deposited_amount = db.Column(db.Float, nullable=True)

    def to_dict(self):
        package_info = self.package.to_dict() if self.package else {}
        return {
            "user_package_id": self.id,
            "package_name": package_info.get('name'),
            "investment_amount": self.investment_amount,
            "total_withdrawn": self.total_withdrawn,
            "package_dividend_percentage": package_info.get('dividend_percentage'),
            "status": self.status,
            "purchase_date": self.purchase_date.isoformat() if self.purchase_date else None,
            "activation_date": self.activation_date.isoformat() if self.activation_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "rejection_reason": self.rejection_reason,
            "payment_method": self.payment_method
        }

class WithdrawalRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user_package_id = db.Column(db.Integer, db.ForeignKey('user_package.id'), nullable=False, unique=True)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    request_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        
    withdrawal_method = db.Column(db.String(50), nullable=False)

    account_name = db.Column(db.String(120), nullable=True)
    account_number = db.Column(db.String(50), nullable=True)
    bank_name = db.Column(db.String(120), nullable=True)

    wallet_address = db.Column(db.String(255), nullable=True)
    crypto_network = db.Column(db.String(50), nullable=True)

    def to_dict(self):
        data = {
            "withdrawal_id": self.id,
            "user_name": self.user.first_name,
            "package_name": self.user_package.package.name,
            "amount": self.amount,
            "status": self.status,
            "request_date": self.request_date.isoformat(),
            "withdrawal_method": self.withdrawal_method
        }
        if self.withdrawal_method == 'bank_transfer':
            data.update({
                "account_name": self.account_name,
                "account_number": self.account_number,
                "bank_name": self.bank_name
            })
        elif self.withdrawal_method == 'crypto':
            data.update({
                "wallet_address": self.wallet_address,
                "crypto_network": self.crypto_network
            })
        return data