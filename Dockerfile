FROM apache/airflow:2.0.2-python3.8

WORKDIR /opt/airflow

COPY requirements.txt requirements.txt

RUN pip install -r requirements.txt