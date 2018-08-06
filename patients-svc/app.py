import os
import sqlite3
import random
import string

from flask import Flask, request, g
from flask_restful import Resource, Api, reqparse

app = Flask(__name__)
api = Api(app)

def get_db():
    if getattr(g, 'db', None) == None:
        g.db = sqlite3.connect(os.getenv('SQLITE_DB', 'database.db'))
    return g.db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()

class PatientRequestParser:
    def __init__(self, parser):
        self._parser = parser
        self._parser.add_argument('first_name', required=True, type=str, location='json')
        self._parser.add_argument('middle_name', required=True, type=str, location='json')
        self._parser.add_argument('last_name', required=True, type=str, location='json')
        self._parser.add_argument('email', required=True, type=str, location='json')
        self._parser.add_argument('dob', required=True, type=str, location='json')
        self._parser.add_argument('gender', required=True, type=str, location='json')
        self._parser.add_argument('status', required=True, type=str, location='json')
        self._parser.add_argument('terms_accepted', required=True, type=int, location='json')
        self._parser.add_argument('terms_accepted_at', required=True, type=str, location='json')
        self._parser.add_argument('address_street', required=True, type=str, location='json')
        self._parser.add_argument('address_city', required=True, type=str, location='json')
        self._parser.add_argument('address_state', required=True, type=str, location='json')
        self._parser.add_argument('address_zip', required=True, type=str, location='json')
        self._parser.add_argument('phone', required=True, type=str, location='json')

    def parse(self):
        return self._parser.parse_args(strict=True)

class Patients(Resource):
    def __init__(self, **kwargs):
        self.db = get_db()
        self._defaults = { 'limit': 20, 'offset': 0 }
        self.request_parser = kwargs['request_parser']

    def post(self):
        request = self.request_parser.parse()
        cur = self.db.cursor()
        props = [prop for prop, _ in request.items()]
        vals = [val for _, val in request.items()]
        props.append('id')
        new_id = self._generate_id()
        vals.append(new_id)

        insert = 'INSERT INTO person ({0}) VALUES ({1})'
        insert_query = insert.format(', '.join(props), ', '.join(['?'] * len(vals)))
        cur.execute(insert_query, vals)
        self.db.commit()
        response = { 'id': new_id }
        response.update(request)
        return response, 201

    def get(self):
        cur = self.db.cursor()
        cur.execute('SELECT * FROM person LIMIT ? OFFSET ?', (
            self._params('limit'),
            self._params('offset'),
        ))

        rows = cur.fetchall()
        response = [{cur.description[i][0]: val for i,
                    val in enumerate(row)} for row in rows]
        return response, 200

    def _params(self, key):
        args = request.args
        if key in args:
            return args[key]
        return self._defaults[key]

    def _generate_id(self):
        return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))

class Patient(Resource):
    def __init__(self, **kwargs):
        self.db = get_db()
        self.request_parser = kwargs['request_parser']
    
    def get(self, id):
        cur = self.db.cursor()
        cur.execute('SELECT * from person WHERE id = ?', (id,))
        patient = cur.fetchone()
        response = {cur.description[i][0]: val for i, val in enumerate(patient)}
        return response, 200

    def put(self, id):        
        cur = self.db.cursor()
        request = self.request_parser.parse()
        props = [prop for prop, _ in request.items()]
        vals = [val for _, val in request.items()]
        vals.append(id)

        update = 'UPDATE person SET {0} WHERE id = ?'
        update_args = ['{0} = ?'.format(props[i]) for i in range(len(props))]
        update_query = update.format(', '.join(update_args))
        cur.execute(update_query, vals)
        self.db.commit()
        return None, 204

    def delete(self, id):
        cur = self.db.cursor()
        cur.execute('DELETE FROM person WHERE id = ?', (id,))
        self.db.commit()
        return None, 204

if __name__ == '__main__':
    api.add_resource(Patients, '/patients', resource_class_kwargs={ 'request_parser': PatientRequestParser(reqparse.RequestParser()) })
    api.add_resource(Patient, '/patients/<string:id>', resource_class_kwargs={ 'request_parser': PatientRequestParser(reqparse.RequestParser()) })
    app.run(debug=os.getenv('debug', True), host="0.0.0.0", port=5000)
