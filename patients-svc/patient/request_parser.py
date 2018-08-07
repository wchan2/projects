from datetime import datetime

class PatientRequestParser:
    GENDER = ['male', 'female']
    STATUS = ['active', 'inactive']

    def __init__(self, parser):
        self._parser = parser
        self._parser.add_argument(
            'first_name', required=True, type=str, location='json')
        self._parser.add_argument(
            'middle_name', required=True, type=str, location='json')
        self._parser.add_argument(
            'last_name', required=True, type=str, location='json')
        self._parser.add_argument(
            'email', required=True, type=str, location='json')
        self._parser.add_argument(
            'dob', required=True, type=str, location='json')
        self._parser.add_argument(
            'gender', required=True, type=str, location='json')
        self._parser.add_argument(
            'status', required=True, type=str, location='json')
        self._parser.add_argument(
            'terms_accepted', required=True, type=int, location='json')
        self._parser.add_argument(
            'terms_accepted_at', required=True, type=str, location='json')
        self._parser.add_argument(
            'address_street', required=True, type=str, location='json')
        self._parser.add_argument(
            'address_city', required=True, type=str, location='json')
        self._parser.add_argument(
            'address_state', required=True, type=str, location='json')
        self._parser.add_argument(
            'address_zip', required=True, type=str, location='json')
        self._parser.add_argument(
            'phone', required=True, type=str, location='json')

    def parse(self):
        return self._parser.parse_args(strict=True)

    @classmethod
    def validate(cls, args):
        errors = []
        err = cls.validate_gender(args['gender'])
        if err != None:
            errors.append(err)
        err = cls.validate_status(args['status'])
        if err != None:
            errors.append(err)
        err = cls.validate_age(args['dob'])
        if err != None:
            errors.append(err)

        return errors

    @classmethod
    def validate_date(cls, date):
        try:
            datetime.strptime(date, '%m-%d-%Y')
        except ValueError:
            return 'Invalid date format; format should be MM-DD-YYYY'

    @classmethod
    def validate_gender(cls, gender):
        if gender in cls.GENDER:
            return None
        return 'Invalid gender; value should be `male` or `female`, case sensitive'
    
    @classmethod
    def validate_status(cls, status):
        if status in cls.STATUS:
            return None
        return 'Invalid value for `status`; value should be either `inactive` or `active`'
    
    @classmethod
    def validate_age(cls, dob):
        err = cls.validate_date(dob)
        if err != None:
            return err
        birthday = datetime.strptime(dob, '%m-%d-%Y')
        today = datetime.today()
        age = today.year - birthday.year
        is_greater_than_8 = age >= 8
        if (today.month == birthday.month and today.day < birthday.day) or today.month < birthday.month:
            is_greater_than_8 = age - 1 >= 8
        if is_greater_than_8:
            return None
        return 'Invalid age; patient age must be greater than 8'

    @classmethod
    def validate_phone(cls, phone):
        pass

    @classmethod
    def validate_address(cls, address):
        pass

    @classmethod
    def validate_email(cls, email):
        pass
