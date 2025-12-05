from app import create_app
# REMOVED: No more seed command here

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5001)