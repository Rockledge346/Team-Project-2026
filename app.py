from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy

from config import Config

app = Flask(__name__, template_folder="pages")
app.config.from_object(Config)
db = SQLAlchemy(app)


@app.route("/")
def customer_page():
    return render_template("customer.html")


@app.route("/admin")
def admin_page():
    return render_template("admin.html")


if __name__ == "__main__":
    import os
    instance_path = os.path.join(os.path.dirname(__file__), "instance")
    os.makedirs(instance_path, exist_ok=True)
    with app.app_context():
        db.create_all()
    app.run(debug=True)
