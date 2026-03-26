from app import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    user1 = User(
        username="Kyle",
        email="kyle@atu.ie",
        is_admin=True
    )
    user1.set_password("ThisStrongPassword123!")
   


    user2 = User(
        username="test",
        email="test@atu.ie",
        is_admin=False
    )
    user2.set_password("test")

  
    db.session.add(user1)
    db.session.add(user2)
    db.session.commit()
  
    print(generate_password_hash("ThisStrongPassword123!"))
    print(generate_password_hash("test!"))