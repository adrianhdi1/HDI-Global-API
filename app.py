from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"message": "HDI API LIVE 🚀"})

@app.route("/hdi/pay")
def pay():
    return jsonify({"message": "Payment endpoint working 💰"})

if __name__ == "__main__":
    app.run()
