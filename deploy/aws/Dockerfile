FROM apache/airflow:3.3.1
COPY requirements-aws.txt requirements-airflow.txt /tmp/pipeline-deps/
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/pipeline-deps/requirements-aws.txt
COPY --chown=airflow:root scripts /opt/soccer/scripts
COPY --chown=airflow:root run_pipeline.py /opt/soccer/run_pipeline.py
COPY --chown=airflow:root data/live_matches.csv data/teams.csv data/venues.csv /opt/soccer/historical-data/
COPY --chown=airflow:root dags /opt/airflow/dags
COPY --chown=airflow:root deploy/aws/certs/global-bundle.pem /opt/soccer/certs/global-bundle.pem
ENV PYTHONPATH=/opt/soccer HISTORICAL_DATA_DIR=/opt/soccer/historical-data
