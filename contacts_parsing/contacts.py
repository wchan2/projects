#!/usr/bin/env python

import re
import csv
import json
import argparse
import sys

def first_name(string):
    val = re.match(r'^[a-zA-Z]*$', string)
    if val == None:
        raise ValueError('Did not match first name')
    return {'firstname': val.group()}

def last_name(string):
    val = re.match(r'^[a-zA-Z]*$', string)
    if val == None:
        raise ValueError('Did not match last name')
    return {'lastname': val.group()}

def full_name(string):
    result = {}
    words = string.split()
    if len(words) != 2:
        raise ValueError('Did not match full name')
    first, last = words
    result.update(first_name(first.strip()))
    result.update(last_name(last.strip()))
    return result

def phone_number(string):
    val = re.findall(r'[0-9]', string)
    if val == None or len(val) != 10:
        raise ValueError
    phone = val[:3] + ['-'] + val[3:6] + ['-'] + val[6:]
    return {'phonenumber': ''.join(phone)}

def color(string):
    val = re.match(r'^[a-zA-Z\s]*$', string)
    if val == None:
        raise ValueError('Did not match color')
    return {'color': val.group()}

def zip_code(string):
    val = re.match(r'^[0-9]{5}$', string)
    if val == None:
        raise ValueError('Did not match zip code')
    return {'zipcode': val.group()}

def format_record(values, fmt):
    result = {}
    for i, fn in enumerate(fmt):
        result.update(fn(values[i].strip()))
    return result

valid_formats = [
    [full_name, color, zip_code, phone_number],
    [last_name, first_name, phone_number, color, zip_code],
    [first_name, last_name, zip_code, phone_number, color],
]

def normalize_record(values):
    fmts = filter(lambda f: len(f) == len(values), valid_formats)
    for fmt in fmts:
        try:
            return format_record(values, fmt)
        except ValueError:
            continue
    raise ValueError

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-input', type=str, help='Filename of the file to read contacts')
    parser.add_argument('-output', type=str, help='Filename of the file to store the normalized contacts information')
    args = parser.parse_args()
    if args.input == None or args.output == None:
        parser.print_help()
        sys.exit(1)
    with open(args.input) as f:
        contacts_reader = csv.reader(f, delimiter=',')
        results = []
        errors = []
        for i, row in enumerate(contacts_reader):
            try:
                results.append(normalize_record(row))
            except ValueError as e:
                errors.append(i)

    with open(args.output, 'w') as f:
        json.dump({
            'entries': results,
            'errors': errors,
        }, f, sort_keys=True, indent=2)
