from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.hooks.base import BaseHook
import psycopg2
import pandas as pd
from datetime import datetime
import os

def load_csv_to_postgres(**kwargs):
    pg_conn = BaseHook.get_connection('postgre_conn')

    conn_pg = psycopg2.connect(
        host=pg_conn.host,
        database=pg_conn.schema,
        user=pg_conn.login,
        password=pg_conn.password,
        port=pg_conn.port
    )
    
    cursor_pg = conn_pg.cursor()
    
    csv_data = pd.read_csv("/opt/airflow/dags/datasets/Financial_Sample.csv")
    
    table_name = "dealer.financial"
    
    cursor_pg.execute(f"""
    SELECT EXISTS (
        SELECT 1 
        FROM information_schema.tables 
        WHERE table_name='{table_name.split('.')[-1]}' AND table_schema='{table_name.split('.')[0]}'
    );
    """)
    
    table_exists = cursor_pg.fetchone()[0]

    if not table_exists:
        create_table_query = f"""
        CREATE TABLE {table_name} (
            Segment VARCHAR(50),
            Country VARCHAR(30),
            Product VARCHAR(30),
            "Discount Band" VARCHAR(220),
            "Units Sold" DECIMAL(10, 2),
            "Manufacturing Price" INT,
            "Sale Price" INT,
            "Gross Sales" DECIMAL(10, 2),
            Discounts DECIMAL(10, 2),
            Sales DECIMAL(10, 2),
            COGS DECIMAL(10, 2),
            Profit DECIMAL(10, 2),
            "Date" TIMESTAMP,
            "Month Number" INT,
            "Month Name" VARCHAR(15),
            Year INT
        );
        """
        cursor_pg.execute(create_table_query)

    insert_query = f"""
    INSERT INTO {table_name} (
        Segment, Country, Product, "Discount Band", "Units Sold", 
        "Manufacturing Price", "Sale Price", "Gross Sales", 
        Discounts, Sales, COGS, Profit, "Date", 
        "Month Number", "Month Name", Year
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
    """
    
    for _, row in csv_data.iterrows():
        cursor_pg.execute(insert_query, tuple(row))
    
    conn_pg.commit()
    cursor_pg.close()
    conn_pg.close()

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
}

with DAG(
    'load_csv_to_postgres',
    default_args=default_args,
    description='Load CSV data to PostgreSQL',
    schedule_interval='0 21 * * *',
    catchup=False,
) as dag:

    load_csv_task = PythonOperator(
        task_id='load_csv_task',
        python_callable=load_csv_to_postgres,
        provide_context=True,
    )

    load_csv_task
