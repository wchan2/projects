import pytest
from app import app
import json

@pytest.fixture
def client():
    client = app.test_client()
    yield client

def test_patients_limit(client):
    response = client.get('/patients?limit=10')
    patients = json.loads(response.data)
    assert len(patients) == 10

def test_patients_offset(client):
    ten_entries = json.loads(client.get('/patients?limit=10').data)
    second_five = json.loads(client.get('/patients?limit=5&offset=5').data)
    assert ten_entries[5:] == second_five

def test_patients_crud(client):
    create_response = client.post('/patients', json={
        "first_name": "Foo",
        "middle_name": "Bar",
        "last_name": "Baz",
        "email": "foo@baz.com",
        "dob": "01-01-2008",
        "gender": "male",
        "status": "active",
        "terms_accepted": 0,
        "terms_accepted_at": "2017-09-30T05:37:31.700Z",
        "address_street": "11 ABC Street",
        "address_city": "New York",
        "address_state": "NY",
        "address_zip": "10002",
        "phone": "212-732-6445"
    })

    create_data = json.loads(create_response.data)
    patient_path = '/patients/{0}'.format(create_data['id'])
    get_patient_response = client.get(patient_path)
    assert json.loads(create_response.data) == json.loads(get_patient_response.data), 'Expected to retrieve the created patient'

    update_patient_request = {
        "first_name": "Foo",
        "middle_name": "Bar",
        "last_name": "Baz",
        "email": "foo@qux.com",
        "dob": "01-01-2007",
        "gender": "male",
        "status": "active",
        "terms_accepted": 0,
        "terms_accepted_at": "2017-09-30T05:37:31.700Z",
        "address_street": "11 ABC Street",
        "address_city": "New York",
        "address_state": "NY",
        "address_zip": "10002",
        "phone": "212-732-6445"
    }
    update_patient_response = client.put(patient_path, json=update_patient_request)
    assert update_patient_response.status_code == 204, 'Expected update response status code to be 204 but got {0}'.format(update_patient_response.status_code)
    get_patient_response = client.get(patient_path)
    get_patient_data = json.loads(get_patient_response.data)
    del get_patient_data['id']
    assert update_patient_request == get_patient_data, 'Expected to retrieve the updated patient'

    delete_response = client.delete(patient_path)
    assert delete_response.status_code == 204, 'Expected delete response status to be 204 but got {0}'.format(delete_response.status)
    get_patient_data = json.loads(client.get(patient_path).data)
    assert get_patient_data == '', 'Expected deleted patient to be empty but got `{0}`'.format(get_patient_data)

def test_create_patient_age_less_than_8(client):
    pass

def test_create_patient_bad_dob(client):
    pass
