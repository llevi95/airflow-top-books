# airflow-top-books
A containerized Apache Airflow pipeline (CeleryExecutor with Redis/Postgres) that scrapes Goodreads “Best Books Ever” pages and loads parsed book metrics (title, author, avg_rating, num_ratings, score, people_voted) into PostgreSQL with retries and polite rate limiting.
