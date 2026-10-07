from app import create_app

app = create_app()

if __name__ == "__main__":
    # debug=True solo mientras desarrollas; ponlo en False para el cliente final
    app.run(host="127.0.0.1", port=app.config["PORT"], debug=True)