import string
import random

class PatientRepository:
    def __init__(self, db):
        self.db = db

    def find_by_id(self, id):
        cur = self.db.cursor()
        cur.execute('SELECT * from person WHERE id = ?', (id,))
        patient = cur.fetchone()
        if patient == None:
            return None
        return {cur.description[i][0]: val for i, val in enumerate(patient)}

    def list(self, limit, offset):
        cur = self.db.cursor()
        cur.execute('SELECT * FROM person LIMIT ? OFFSET ?', (limit, offset))
        rows = cur.fetchall()
        return [{cur.description[i][0]: val for i, val in enumerate(row)} for row in rows]

    def create(self, patient):
        cur = self.db.cursor()
        props = [prop for prop, _ in patient.items()]
        vals = [val for _, val in patient.items()]
        props.append('id')
        new_id = self._generate_id()
        vals.append(new_id)

        insert = 'INSERT INTO person ({0}) VALUES ({1})'
        insert_query = insert.format(
            ', '.join(props), ', '.join(['?'] * len(vals)))
        cur.execute(insert_query, vals)
        self.db.commit()
        return new_id

    def update(self, id, patient):
        cur = self.db.cursor()

        props = [prop for prop, _ in patient.items()]
        vals = [val for _, val in patient.items()]
        vals.append(id)

        update = 'UPDATE person SET {0} WHERE id = ?'
        update_args = ['{0} = ?'.format(props[i]) for i in range(len(props))]
        update_query = update.format(', '.join(update_args))
        cur.execute(update_query, vals)
        self.db.commit()
        return True

    def delete(self, id):
        cur = self.db.cursor()
        cur.execute('DELETE FROM person WHERE id = ?', (id,))
        self.db.commit()
        return True

    def _generate_id(self):
        return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
