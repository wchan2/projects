# Patient Service

CRUD app that lists, creates, reads, updates and deletes patient data

## Tool Dependencies

- [Docker](https://www.docker.com/)
- [docker-compose](https://docs.docker.com/compose/)

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