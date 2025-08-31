from flask import Flask, request, jsonify
from sqlalchemy import create_engine, Column, Integer, String, Enum, ForeignKey, DECIMAL, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import requests

# === CONFIG ===
BOT_TOKEN = "8042603273:AAFZpfKNICr57kYBkexm1MmcJLU_2mTSRmA"
DATABASE_URL = "mysql+pymysql://postgres:congashop123laoidnfo2ndo@localhost:3306/diamond_shop"

# === FLASK SETUP ===
app = Flask(__name__)

# === SQLAlchemy SETUP ===
engine = create_engine(DATABASE_URL, echo=True)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

# === MODELS ===
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True)
    username = Column(String)
    role = Column(Enum("user","admin"), default="user")
    purchases = relationship("Purchase", back_populates="user")

class DiamondPrice(Base):
    __tablename__ = "diamond_prices"
    id = Column(Integer, primary_key=True)
    amount = Column(Integer)
    price = Column(DECIMAL(10,2))

class Purchase(Base):
    __tablename__ = "purchases"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    game_id = Column(String)
    server_id = Column(String)
    amount = Column(Integer)
    slip_file_id = Column(String)
    status = Column(Enum("PENDING","DONE","FAILED"), default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="purchases")

Base.metadata.create_all(bind=engine)

# === HELPER: Notify user via Telegram ===
def notify_user(telegram_id, message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": telegram_id,
        "text": message
    }
    requests.post(url, json=payload)

# === ROUTES ===
@app.route("/purchase", methods=["POST"])
def create_purchase():
    data = request.json
    user = session.query(User).filter_by(telegram_id=data["telegram_id"]).first()
    if not user:
        user = User(telegram_id=data["telegram_id"], username=data.get("username",""))
        session.add(user)
        session.commit()

    purchase = Purchase(
        user_id=user.id,
        game_id=data["game_id"],
        server_id=data["server_id"],
        amount=data["amount"],
        slip_file_id=data["slip_file_id"],
        status="PENDING"
    )
    session.add(purchase)
    session.commit()
    return jsonify({"message":"Purchase created","purchase_id":purchase.id})

@app.route("/purchase/<int:purchase_id>/status", methods=["PATCH"])
def update_purchase_status(purchase_id):
    data = request.json
    purchase = session.query(Purchase).get(purchase_id)
    if not purchase:
        return jsonify({"error":"Purchase not found"}), 404
    purchase.status = data["status"]
    session.commit()
    # Notify user via bot
    notify_user(purchase.user.telegram_id, f"Your purchase of {purchase.amount} diamonds is now {purchase.status}")
    return jsonify({"message":"Status updated"})

@app.route("/purchases/<telegram_id>", methods=["GET"])
def get_user_purchases(telegram_id):
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        return jsonify({"purchases":[]})
    result = []
    for p in user.purchases:
        result.append({
            "id": p.id,
            "game_id": p.game_id,
            "server_id": p.server_id,
            "amount": p.amount,
            "status": p.status,
            "created_at": p.created_at
        })
    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
