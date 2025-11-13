# Goodreads Best Books Scraper

A production-ready Apache Airflow DAG that scrapes the [Goodreads "Best Books Ever"](https://www.goodreads.com/list/show/1.Best_Books_Ever) list and stores the data in PostgreSQL.

## 🎯 Overview

This project implements an automated ETL (Extract, Transform, Load) pipeline using Apache Airflow to:

1. **Extract**: Scrape book data from Goodreads' "Best Books Ever" list
2. **Transform**: Parse and clean the scraped HTML data
3. **Load**: Store structured data in PostgreSQL database

The pipeline collects the following information for each book:
- Title
- Author
- Average rating
- Number of ratings
- Score
- Number of people who voted

## ✨ Features

- **Automated Scheduling**: Runs daily to keep data up-to-date
- **Polite Scraping**: Implements rate limiting and random delays to avoid overwhelming the server
- **Error Handling**: Robust error handling with retry mechanisms
- **Fallback Data**: Mock data fallback for development and testing
- **Scalable Architecture**: Built on Apache Airflow with CeleryExecutor
- **Docker-based Deployment**: Complete containerized setup with Docker Compose
- **Database Management**: Integrated PostgreSQL with pgAdmin interface
- **Monitoring**: Includes Flower for Celery task monitoring

## 🏗️ Architecture

The system uses a microservices architecture with the following components:

### Core Services

1. **Airflow API Server**: REST API interface (port 8080)
2. **Airflow Scheduler**: Task scheduling and orchestration
3. **Airflow DAG Processor**: Processes DAG definitions
4. **Airflow Worker**: Executes tasks using Celery
5. **Airflow Triggerer**: Handles deferred tasks
6. **PostgreSQL**: Primary database (port 5432)
7. **Redis**: Message broker for Celery (port 6379)
8. **pgAdmin**: Database management interface (port 5050)
9. **Flower** (optional): Celery monitoring (port 5555)

### Data Flow

```
Goodreads Website → Airflow Worker (Scraper) → PostgreSQL Database
                          ↓
                    Redis (Task Queue)
                          ↓
                  Airflow Scheduler
```

## 📦 Prerequisites

- Docker Desktop or Docker Engine (20.10+)
- Docker Compose (2.0+)
- At least 4GB RAM available for Docker
- At least 10GB free disk space

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/goodreads-scraper.git
cd goodreads-scraper
```

### 2. Set Up Directory Structure

```bash
# Airflow Configuration
AIRFLOW_UID=50000
AIRFLOW_IMAGE_NAME=apache/airflow:3.1.2
AIRFLOW_PROJ_DIR=.

# Airflow Admin Credentials
_AIRFLOW_WWW_USER_USERNAME=airflow
_AIRFLOW_WWW_USER_PASSWORD=airflow

# PostgreSQL Configuration
POSTGRES_USER=airflow
POSTGRES_PASSWORD=airflow
POSTGRES_DB=airflow

# pgAdmin Configuration
PGADMIN_DEFAULT_EMAIL=admin@pgadmin.com
PGADMIN_DEFAULT_PASSWORD=root
```

### 5. Start the Services

```bash
# Initialize Airflow database and create admin user
docker-compose up airflow-init

# Start all services
docker-compose up -d

# Optional: Start with Flower for monitoring
docker-compose --profile flower up -d
```

### 6. Verify Installation

Check that all services are running:

```bash
docker-compose ps
```

All services should show as "healthy" or "running".

## ⚙️ Configuration

### Airflow Connection Setup

1. Access Airflow UI at http://localhost:8080
2. Login with credentials (default: airflow/airflow)
3. Navigate to Admin → Connections
4. Create a new connection:
   - **Connection Id**: `books_connection`
   - **Connection Type**: Postgres
   - **Host**: `postgres`
   - **Schema**: `airflow`
   - **Login**: `airflow`
   - **Password**: `airflow`
   - **Port**: `5432`

### DAG Configuration

Edit the following constants in `dags/app.py` to customize behavior:

```python
POSTGRES_CONN_ID   = "books_connection"      # Airflow connection ID
NUM_BOOKS          = 1_000                    # Target number of books to scrape
MAX_PAGES          = 100                      # Maximum pages to fetch
REQUEST_DELAY_SECS = (0.8, 2.0)              # Delay range between requests (seconds)
```

### Scheduling

By default, the DAG runs daily. To modify the schedule, edit the `schedule` parameter in `app.py`:

```python
schedule=timedelta(days=1),  # Change to your preferred interval
```

## 📖 Usage

### Running the DAG Manually

1. Access Airflow UI at http://localhost:8080
2. Find the DAG named `fetch_and_store_goodreads`
3. Toggle the DAG to "ON" state
4. Click the "Play" button to trigger a manual run

### Monitoring Execution

- **Airflow UI**: http://localhost:8080 - View DAG runs, task logs, and execution history
- **Flower** (if enabled): http://localhost:5555 - Monitor Celery workers and tasks
- **pgAdmin**: http://localhost:5050 - Query and manage database

### Accessing the Database

#### Via pgAdmin

1. Access pgAdmin at http://localhost:5050
2. Login with credentials from `.env` file
3. Add server:
   - Name: `Airflow DB`
   - Host: `postgres`
   - Port: `5432`
   - Database: `airflow`
   - Username: `airflow`
   - Password: `airflow`

#### Via Command Line

```bash
docker exec -it <postgres-container-id> psql -U airflow -d airflow

# Query the data
SELECT * FROM goodreads_books LIMIT 10;
SELECT COUNT(*) FROM goodreads_books;
SELECT author, COUNT(*) as book_count 
FROM goodreads_books 
GROUP BY author 
ORDER BY book_count DESC 
LIMIT 10;
```

## 📊 Data Schema

### Table: `goodreads_books`

| Column        | Type              | Description                          |
|---------------|-------------------|--------------------------------------|
| id            | SERIAL PRIMARY KEY| Auto-incrementing unique identifier  |
| title         | TEXT NOT NULL     | Book title                           |
| author        | TEXT              | Book author                          |
| avg_rating    | DOUBLE PRECISION  | Average rating (e.g., 4.25)         |
| num_ratings   | BIGINT            | Total number of ratings              |
| score         | BIGINT            | Goodreads list score                 |
| people_voted  | BIGINT            | Number of people who voted           |

### Sample Query Results

```sql
 id |            title             |       author        | avg_rating | num_ratings |  score   | people_voted
----+------------------------------+---------------------+------------+-------------+----------+--------------
  1 | Harry Potter and the Sorcer..| J.K. Rowling       |       4.47 |     9117773 |  2947818 |        30210
  2 | The Hunger Games             | Suzanne Collins     |       4.32 |     7823456 |  2456789 |        25340
```

## 🔧 Troubleshooting

### Common Issues

#### Services Not Starting

```bash
# Check service logs
docker-compose logs airflow-scheduler
docker-compose logs postgres

# Restart services
docker-compose restart
```

#### Memory Issues

If you see memory warnings, increase Docker's memory allocation:
- Docker Desktop: Settings → Resources → Memory (increase to 4GB+)

#### Connection Refused Errors

Ensure all services are healthy:
```bash
docker-compose ps
```

Wait for health checks to pass before accessing services.

#### No Data Scraped

1. Check if Goodreads structure has changed
2. Review task logs in Airflow UI
3. The fallback mock data will be used if scraping fails

#### Database Connection Issues

Verify the connection settings:
```bash
docker exec -it <airflow-worker-container> airflow connections get books_connection
```

### Logs Location

- **Airflow Logs**: `./logs/` directory
- **Docker Logs**: `docker-compose logs [service-name]`

## 🛠️ Development

### Project Structure

```
airflow-top-books/
├── docker-compose.yaml                # Docker services configuration
├── dags/
│   └── app.py                         # Main DAG definition
├── docs/
│   └── class_diagram.png              # Class diagram
│   └── sequence_diagram.py            # Sequence diagram
└── README.md               
```

### Adding Custom Dependencies

Add Python packages to `docker-compose.yaml` under `_PIP_ADDITIONAL_REQUIREMENTS`:

```yaml
_PIP_ADDITIONAL_REQUIREMENTS: >
  apache-airflow-providers-common-sql
  apache-airflow-providers-postgres
  your-new-package
```

Then rebuild:
```bash
docker-compose down
docker-compose up -d
```

### Modifying the DAG

1. Edit `dags/app.py`
2. Save changes
3. Airflow will automatically detect changes (may take 30-60 seconds)
4. Refresh the Airflow UI to see updates
5. Open a Pull Request

## Acknowledgments

- [Apache Airflow](https://airflow.apache.org/) - Workflow orchestration platform
- [Goodreads](https://www.goodreads.com/) - Data source
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) - HTML parsing

## Support

For issues and questions:
- Open an issue on GitHub
- Check existing issues for solutions
- Review Airflow documentation: https://airflow.apache.org/docs/

---

**Note**: This scraper is for educational purposes. Please respect Goodreads' terms of service and robots.txt when using this tool.
