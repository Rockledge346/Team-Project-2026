from flask import Flask, render_template, request, redirect, url_for, flash, session
import uuid
from flask_wtf import CSRFProtect
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from config import Config
from datetime import datetime
import random
import string
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from getpass import getpass
from urllib.parse import urlparse, urljoin 

app = Flask(__name__, template_folder="pages")
app.config.from_object(Config)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
csrf = CSRFProtect(app)
APP_BOOT_ID = uuid.uuid4().hex
BOOKING_ADDONS = {
    "breakfast": {"label": "Breakfast", "price": 12.0},
    "dinner": {"label": "Dinner", "price": 22.0},
}

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

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
    rooms = db.relationship("Room", backref="booking")


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


@app.before_request
def invalidate_session_after_restart():
    if current_user.is_authenticated:
        if session.get("app_boot_id") != APP_BOOT_ID:
            logout_user()
            session.pop("app_boot_id", None)
            return redirect(url_for("login"))

@login_manager.user_loader
def load_user(user_id):
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    return User.query.get(uid)

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login", next=request.path))
        if not current_user.is_admin:
            flash("Admin access required.", "danger")
            return redirect(url_for("customer_page"))
        return f(*args, **kwargs)
    return decorated

def is_safe_url(target):
    host_url = request.host_url
    test_url = urlparse(urljoin(host_url, target))
    ref_url = urlparse(host_url)
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc

def generate_reference():
    while True:
        ref = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        if not Booking.query.filter_by(reference=ref).first():
            return ref


def get_selected_addons(form_data):
    selected_keys = form_data.getlist("addons")
    selected = []
    addons_total_per_night = 0.0

    for key in selected_keys:
        addon = BOOKING_ADDONS.get(key)
        if addon:
            selected.append({"key": key, **addon})
            addons_total_per_night += addon["price"]

    return selected, addons_total_per_night


@app.route("/")
def customer_page():
    room_types = RoomType.query.all()
    return render_template("customer.html", room_types=room_types)


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
       
        useable_rooms = Room.query.filter_by(
            room_type_id=rt.id,
            status="available"
        ).count()
        
        maintenance_rooms = RoomMaintenance.query.join(Room).filter(
        Room.room_type_id == rt.id,
        RoomMaintenance.start_date < check_out,
        RoomMaintenance.end_date > check_in
    ).count()
        
        
        rooms_left = useable_rooms - booked
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
    selected_addons = []
    addons_total_per_night = 0.0
    addons_total = 0.0
    room_total = room_type.base_price * num_nights
    grand_total = room_total

    booked = get_rooms_booked(room_type.id, check_in, check_out)
    usable_rooms = Room.query.filter_by(
    room_type_id=room_type.id,
    status="available"
    ).count()

  

    rooms_left = usable_rooms - booked

    if rooms_left <= 0:
        flash("Sorry, this room type is fully booked for the selected dates.", "danger")
        return redirect(url_for("search_page", check_in=check_in, check_out=check_out))

    if request.method == "POST":
        booked = get_rooms_booked(room_type.id, check_in, check_out)
        if booked >= room_type.num_rooms:
            flash("Sorry, this room type just became fully booked. Please choose another.", "danger")
            return redirect(url_for("search_page", check_in=check_in, check_out=check_out))

        selected_addons, addons_total_per_night = get_selected_addons(request.form)
        addons_total = addons_total_per_night * num_nights
        grand_total = room_total + addons_total

        guest = Guest(
            first_name=request.form["first_name"],
            last_name=request.form["last_name"],
            email=request.form["email"],
            phone=request.form.get("phone", ""),
            address=request.form.get("address", "")
        )
        db.session.add(guest)


        payment_method = request.form.get("payment_method", "reception")
        payment_status = "paid" if payment_method == "card" else "pending"

        booking = Booking(
            guest_name=request.form["first_name"] + " " + request.form["last_name"],
            guest_email=request.form["email"],
            check_in=check_in,
            check_out=check_out,
            guest_id=guest.id,
            room_type_id=room_type.id,
            reference=generate_reference(),
            status="confirmed",
            payment_status=payment_status,
            num_adults=int(request.form.get("num_adults", 1)),
            num_children=int(request.form.get("num_children", 0)),
            special_requests=combined_special_requests,
            total_amount=grand_total,
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
                           total=grand_total,
                           room_total=room_total,
                           addons=BOOKING_ADDONS)


@app.route("/confirmation/<int:booking_id>")
def confirmation_page(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    room_type = RoomType.query.get(booking.room_type_id) if booking.room_type_id else None
    return render_template("confirmation.html", booking=booking, room_type=room_type)



@app.route("/my-booking", methods=["GET", "POST"])
def my_booking():
    if request.method == "POST":
        ref = request.form.get("reference", "").strip().upper()
        email = request.form.get("email", "").strip().lower()
        if not ref or not email:
            flash("Please enter both your reference number and email.", "danger")
            return redirect(url_for("my_booking"))
        booking = Booking.query.filter_by(reference=ref).first()
        if not booking or booking.guest_email.lower() != email:
            flash("No booking found. Please check your reference number and email.", "danger")
            return redirect(url_for("my_booking"))
        return redirect(url_for("view_booking", reference=ref))
    return render_template("my_booking_lookup.html")


@app.route("/my-booking/<reference>", methods=["GET", "POST"])
def view_booking(reference):
    booking = Booking.query.filter_by(reference=reference.upper()).first()
    if not booking:
        flash("No booking found with that reference number.", "danger")
        return redirect("/")

    room_type = RoomType.query.get(booking.room_type_id) if booking.room_type_id else None

    if request.method == "POST":
        action = request.form.get("action")

        if action == "cancel":
            if booking.status == "cancelled":
                flash("This booking is already cancelled.", "warning")
            else:
                booking.status = "cancelled"
                if booking.payment_status == "paid":
                    checkin = datetime.strptime(booking.check_in, "%Y-%m-%d")
                    hours_until = (checkin - datetime.utcnow()).total_seconds() / 3600
                    if hours_until > 24:
                        booking.payment_status = "refunded"
                        flash("Booking cancelled. Your payment has been refunded.", "success")
                    else:
                        flash("Booking cancelled. Refund not available within 24 hours of check-in.", "warning")
                else:
                    flash("Booking cancelled successfully.", "success")
                db.session.commit()
            return redirect(url_for("view_booking", reference=reference))

        elif action == "edit":
            if booking.status == "cancelled":
                flash("Cancelled bookings cannot be edited.", "danger")
                return redirect(url_for("view_booking", reference=reference))

            booking.num_adults = int(request.form.get("num_adults", booking.num_adults))
            booking.num_children = int(request.form.get("num_children", booking.num_children))
            booking.special_requests = request.form.get("special_requests", booking.special_requests)
            db.session.commit()
            flash("Booking updated successfully.", "success")
            return redirect(url_for("view_booking", reference=reference))

    ci = datetime.strptime(booking.check_in, "%Y-%m-%d")
    co = datetime.strptime(booking.check_out, "%Y-%m-%d")
    num_nights = (co - ci).days

    return render_template("my_booking.html", booking=booking, room_type=room_type, num_nights=num_nights)


##ADMIN ROUTES

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if User.query.filter_by(username=username).first():
            flash("Username already taken.", "danger")
            return redirect(url_for("register"))

        user = User(username=username, email=email)
        user.set_password(password)
        # By default is_admin=False. Make sure only trusted flow can set is_admin=True.
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()

        next_page = request.values.get("next")
        if next_page and not is_safe_url(next_page):
            next_page = None

        if user and user.check_password(password):
            login_user(user)
            session["app_boot_id"] = APP_BOOT_ID
            flash("Logged in successfully.", "success ")
            if next_page:
                return redirect(next_page)
            elif user.is_admin:
                return redirect(url_for("admin_dashboard"))
                
        flash("Invalid credentials.", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.pop("app_boot_id", None)
    flash("Logged out.", "info")
    return redirect(url_for("customer_page"))

@app.route("/admin-login")
@login_required
@admin_required
def admin_login():
    return render_template("login.html")

@app.route("/admin-dashboard")
@login_required
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html")

@app.cli.command("create-admin")
def create_admin_command():
    """Create an admin user interactively: flask create-admin"""
    username = input("username: ").strip()
    email = input("email: ").strip()
    password = getpass("password: ")
    if not username or not password or not email:
        print("username, email and password required")
        return

    if User.query.filter_by(username=username).first():
        print("user exists")
        return

    u = User(username=username, email=email.lower(), is_admin=True)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    print("admin user created")



@app.route("/admin/bookings")
@login_required
@admin_required
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
            "reference": b.reference,
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
@login_required
@admin_required
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
        reference=generate_reference(),
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
            reference=generate_reference(),
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


#manage edit delete bookings admin side
@app.route("/admin/manage-booking/<int:booking_id>", methods=["GET", "POST"])
@login_required
@admin_required
def manage_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    room_types = RoomType.query.all() 

    if request.method == "POST":
        action = request.form.get("action") 
        
        
        #cannot edit cancelled bookings
        if booking.status == "cancelled" and action!="cancel":
          flash("Cancelled bookings cannot be edited.", "danger")
          return redirect("/admin/bookings")


        if action == "cancel":
            booking.status = "cancelled"
            #refund if within 24 hours
            if booking.payment_status == "paid":

                checkin = datetime.strptime(booking.check_in, "%Y-%m-%d")
                hours_until_checkin = (checkin - datetime.utcnow()).total_seconds() / 3600

                if hours_until_checkin > 24:
                  booking.payment_status = "refunded"
                  flash("Booking cancelled. Payment refunded.", "success")
                else:
                  flash("Booking cancelled. Refund not available within 24 hours of check-in.", "warning")

            else:
             flash("Booking cancelled successfully.", "warning")
            
            db.session.commit()
            flash(f"Booking #{booking.id} cancelled successfully.", "warning")
            return redirect("/admin/bookings")
        
        elif action == "check_in":
            if booking.payment_status != "paid":
                 flash("Cannot check in: payment not completed.", "danger")   
                 return redirect("/admin/bookings")
            
            booking.status= "checked_in"
            db.session.commit()
            flash(f"Booking #{booking.id} checked in.", "success")
            return redirect("/admin/bookings")

        elif action == "check_out":
             booking.status = "completed"
             
             room = Room.query.filter_by(current_booking_id=booking.id).first()
             if room:
                room.current_booking_id = None
             
             db.session.commit()
             flash(f"Booking #{booking.id} checked out.", "info")
             return redirect("/admin/bookings")
    
    
    
        elif action == "edit":
            # Update booking details form
            booking.status = request.form.get("status", booking.status)
            booking.payment_status = request.form.get("payment_status", booking.payment_status)
            booking.num_rooms = int(request.form.get("num_rooms", booking.num_rooms))
            booking.num_adults = int(request.form.get("num_adults", booking.num_adults))
            booking.num_children = int(request.form.get("num_children", booking.num_children))
            booking.special_requests = request.form.get("special_requests", booking.special_requests)
            #payment
            payment_status = request.form.get("payment_status", booking.payment_status)
            booking.payment_status = payment_status
     
       
           
           #if new rooom added add to oirignal price 
            room = RoomType.query.get(booking.room_type_id)
            if room:
                ci = datetime.strptime(booking.check_in, "%Y-%m-%d")
                co = datetime.strptime(booking.check_out, "%Y-%m-%d")
                nights = (co - ci).days

                booking.total_amount = room.base_price * nights * booking.num_rooms

            db.session.commit()

            flash(f"Booking #{booking.id} updated successfully.", "success")
            return redirect("/admin/bookings")
           
    
    return render_template("admin_edit_booking.html", booking=booking, room_types=room_types)

#View Rooms
@app.route("/admin/view_rooms")
@login_required
@admin_required
def view_rooms():

     rooms = Room.query.all()
  

     return render_template("view_rooms.html", rooms=rooms)










#edit rooms route add edit remove update rooms.
@app.route("/admin/edit_rooms")
@login_required
@admin_required
def edit_rooms():

    rooms = Room.query.all()

    return render_template("edit_rooms.html", rooms=rooms)








##update room status
@app.route("/admin/update-room-status/<int:room_id>", methods=["POST"])
@admin_required
@login_required
def update_room_status(room_id):

    room = Room.query.get_or_404(room_id)

    status = request.form.get("status")
    price = request.form.get("price")

    room.status = status
    if price:
        room.room_type.base_price = float(price)
    room.updated_at = datetime.utcnow()

    db.session.commit()

    flash("Room updated successfully.", "success")

    return redirect("/admin/edit_rooms")








#seed data 
def seed_data():
    if RoomType.query.first() is not None:
        return

    room_types = [
        RoomType(
            code="STD", name="Standard Room",
            description="Comfortable room with a double bed, en-suite bathroom, TV, and free Wi-Fi. Perfect for solo travellers or couples.",
            max_adults=2, max_children=1, max_occupancy=3,
            base_price=89.00, num_rooms=10,
            photos="/static/standard.png"
        ),
        RoomType(
            code="DLX", name="Deluxe Room",
            description="Spacious room with a king-size bed, seating area, en-suite bathroom with bath, TV, and free Wi-Fi.",
            max_adults=2, max_children=2, max_occupancy=4,
            base_price=129.00, num_rooms=8,
            photos="/static/deluxe.png"
        ),
        RoomType(
            code="FAM", name="Family Suite",
            description="Large suite with a king-size bed and two single beds. Separate living area, en-suite bathroom, TV, and free Wi-Fi. Ideal for families.",
            max_adults=2, max_children=3, max_occupancy=5,
            base_price=189.00, num_rooms=5,
            photos="/static/family.png"
        ),
        RoomType(
            code="EXC", name="Executive Suite",
            description="Premium suite with a king-size bed, separate living room, work desk, luxury bathroom, mini bar, TV, and free Wi-Fi.",
            max_adults=2, max_children=1, max_occupancy=3,
            base_price=249.00, num_rooms=3,
            photos="/static/executive.png"
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
                status="available",
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
