ARG AIRFLOW_BASE=apache/airflow:3.3.1
FROM ${AIRFLOW_BASE}
COPY requirements-aws.txt requirements-airflow.txt /tmp/pipeline-deps/
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/pipeline-deps/requirements-aws.txt
RUN python -c "import psycopg2; from airflow.providers.fab.auth_manager.fab_auth_manager import FabAuthManager"
COPY --chown=airflow:root scripts /opt/soccer/scripts
COPY --chown=airflow:root sql /opt/soccer/sql
COPY --chown=airflow:root data/live_matches.csv data/teams.csv data/venues.csv /opt/soccer/historical-data/
COPY --chown=airflow:root deploy/aws/demo/demo_dag.py deploy/aws/demo/bootstrap.py deploy/aws/demo/staging_permissions.py /opt/soccer/
COPY dags/soccer_pipeline_dag.py /tmp/soccer_pipeline_dag.py
RUN python /opt/soccer/demo_dag.py /tmp/soccer_pipeline_dag.py /opt/airflow/dags/premier_league_demo.py
ENV PYTHONPATH=/opt/soccer:/opt/soccer/scripts HISTORICAL_DATA_DIR=/opt/soccer/historical-data
