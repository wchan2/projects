FROM python:3

WORKDIR /usr/local/opt

ENV debug=false
ENV SQLITE_DB=database.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "app.py"]
