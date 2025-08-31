from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route("/")
def home():
    return "Fresh Flask app is working!"

@app.route("/test")
def test():
    print("🔥 TEST ROUTE CALLED!")
    return "Test works!"

@app.route("/api/test", methods=["GET", "POST"])
def api_test():
    print("🔥 API TEST CALLED!")
    return jsonify({"message": "API works!", "method": request.method})

if __name__ == "__main__":
    print("🚀 Starting fresh test app...")
    app.run(host="0.0.0.0", port=5000, debug=True)