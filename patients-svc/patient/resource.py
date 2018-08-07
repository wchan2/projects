from flask import request
from flask_restful import Resource
from patient.repository import PatientRepository
from patient.request_parser import PatientRequestParser

class Patients(Resource):
    def __init__(self, **kwargs):
        self._defaults = {'limit': 20, 'offset': 0}
        self._request_parser = kwargs['request_parser']
        self._patient_repo = PatientRepository(kwargs['get_db']())

    def post(self):
        request = self._request_parser.parse()
        validation_errors = self._request_parser.validate(request)
        if len(validation_errors) != 0:
            return validation_errors, 422

        new_id = self._patient_repo.create(request.copy())
        response = {'id': new_id}
        response.update(request.copy())

        return response, 201

    def get(self):
        response = self._patient_repo.list(
            self._params('limit'), self._params('offset'))
        return response, 200

    def _params(self, key):
        args = request.args
        if key in args:
            return args[key]
        return self._defaults[key]

class Patient(Resource):
    def __init__(self, **kwargs):
        self._request_parser = kwargs['request_parser']
        self._patient_repo = PatientRepository(kwargs['get_db']())

    def get(self, id):
        response = self._patient_repo.find_by_id(id)
        if response == None:
            return '', 404
        response['terms_accepted'] = int(response['terms_accepted'])
        return response, 200

    def put(self, id):
        request = self._request_parser.parse()
        validation_errors = self._request_parser.validate(request)
        if len(validation_errors) != 0:
            return validation_errors, 422

        self._patient_repo.update(id, request.copy())
        return None, 204

    def delete(self, id):
        self._patient_repo.delete(id)
        return None, 204
