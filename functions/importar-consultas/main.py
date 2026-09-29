import functions_framework
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@functions_framework.http
def importar_consultas(request):
    return jsonify({"message": "Hello from Cloud Function"})