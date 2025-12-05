from app import create_app
from app.seed import seed_packages

app = create_app()

@app.cli.command("db-seed")
def db_seed():
    """Seeds the database with initial data."""
    seed_packages()

if __name__ == '__main__':
    app.run(debug=True, port=5001)