from .extensions import db
from .models import Package

def seed_packages():
    """Seeds the database with the three default investment packages."""
    
    default_packages = [
        {
            "name": "Conservative",
            "min_price": 15000,
            "max_price": 5000000,
            "min_price_usd": 10,
            "max_price_usd": 3400,
            "duration_days": 18,
            "dividend_percentage": 10,
            "image_url": "/images/conservative.jpeg" # Updated to jpeg
        },
        {
            "name": "Moderate",
            "min_price": 6000000,
            "max_price": 60000000,
            "min_price_usd": 4000,
            "max_price_usd": 40000,
            "duration_days": 18,
            "dividend_percentage": 15,
            "image_url": "/images/moderate.jpeg" # Updated to jpeg
        },
        {
            "name": "Growth",
            "min_price": 70000000,
            "max_price": None, # Represents unlimited
            "min_price_usd": 47000,
            "max_price_usd": None, # Represents unlimited
            "duration_days": 14,
            "dividend_percentage": 20,
            "image_url": "/images/growth.jpeg" # Updated to jpeg
        }
    ]

    for pkg_data in default_packages:
        package = Package.query.filter_by(name=pkg_data["name"]).first()
        if not package:
            new_package = Package(**pkg_data)
            db.session.add(new_package)
            print(f'Added package: {pkg_data["name"]}')
        else: # Update existing packages if found
            package.image_url = pkg_data["image_url"]
            print(f'Updated image for package: {pkg_data["name"]}')


    db.session.commit()
    print("Database seeding/update complete.")