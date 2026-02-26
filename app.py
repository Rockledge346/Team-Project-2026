from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from config import Config
from datetime import datetime

app = Flask(__name__, template_folder="pages")
app.config.from_object(Config)
db = SQLAlchemy(app)


class RoomType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    max_adults = db.Column(db.Integer, default=2)
    max_children = db.Column(db.Integer, default=1)
    max_occupancy = db.Column(db.Integer, default=3)
    base_price = db.Column(db.Float, nullable=False)
    num_rooms = db.Column(db.Integer, default=5)
    photos = db.Column(db.String(500))


class Guest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guest_name = db.Column(db.String(100), nullable=False)
    guest_email = db.Column(db.String(120), nullable=False)
    check_in = db.Column(db.String(20), nullable=False)
    check_out = db.Column(db.String(20), nullable=False)
    guest_id = db.Column(db.Integer, db.ForeignKey('guest.id'), nullable=True)
    room_type_id = db.Column(db.Integer, db.ForeignKey('room_type.id'), nullable=True)
    reference = db.Column(db.String(20))
    status = db.Column(db.String(20), default='confirmed')
    payment_status = db.Column(db.String(20), default='pending')
    num_rooms = db.Column(db.Integer, default=1)
    num_adults = db.Column(db.Integer, default=1)
    num_children = db.Column(db.Integer, default=0)
    special_requests = db.Column(db.Text)
    total_amount = db.Column(db.Float)
    currency = db.Column(db.String(10), default='EUR')
    room_type = db.relationship('RoomType', backref='bookings')
    guest = db.relationship('Guest', backref='bookings')


class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(10), nullable=False, unique=True)
    room_type_id = db.Column(db.Integer, db.ForeignKey('room_type.id'), nullable=False)
    floor = db.Column(db.Integer)
    status = db.Column(db.String(20), default='available')
    current_booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    room_type = db.relationship('RoomType', backref='rooms')


@app.route("/")
def customer_page():
    return render_template("customer.html")


def get_rooms_booked(room_type_id, check_in, check_out):
    return Booking.query.filter(
        Booking.room_type_id == room_type_id,
        Booking.status != 'cancelled',
        Booking.check_in < check_out,
        Booking.check_out > check_in
    ).count()


@app.route("/search")
def search_page():
    check_in = request.args.get("check_in")
    check_out = request.args.get("check_out")

    if not check_in or not check_out:
        return redirect("/")

    ci = datetime.strptime(check_in, "%Y-%m-%d")
    co = datetime.strptime(check_out, "%Y-%m-%d")
    num_nights = (co - ci).days

    if num_nights < 1:
        return redirect("/")

    room_types = RoomType.query.all()

    available_rooms = []
    for rt in room_types:
        booked = get_rooms_booked(rt.id, check_in, check_out)
        rooms_left = rt.num_rooms - booked
        if rooms_left > 0:
            rt.rooms_available = rooms_left
            available_rooms.append(rt)

    return render_template("search.html",
                           room_types=available_rooms,
                           check_in=check_in,
                           check_out=check_out,
                           num_nights=num_nights)


@app.route("/book/<int:room_type_id>", methods=["GET", "POST"])
def book_page(room_type_id):
    room_type = RoomType.query.get_or_404(room_type_id)
    check_in = request.args.get("check_in") or request.form.get("check_in")
    check_out = request.args.get("check_out") or request.form.get("check_out")

    if not check_in or not check_out:
        return redirect("/")

    ci = datetime.strptime(check_in, "%Y-%m-%d")
    co = datetime.strptime(check_out, "%Y-%m-%d")
    num_nights = (co - ci).days
    total = room_type.base_price * num_nights

    booked = get_rooms_booked(room_type.id, check_in, check_out)
    rooms_left = room_type.num_rooms - booked

    if rooms_left <= 0:
        flash("Sorry, this room type is fully booked for the selected dates.", "danger")
        return redirect(url_for("search_page", check_in=check_in, check_out=check_out))

    if request.method == "POST":
        booked = get_rooms_booked(room_type.id, check_in, check_out)
        if booked >= room_type.num_rooms:
            flash("Sorry, this room type just became fully booked. Please choose another.", "danger")
            return redirect(url_for("search_page", check_in=check_in, check_out=check_out))

        guest = Guest(
            first_name=request.form["first_name"],
            last_name=request.form["last_name"],
            email=request.form["email"],
            phone=request.form.get("phone", ""),
            address=request.form.get("address", "")
        )
        db.session.add(guest)
        db.session.flush()

        payment_method = request.form.get("payment_method", "reception")
        payment_status = "paid" if payment_method == "card" else "pending"

        booking = Booking(
            guest_name=request.form["first_name"] + " " + request.form["last_name"],
            guest_email=request.form["email"],
            check_in=check_in,
            check_out=check_out,
            guest_id=guest.id,
            room_type_id=room_type.id,
            reference="11111",
            status="confirmed",
            payment_status=payment_status,
            num_adults=int(request.form.get("num_adults", 1)),
            num_children=int(request.form.get("num_children", 0)),
            special_requests=request.form.get("special_requests", ""),
            total_amount=total,
            currency="EUR"
        )
        db.session.add(booking)
        db.session.commit()

        return redirect(url_for("confirmation_page", booking_id=booking.id))

    return render_template("book.html",
                           room_type=room_type,
                           check_in=check_in,
                           check_out=check_out,
                           num_nights=num_nights,
                           total=total)


@app.route("/confirmation/<int:booking_id>")
def confirmation_page(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    room_type = RoomType.query.get(booking.room_type_id) if booking.room_type_id else None
    return render_template("confirmation.html", booking=booking, room_type=room_type)



@app.route("/admin")
def admin_page():
    return render_template("admin.html")


@app.route("/admin/bookings")
def admin_bookings():
    bookings = Booking.query.order_by(Booking.id.desc()).all()

    booking_rows = []
    for b in bookings:
        room_type_name = b.room_type.name if b.room_type else "—"

        nights = "—"
        try:
            ci = datetime.strptime(b.check_in, "%Y-%m-%d")
            co = datetime.strptime(b.check_out, "%Y-%m-%d")
            nights = (co - ci).days
        except:
            pass

        booking_rows.append({
            "id": b.id,
            "guest_name": b.guest_name,
            "guest_email": b.guest_email,
            "check_in": b.check_in,
            "check_out": b.check_out,
            "nights": nights,
            "room_type": room_type_name,
            "num_rooms": b.num_rooms,
            "total_amount": b.total_amount,
            "currency": b.currency or "EUR",
            "status": b.status,
            "payment_status": b.payment_status,
            "is_paid": (b.payment_status == "paid"),
            "special_requests": b.special_requests or ""

        })

    return render_template("admin_booking.html", bookings=booking_rows)

@app.route("/admin/create-booking", methods=["GET", "POST"])
def create_booking():
    room_types = RoomType.query.all()

    if request.method == "POST":
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        email = request.form["email"]
        check_in = request.form["check_in"]
        check_out = request.form["check_out"]
        room_type_id = int(request.form["room_type_id"])

        phone = request.form.get("phone", "")
        address = request.form.get("address", "")
        num_rooms = int(request.form.get("num_rooms", 1))
        num_adults = int(request.form.get("num_adults", 1))
        num_children = int(request.form.get("num_children", 0))
        status = request.form.get("status", "confirmed")
        payment_status = request.form.get("payment_status", "pending")
        special_requests = request.form.get("special_requests", "")

        ci = datetime.strptime(check_in, "%Y-%m-%d")
        co = datetime.strptime(check_out, "%Y-%m-%d")
        num_nights = (co - ci).days
        if num_nights < 1:
            return redirect(url_for("create_booking"))

        room_type = RoomType.query.get_or_404(room_type_id)
        total = room_type.base_price * num_nights * num_rooms

        guest = Guest(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            address=address
        )
        db.session.add(guest)
        db.session.flush()

        booking = Booking(
            guest_name=f"{first_name} {last_name}",
            guest_email=email,
            check_in=check_in,
            check_out=check_out,
            guest_id=guest.id,
            room_type_id=room_type.id,
            reference=f"BK{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            status=status,
            payment_status=payment_status,
            num_rooms=num_rooms,
            num_adults=num_adults,
            num_children=num_children,
            special_requests=special_requests,
            total_amount=total,
            currency="EUR"
        )

        db.session.add(booking)
        db.session.commit()
        return redirect("/admin/bookings")

    return render_template("create_booking.html", room_types=room_types)



def seed_data():
    if RoomType.query.first() is not None:
        return

    room_types = [
        RoomType(
            code="STD", name="Standard Room",
            description="Comfortable room with a double bed, en-suite bathroom, TV, and free Wi-Fi. Perfect for solo travellers or couples.",
            max_adults=2, max_children=1, max_occupancy=3,
            base_price=89.00, num_rooms=10,
            photos="https://placehold.co/600x400/e8d5b7/333?text=Standard+Room"
        ),
        RoomType(
            code="DLX", name="Deluxe Room",
            description="Spacious room with a king-size bed, seating area, en-suite bathroom with bath, TV, and free Wi-Fi.",
            max_adults=2, max_children=2, max_occupancy=4,
            base_price=129.00, num_rooms=8,
            photos="https://placehold.co/600x400/c9b99a/333?text=Deluxe+Room"
        ),
        RoomType(
            code="FAM", name="Family Suite",
            description="Large suite with a king-size bed and two single beds. Separate living area, en-suite bathroom, TV, and free Wi-Fi. Ideal for families.",
            max_adults=2, max_children=3, max_occupancy=5,
            base_price=189.00, num_rooms=5,
            photos="https://placehold.co/600x400/b8c9a1/333?text=Family+Suite"
        ),
        RoomType(
            code="EXC", name="Executive Suite",
            description="Premium suite with a king-size bed, separate living room, work desk, luxury bathroom, mini bar, TV, and free Wi-Fi.",
            max_adults=2, max_children=1, max_occupancy=3,
            base_price=249.00, num_rooms=3,
            photos="https://placehold.co/600x400/a1b5c9/333?text=Executive+Suite"
        ),
    ]
    db.session.add_all(room_types)
    db.session.commit()

    floors = {"STD": 1, "DLX": 2, "FAM": 3, "EXC": 4}
    for rt in RoomType.query.all():
        floor = floors.get(rt.code, 1)
        for i in range(rt.num_rooms):
            room = Room(
                room_number=str(floor * 100 + i + 1),
                room_type_id=rt.id,
                floor=floor,
                status="available"
            )
            db.session.add(room)
    db.session.commit()


if __name__ == "__main__":
    import os
    instance_path = os.path.join(os.path.dirname(__file__), "instance")
    os.makedirs(instance_path, exist_ok=True)
    with app.app_context():
        db.create_all()
        seed_data()
    app.run(debug=True)
