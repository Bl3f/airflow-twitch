import os
import json
import tempfile

from airflow import DAG
from airflow.utils.dates import parse_execution_date
from airflow.operators.python import PythonOperator
from airflow.providers.google.cloud.hooks.gcs import GCSHook
from airflow.providers.google.cloud.transfers.gcs_to_bigquery import GCSToBigQueryOperator
from airflow.providers.google.cloud.operators.bigquery import BigQueryCreateEmptyDatasetOperator
from airflow.models import Variable

import twitch

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email': ['airflow@example.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
}

STREAMERS = Variable.get("STREAMERS", "blef__").split(",")
GCP_CONN_ID = os.getenv("GCP_CONN_ID")
PROJECT_ID = os.getenv("PROJECT_ID")
BUCKET_NAME = os.getenv("BUCKET_NAME")


def get_chat_history(ds, gcp_conn_id, bucket, path):
    client = twitch.Helix(os.getenv("TWITCH_CLIENT_ID"), os.getenv("TWITCH_CLIENT_SECRET"))
    hook = GCSHook(gcp_conn_id=gcp_conn_id)

    tmp = tempfile.NamedTemporaryFile()

    for streamer_name in STREAMERS:
        with open(tmp.name, "w") as f:
            streamer = client.user(streamer_name)
            for video in streamer.videos():
                if ds in video.created_at:
                    for comment in video.comments:
                        content = comment.data
                        if "user_notice_params" in content["message"]:
                            content["message"]["user_notice_params"] = {
                                key.replace("-", "_"): value for key, value in content["message"]["user_notice_params"].items()
                            }
                        f.write(f"{json.dumps(content)}\n")

            hook.upload(
                bucket_name=bucket, 
                object_name=os.path.join(path, f"{streamer_name}/{ds}.json"),
                filename=f.name,
            )


with DAG(
    'chat-saver',
    default_args=default_args,
    description='A simple DAG to get chat from Twitch streams and save it to BigQuery.',
    schedule_interval="0 2 * * *",
    catchup=True,
    start_date=parse_execution_date("2021-04-01"),
) as dag:
    t1 = PythonOperator(
        task_id="get_chat_history",
        python_callable=get_chat_history,
        op_kwargs={"gcp_conn_id": GCP_CONN_ID, "bucket": BUCKET_NAME, "path": "twitch/comments"}
    )

    t2 = BigQueryCreateEmptyDatasetOperator(
        task_id="bigquery_create_operator",
        gcp_conn_id=GCP_CONN_ID,
        project_id=PROJECT_ID,
        dataset_id="twitch",
        location="EU",
    )

    with open(f"{os.path.dirname(__file__)}/comments.schema.json", "r") as f:
        schema = json.load(f)

    t3 = GCSToBigQueryOperator(
        task_id="gcs_to_bigquery",
        bucket=BUCKET_NAME,
        source_objects=[f"twitch/comments/{streamer_name}/{{{{ ds }}}}.json" for streamer_name in STREAMERS],
        destination_project_dataset_table="twitch.comments",
        bigquery_conn_id=GCP_CONN_ID,
        google_cloud_storage_conn_id=GCP_CONN_ID,
        source_format='NEWLINE_DELIMITED_JSON',
        schema_fields=schema,
        write_disposition="write_append",
        ignore_unknown_values=True,
        location="EU",

    )

    t1 >> t2 >> t3

if __name__ == "__main__":
    get_chat_history("2021-06-04")
