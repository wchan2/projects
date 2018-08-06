import os
import sqlite3

from flask import Flask, g
from flask_restful import Api, reqparse

from patient.resource import Patients, Patient, PatientRequestParser
from patient.repository import PatientRepository


def get_db():
    if getattr(g, 'db', None) == None:
        g.db = sqlite3.connect(os.getenv('SQLITE_DB', 'database.db'))
    return g.db

app = Flask(__name__)
api = Api(app)

patient_kwargs = {'request_parser': PatientRequestParser(reqparse.RequestParser()), 'get_db': get_db}
api.add_resource(Patients, '/patients', resource_class_kwargs=patient_kwargs)
api.add_resource(Patient, '/patients/<string:id>', resource_class_kwargs=patient_kwargs)

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()

if __name__ == '__main__':
    app.run(debug=not os.getenv('debug', False), host="0.0.0.0", port=5000)
