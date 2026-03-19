from app import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    user = User(
        username="Kyle",
        email="kyle@atu.ie",
        is_admin=True
    )
    user.set_password("ThisStrongPassword123!")
    db.session.add(user)
    db.session.commit()
    print(generate_password_hash("ThisStrongPassword123!"))
