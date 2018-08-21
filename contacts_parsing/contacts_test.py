import unittest
from contacts import full_name, first_name, last_name, phone_number, zip_code, color, normalize_record

class TestFirstName(unittest.TestCase):
    def test_first_name_with_capitalize_letter(self):
        self.assertEqual({'firstname': 'Foo'}, first_name(
            'Foo'), 'Expect first name with capitalize word to be returned')

    def test_first_name_with_all_lowercase(self):
        self.assertEqual({'firstname': 'foo'}, first_name('foo'), 'Expect first name with all lowercase letters to be returned')

    def test_first_name_with_all_uppercase(self):
        self.assertEqual({'firstname': 'FOO'}, first_name(
                    'FOO'), 'Expect first name with all uppercase letters to be returned')
    
    def test_first_name_with_camelcase(self):
        self.assertEqual({'firstname': 'FoO'}, first_name(
            'FoO'), 'Expect first name with camelcase letters to be returned')
        self.assertEqual({'firstname': 'foO'}, first_name(
            'foO'), 'Expect first name with camelcase letters to be returned')

    def test_invalid_characters(self):
        invalid_chars = ['+', '-', '$', '%', '^', '&', '*', '(', ')', '!', '@', '#', '<', '>', '?', '/', '\\', '[', ']', '{', '}', '=']
        for char in invalid_chars:
            with self.assertRaises(ValueError):
                first_name('test{0}firstname'.format(char))

class TestLastName(unittest.TestCase):
    def test_last_name_capitalize_letter(self):
        self.assertEqual({'lastname': 'Foo'}, last_name('Foo'), 'Expect last name with capitalize word to be returned')

    def test_last_name_all_lowercase(self):
        self.assertEqual({'lastname': 'foo'}, last_name(
            'foo'), 'Expect last name with all lowercase letters to be returned')

    def test_last_name_all_uppercase(self):
        self.assertEqual({'lastname': 'FOO'}, last_name(
            'FOO'), 'Expect last name with all uppercase letters to be returned')

    def test_last_name_camelcase(self):
        self.assertEqual({'lastname': 'FoO'}, last_name(
            'FoO'), 'Expect last name with camelcase letters to be returned')
        self.assertEqual({'lastname': 'foO'}, last_name(
            'foO'), 'Expect last name with camelcase letters to be returned')

    def test_last_name_invalid_characters(self):
        invalid_chars = ['+', '-', '$', '%', '^', '&', '*', '(', ')', '!', '@', '#', '<', '>', '?', '/', '\\', '[', ']', '{', '}', '=']
        for char in invalid_chars:
            with self.assertRaises(ValueError):
                last_name('test{0}lastname'.format(char))

class TestFullName(unittest.TestCase):
    def test_full_name_with_capitalize_letter(self):
        self.assertEqual({'firstname': 'Foo', 'lastname': 'Bar'}, full_name(
            'Foo Bar'), 'Expect full name to return with first name and last name')

    def test_full_name_with_all_uppercase(self):
        self.assertEqual({'firstname': 'FOO', 'lastname': 'BAR'}, full_name(
            'FOO BAR'), 'Expect full name with all uppercase letters to be returned')

    def test_full_name_with_camelcase(self):
        self.assertEqual({'firstname': 'foO', 'lastname': 'baR'}, full_name(
            'foO baR'), 'Expect full name with camelcase letters to be returned')
        self.assertEqual({'firstname': 'FoO', 'lastname': 'BaR'}, full_name(
            'FoO BaR'), 'Expect full name with camelcase letters to be returned')

    def test_full_name_with_invalid_characters(self):
        invalid_chars = ['+', '-', '$', '%', '^', '&', '*',
                         '(', ')', '!', '@', '#', '<', '>', '?', '/', '\\', '[', ']', '{', '}', '=']
        for char in invalid_chars:
            with self.assertRaises(ValueError):
                full_name('First{0} La{0}st'.format(char))

class TestColor(unittest.TestCase):
    def test_color_with_capitalize_letter(self):
        self.assertEqual({'color': 'Blue'}, color(
            'Blue'), 'Expect color with capitalize word to be returned')

    def test_color_with_all_lowercase(self):
        self.assertEqual({'color': 'blue'}, color(
            'blue'), 'Expect color with all lowercase letters to be returned')

    def test_color_with_all_uppercase(self):
        self.assertEqual({'color': 'BLUE'}, color(
            'BLUE'), 'Expect color with all uppercase letters to be returned')

    def test_color_with_camelcase(self):
        self.assertEqual({'color': 'BluE'}, color(
            'BluE'), 'Expect color with camelcase letters to be returned')
        self.assertEqual({'color': 'bluE'}, color(
            'bluE'), 'Expect color with camelcase letters to be returned')
    
    def test_color_with_space(self):
        self.assertEqual({'color': 'aqua marine'}, color('aqua marine'), 'Expect color with space to be returned')

    def test_invalid_characters(self):
        invalid_chars = ['+', '-', '$', '%', '^', '&', '*', '(', ')', '!', '@', '#', '<', '>', '?', '/', '\\', '[', ']', '{', '}', '=']
        for char in invalid_chars:
            with self.assertRaises(ValueError):
                color('aqua{0}marine'.format(char))

class TestZipCode(unittest.TestCase):
    def test_alphanumeric_zipcode(self):
        with self.assertRaises(ValueError):
            zip_code('1a2a3')
    
    def test_zipcode_with_letters(self):
        with self.assertRaises(ValueError):
            zip_code('abcde')

    def test_zipcode_with_more_than_five_digits(self):
        with self.assertRaises(ValueError):
            zip_code('123456')

    def test_zipcode_with_five_digits(self):
        self.assertEqual({'zipcode': '12345'}, zip_code('12345'), 'Expect zip code with 5 digits to return')

class TestPhoneNumber(unittest.TestCase):
    def test_10_digits(self):
        phone_numbers = [
            '6765457599',
            '676545-7599',
            '(676) 545-7599',
            '(676)545-7599',
            '(676)5457599',
            '(676)545 7599',
            '(676)-545-7599',
            '(676)-5457599',
            '(676-5457599',
            '(676-545-7599',
            '(676 5457599',
            '(676 545 7599',
            '(676545 7599',
            '676)-545-7599',
            '676)545-7599',
            '676) 545-7599',
            '676) 545 7599',
            '676) 545 7599',
            '6a7b6c5d4e5e7e5e9a9',
            '676A545 7599',
        ]
        for num in phone_numbers:
            self.assertEqual({'phonenumber': '676-545-7599'}, phone_number(num))

    def test_invalid_phone_numbers(self):
        invalid_phone_numbers = [
            '6a7b6c5d4e5e7e5e9a90',
            '12345678901',
            'ABCDEFGHIJKLMNOP',
            'abc',
            '123',
            '(*@&#)',
        ]
        for num in invalid_phone_numbers:
            with self.assertRaises(ValueError):
                phone_number(num)

if __name__ == '__main__':
    unittest.main()
