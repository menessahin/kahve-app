from flask import Flask, request, jsonify, render_template
import psycopg2
import iyzipay
import json

app = Flask(__name__)

options = {
    "api_key": "sandbox-XEsYzmCEAcREh0ygeCpbRzDTIKlfgsqC",
    "secret_key": "sandbox-8OkML6PnUJlSlyZIUoml160ajUlj88xZ",
    "base_url": "sandbox-api.iyzipay.com"
}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/ode", methods=["POST"])
def ode():
    conn = psycopg2.connect("postgresql://neondb_owner:npg_F4yGW9RCvqhg@ep-silent-bonus-asc1bk7o-pooler.c-4.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
    cursor = conn.cursor()

    isim = request.form["isim"]
    tutar = request.form["tutar"]
    tutar_iyzico = "{:.1f}".format(float(tutar))
    tutar_db = int(float(tutar))
    mesaj = request.form["mesaj"]

    req = {
        "locale": "tr",
        "conversationId": "123456789",
        "price": tutar_iyzico,
        "paidPrice": tutar_iyzico,
        "currency": "TRY",
        "installment": "1",
        "paymentChannel": "WEB",
        "paymentGroup": "PRODUCT",
        "paymentCard": {
            "cardHolderName": "Test Kullanıcı",
            "cardNumber": "5528790000000008",
            "expireMonth": "12",
            "expireYear": "2030",
            "cvc": "123",
            "registerCard": "0"
        },
        "buyer": {
            "id": "BY789",
            "name": isim,
            "surname": "Test",
            "identityNumber": "74300864791",
            "email": "test@test.com",
            "ip": "85.34.78.112",
            "registrationAddress": "Test Mahallesi, Istanbul, Turkey",
            "city": "Istanbul",
            "country": "Turkey"
        },
        "shippingAddress": {
            "address": "Test Mahallesi",
            "city": "Istanbul",
            "country": "Turkey",
            "contactName": isim
        },
        "billingAddress": {
            "address": "Test Mahallesi",
            "city": "Istanbul",
            "country": "Turkey",
            "contactName": isim
        },
        "basketItems": [
            {
                "id": "KAHVE1",
                "name": "Kahve",
                "category1": "Hediye",
                "itemType": "VIRTUAL",
                "price": tutar_iyzico
            }
        ]
    }

    result = iyzipay.Payment().create(req, options)
    response = json.loads(result.read().decode("utf-8"))
    status = response["status"]

    cursor.execute(
        "INSERT INTO payments (sender_name, amount, message, status) VALUES (%s, %s, %s, %s)",
        (isim, tutar_db, mesaj, status)
    )
    conn.commit()
    conn.close()

    return jsonify({"status": status, "isim": isim, "tutar": tutar_db})

@app.route("/liste")
def liste():
    conn = psycopg2.connect("postgresql://neondb_owner:npg_F4yGW9RCvqhg@ep-silent-bonus-asc1bk7o-pooler.c-4.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
    cursor = conn.cursor()
    cursor.execute("SELECT sender_name, amount, message, created_at FROM payments ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{"isim": r[0], "tutar": r[1], "mesaj": r[2], "tarih": str(r[3])} for r in rows])

if __name__ == "__main__":
    app.run(debug=True)