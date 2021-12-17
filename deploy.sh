docker build -t blef-airflow .
docker tag blef-airflow:latest cblefari/blef-airflow:$1
docker push cblefari/blef-airflow:$1

helm upgrade --install airflow apache-airflow/airflow -n airflow -f values.yaml --set custom_tag=$1