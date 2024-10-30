from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.hooks.base import BaseHook
import psycopg2
import mysql.connector
from datetime import datetime, timedelta
import pandas as pd

def extract_from_mysql(**kwargs):
    
    mysql_conn = BaseHook.get_connection('mysql_conn')

    conn_mysql = mysql.connector.connect(
        host=mysql_conn.host,
        user=mysql_conn.login,
        password=mysql_conn.password,
        database=mysql_conn.schema,
        port=mysql_conn.port
    )

    cursor_mysql = conn_mysql.cursor()

    execution_date = kwargs['execution_date']
    
    today_date = execution_date.date() 
    
    backfill_start_date = '2021-11-01'
    backfill_end_date = '2021-12-31'

    
    query = f"""
    SELECT * FROM store.sales
    WHERE purchase_date = '{today_date}' OR (purchase_date >= '{backfill_start_date}' AND purchase_date <= '{backfill_end_date}')
    """
    
    cursor_mysql.execute(query)
    
    data = cursor_mysql.fetchall()
    
    kwargs['ti'].xcom_push(key='extracted_data', value=data)
    
    cursor_mysql.close()
    conn_mysql.close()

def transform_data(**kwargs):
    ti = kwargs['ti']
    extracted_data = ti.xcom_pull(key='extracted_data', task_ids='extract_task')
    
    columns = ['sales_id', 'purchase_date', 'motorcycle_name', 'motorcycle_group', 'dealer_origin', 'price', 'qty', 'total']  # Update with actual column names
    df = pd.DataFrame(extracted_data, columns=columns)
    
    df['purchase_date'] = pd.to_datetime(df['purchase_date'])
    df["total_amount"] = df['price'] * df['qty']
    df = df.drop(columns='total')
    
    transformed_data = [tuple(row) for row in df.to_numpy()]

    ti.xcom_push(key='transformed_data', value=transformed_data)

def load_to_postgres(**kwargs):
    ti = kwargs['ti']
    transformed_data = ti.xcom_pull(key='transformed_data', task_ids='transform_task')

    pg_conn = BaseHook.get_connection('postgre_conn')

    conn_pg = psycopg2.connect(
        host=pg_conn.host,
        database=pg_conn.schema,
        user=pg_conn.login,
        password=pg_conn.password,
        port=pg_conn.port
    )

    cursor_pg = conn_pg.cursor()

    table_name = "dealer.motorcycle"  
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        sales_id INT,
        purchase_date TIMESTAMP,
        motorcycle_name VARCHAR(255),
        motorcycle_group VARCHAR(255),
        dealer_origin VARCHAR(255),
        price INT,
        qty INT,
        total INT
    )
    """

    cursor_pg.execute(create_table_query)

    insert_query = f"INSERT INTO {table_name} VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
    for row in transformed_data:
        cursor_pg.execute(insert_query, row)

    conn_pg.commit()
    cursor_pg.close()
    conn_pg.close()

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
}

with DAG(
    'mysql_to_postgres_etl',
    default_args=default_args,
    description='ETL from MySQL to PostgreSQL',
    schedule_interval='0 20 * * *', 
    catchup=False,
) as dag:

    extract_task = PythonOperator(
        task_id='extract_task',
        python_callable=extract_from_mysql,
        provide_context=True,
    )

    transform_task = PythonOperator(
        task_id='transform_task',
        python_callable=transform_data,
        provide_context=True,
    )

    load_task = PythonOperator(
        task_id='load_task',
        python_callable=load_to_postgres,
        provide_context=True,
    )

    extract_task >> transform_task >> load_task
