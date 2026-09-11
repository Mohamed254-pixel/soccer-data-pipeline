FROM apache/airflow:3.3.1

COPY requirements-airflow.txt .

RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r requirements-airflow.txt