# Patient Service

CRUD app that lists, creates, reads, updates and deletes patient data

## Tool Dependencies

- [Docker](https://www.docker.com/)
- [docker-compose](https://docs.docker.com/compose/)

## Frameworks & Libraries Used

- [Flask](http://flask.pocoo.org/)
- [Flask-RESTful](https://flask-restful.readthedocs.io/en/latest/)
- [pytest](https://docs.pytest.org/en/latest/)

## Environment Variables

- `debug` - setting this to any value will turn it off
- `SQLITE3_DB` - filename of the database file

## Useful Commands

```sh
make start # build the image and start the application
make test  # run tests (works only when application is started)
make clean # removes the Docker container and 
make logs  # watch application logs
```

## Resetting the local environment

```sh
# Resetting the database
sqlite3 database.db

# When inside sqlite3
.mode csv
.import person.csv person
```

## Areas of improvement

- Add unit tests
- Return age on get requests
- Add database schema: enums for `status`, `terms_accepted` and `gender` and automatically set the date for `terms_accepted_at`
- Remove `terms_accepted_at` for HTTP requests
- Add patient data validation: `phone`, `age`, `dob`, `email` and enumerated fields
- Add patient response marshaling
- Add database migration strategy
- Add test fixtures instead of using the current database for testing
