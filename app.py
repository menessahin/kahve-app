import os
import json
import uuid
from contextlib import closing

import psycopg2
import iyzipay
from flask import Flask, request, jsonify, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)

# Render gibi proxy arkasında gerçek kullanıcı IP'sini doğru almak için
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per hour"],
    storage_uri="memory://",
)

# ---- Ayarlar (hepsi ortam değişkenlerinden gelir, koda şifre YAZILMAZ) ----
DATABASE_URL = os.environ["DATABASE_URL"]

options = {
    "api_key": os.environ["IYZICO_API_KEY"],
    "secret_key": os.environ["IYZICO_SECRET_KEY"],
    "base_url": os.environ.get("IYZICO_BASE_URL", "sandbox-api.iyzipay.com"),
}

# Bu kodda sabit test kartı kullanılıyor. Gerçek ödeme almaya kalkmayalım diye
# sandbox dışında uygulamayı başlatmıyoruz.
if "sandbox" not in options["base_url"]:
    raise RuntimeError(
        "Sabit test kartı yalnızca sandbox için. Canlı ödeme için iyzico "
        "Checkout Form entegrasyonuna geçilmeli."
    )

MIN_TUTAR = 1
MAX_TUTAR = 5000
MAX_ISIM = 50
MAX_MESAJ = 200


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def hata(mesaj, kod=400):
    return jsonify({"status": "error", "hata": mesaj}), kod


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ode", methods=["POST"])
@limiter.limit("5 per minute")
def ode():
    # ---- Girdi doğrulama ----
    isim = request.form.get("isim", "").strip()
    mesaj = request.form.get("mesaj", "").strip()
    tutar_raw = request.form.get("tutar", "").strip()

    if not isim or len(isim) > MAX_ISIM:
        return hata(f"İsim 1-{MAX_ISIM} karakter olmalı.")
    if len(mesaj) > MAX_MESAJ:
        return hata(f"Mesaj en fazla {MAX_MESAJ} karakter olabilir.")

    try:
        tutar = int(tutar_raw)  # sadece tam TL kabul ediyoruz
    except ValueError:
        return hata("Tutar tam sayı olmalı.")
    if not (MIN_TUTAR <= tutar <= MAX_TUTAR):
        return hata(f"Tutar {MIN_TUTAR}-{MAX_TUTAR} TL arasında olmalı.")

    tutar_iyzico = f"{tutar}.0"

    # ---- iyzico isteği ----
    req = {
        "locale": "tr",
        "conversationId": str(uuid.uuid4()),
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
            "registerCard": "0",
        },
        "buyer": {
            "id": "BY789",
            "name": isim,
            "surname": "Test",
            "identityNumber": "74300864791",  # sandbox için sahte değer
            "email": "test@test.com",
            "ip": request.remote_addr or "127.0.0.1",
            "registrationAddress": "Test Mahallesi, Istanbul, Turkey",
            "city": "Istanbul",
            "country": "Turkey",
        },
        "shippingAddress": {
            "address": "Test Mahallesi",
            "city": "Istanbul",
            "country": "Turkey",
            "contactName": isim,
        },
        "billingAddress": {
            "address": "Test Mahallesi",
            "city": "Istanbul",
            "country": "Turkey",
            "contactName": isim,
        },
        "basketItems": [
            {
                "id": "KAHVE1",
                "name": "Kahve",
                "category1": "Hediye",
                "itemType": "VIRTUAL",
                "price": tutar_iyzico,
            }
        ],
    }

    try:
        result = iyzipay.Payment().create(req, options)
        response = json.loads(result.read().decode("utf-8"))
        status = response.get("status", "failure")
    except Exception:
        app.logger.exception("iyzico isteği başarısız")
        return hata("Ödeme servisine ulaşılamadı, lütfen tekrar deneyin.", 502)

    # ---- Veritabanına kayıt ----
    try:
        with closing(get_conn()) as conn, conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO payments (sender_name, amount, message, status) "
                "VALUES (%s, %s, %s, %s)",
                (isim, tutar, mesaj, status),
            )
            conn.commit()
    except Exception:
        app.logger.exception("Ödeme veritabanına yazılamadı")

    resp = {"status": status, "isim": isim, "tutar": tutar}
    if status != "success":
        resp["hata"] = response.get("errorMessage", "Ödeme başarısız.")
    return jsonify(resp)


@app.route("/liste")
def liste():
    try:
        with closing(get_conn()) as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT sender_name, amount, message, created_at "
                "FROM payments WHERE status = 'success' "
                "ORDER BY created_at DESC LIMIT 50"
            )
            rows = cursor.fetchall()
    except Exception:
        app.logger.exception("Liste okunamadı")
        return hata("Liste şu an alınamıyor.", 500)

    return jsonify(
        [
            {"isim": r[0], "tutar": r[1], "mesaj": r[2], "tarih": str(r[3])}
            for r in rows
        ]
    )


if __name__ == "__main__":
    app.run(port=5000)  # debug kapalı
