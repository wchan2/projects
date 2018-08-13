# Parsing Contacts Data

Given a file with the following valid formats, normalize the output also in the following

## Valid formats

- Phone numbers should be 10 digits and may contain letters
- Zip codes are only 5 digits

```
Lastname, Firstname, (703)-742-0996, Blue, 10013
Firstname Lastname, Red, 11237, 703 955 0373
Firstname, Lastname, 10013, 646 111 0101, Green
```

## Output

```json
{
    "entries": [
        {
            "color": "yellow",
            "firstname": "James",
            "lastname": "Murphy",
            "phonenumber": "018-154-6474",
            "zipcode": "83880"
        }
    ],
    "errors": [
        1,
        3
    ]
}
```

## Commands to execute the program

```bash
# use `data.in` as the file to read from
# use `data.json` as the file to output to
python contacts.py -input data.in -output data.json

# running tests
python contacts_test.py
```

