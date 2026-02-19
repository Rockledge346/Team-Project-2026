from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask import request, redirect
from config import Config

app = Flask(__name__, template_folder="pages")
app.config.from_object(Config)
db = SQLAlchemy(app)

#db
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guest_name = db.Column(db.String(100), nullable=False)
    guest_email = db.Column(db.String(120), nullable=False)
    check_in = db.Column(db.String(20), nullable=False)
    check_out = db.Column(db.String(20), nullable=False)





#Routes
@app.route("/")
def customer_page():
    return render_template("customer.html")


@app.route("/admin")
def admin_page():
 bookings = Booking.query.all()
 return render_template("admin.html",bookings=bookings)

#create booking function
@app.route("/admin/create-booking", methods=["GET", "POST"])
def create_booking():
    if request.method == "POST":
        booking = Booking(
            guest_name=request.form["name"],
            guest_email=request.form["email"],
            check_in=request.form["check_in"],
            check_out=request.form["check_out"]
        )
        db.session.add(booking)
        db.session.commit()
        return redirect("/admin")

    return render_template("create_booking.html")





if __name__ == "__main__":
    import os
    instance_path = os.path.join(os.path.dirname(__file__), "instance")
    os.makedirs(instance_path, exist_ok=True)
    with app.app_context():
        db.create_all()
    app.run(debug=True)
