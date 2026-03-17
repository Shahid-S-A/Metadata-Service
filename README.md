HEAD
# Metadata Service

A lightweight API for managing dataset metadata and lineage tracking, built with FastAPI and MySQL.

This service makes it easy to document where your data comes from, how it flows through your systems, and prevents broken lineage chains (circular dependencies).

## Getting Started

### Running the Service

```bash
# Start with Docker Compose (recommended)
docker compose up -d

# API will be available at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

Alternatively, if you prefer to set things up manually for local development:

```bash
# Install dependencies
poetry install

# Set up MySQL (or use Docker to run just the database)
docker run -d -e MYSQL_ROOT_PASSWORD=root_password \
  -e MYSQL_USER=metadata_user \
  -e MYSQL_PASSWORD=metadata_password \
  -e MYSQL_DATABASE=metadata_db \
  -p 3306:3306 mysql:8.0-alpine

# Run the application
poetry run uvicorn app.main:app --reload

```

## How It Works

Here are the key design decisions that make this service useful:

### Cycle Detection (DFS Algorithm)
We prevent circular dependencies in lineage—like A→B→C→A. When you create a lineage relationship, the system checks if a path already exists in the opposite direction. If you try to create a cycle, it rejects it with a clear error. Performance is fast: under 100ms even with 100+ relationships.

### FQN: A Universal Naming Scheme
Each dataset has a Fully Qualified Name (FQN) like `connection.database.schema.table`. This approach is human-readable, guarantees uniqueness across your entire data landscape, and makes searching work well.

### Smart Search with Relevance Ranking
When you search for "customer", the results are sorted by relevance: exact table name matches come first, then column matches, then schema, then database names. Each dataset appears only once with its best match.

### Three Simple Concepts
**Datasets** hold your metadata (FQN, source system, and columns). **Columns** define the structure (name and type). **Lineage** shows relationships—which datasets feed into which. We track lineage at the dataset level (not column-level), which keeps things simple without sacrificing practicality.

## What You Can Do

- **Store metadata**: Register datasets with their names, columns, and source systems
- **Track data flow**: Create lineage relationships to show how data moves through your systems  
- **Prevent mistakes**: The service blocks circular dependencies automatically
- **Find datasets**: Search by table name, column name, schema, or database

## Using the API

The API is self-documenting. Once your service is running, browse the interactive documentation:
- **Swagger UI**: http://localhost:8000/docs (prettier and easier to use)
- **ReDoc**: http://localhost:8000/redoc (alternative format)

The main endpoints you'll use:
- `POST /api/v1/datasets` → Create a dataset
- `GET /api/v1/datasets` → List all datasets
- `POST /api/v1/lineages` → Link datasets together
- `GET /api/v1/search?q=...` → Find datasets by keyword

## Try It Out

Want to see it in action? Open a new terminal and follow along. These curl examples will walk you through creating datasets, linking them, and searching.

**Before you start:**
- Make sure the service is running: `docker compose up -d`
- You need `curl` (it comes with most systems)

**How to try it:**
Copy each command below and paste it into your terminal one at a time. The service will respond with JSON. Try to understand what each step is doing.

### 1. Create a Dataset

Start by registering your first dataset. You need to tell the system:
- **fqn**: The full name of the dataset (format: `connection.database.schema.table`)
- **source_system**: Where it lives (PostgreSQL, Snowflake, MySQL, Redshift, etc.)
- **columns**: What columns it has and their data types

```bash
curl -X POST http://localhost:8000/api/v1/datasets \
  -H "Content-Type: application/json" \
  -d '{
    "fqn": "postgres_prod.sales.public.customers",
    "source_system": "PostgreSQL",
    "columns": [
      {"name": "customer_id", "type": "INT"},
      {"name": "email", "type": "VARCHAR"},
      {"name": "created_at", "type": "TIMESTAMP"}
    ]
  }'
```

**What happens:** The system saves this dataset to the database and sends back a `201 Created` response with the dataset details including its new ID.


### 2. Register a Second Dataset

Now create another dataset. This one will be derived from the first one—it will be downstream and depend on the customer data.

```bash
curl -X POST http://localhost:8000/api/v1/datasets \
  -H "Content-Type: application/json" \
  -d '{
    "fqn": "snowflake_prod.analytics.public.customer_metrics",
    "source_system": "Snowflake",
    "columns": [
      {"name": "metric_id", "type": "INT"},
      {"name": "total_orders", "type": "INT"}
    ]
  }'
```

**What happens:** The system creates the second dataset. You'll get another `201 Created` response.


### 3. Link Them Together (Create Lineage)

Now tell the system how these datasets relate. The first dataset is upstream (the source), and the second is downstream (it depends on the first). This creates a data flow: customers → customer_metrics.

You just need:
- **upstream_fqn**: Which dataset is the source
- **downstream_fqn**: Which dataset depends on the source

```bash
curl -X POST http://localhost:8000/api/v1/lineages \
  -H "Content-Type: application/json" \
  -d '{
    "upstream_fqn": "postgres_prod.sales.public.customers",
    "downstream_fqn": "snowflake_prod.analytics.public.customer_metrics"
  }'
```

**What happens:** The service checks if this would create a cycle. If it's valid, it saves the relationship and sends back `201 Created`.


### 4. See Everything You've Created

Let's view all the datasets you just registered.

```bash
curl http://localhost:8000/api/v1/datasets
```

**What happens:** The system returns a list of all datasets with everything—their IDs, FQNs, columns, source systems, and who depends on whom.


### 5. Find Datasets by Searching

Now search for what you just created. The search is intelligent—it ranks results by relevance:
1. Table name matches (most relevant)
2. Column name matches
3. Schema matches
4. Database matches (least relevant)

```bash
curl "http://localhost:8000/api/v1/search?q=customer"
```

**What happens:** The system searches all FQNs and columns for "customer" and returns matches sorted by relevance.


### 6. Look Up a Dataset by Name

If you know the exact FQN of a dataset, fetch it directly. This is faster than searching.

```bash
curl "http://localhost:8000/api/v1/datasets/by-fqn/postgres_prod.sales.public.customers"
```

**What happens:** The system finds the dataset and returns all its details.


## Checking on Your Service

### Is It Running?

```bash
# List running containers
docker compose ps

# Check if API is responding
curl http://localhost:8000/docs

# Or use the API health check
curl http://localhost:8000/api/v1/health
```

### Check the Logs

If something doesn't work, check the logs to see what happened:

```bash
# Watch API logs in real time
docker compose logs -f api

# Or watch database logs
docker compose logs -f mysql

# Or see everything
docker compose logs -f
```

### Verify the Database

Want to look inside the database directly? You can:

```bash
# Log into MySQL
docker exec -it metadata_db mysql -u metadata_user -p metadata_db

# Then check what's there
SHOW TABLES;
SELECT COUNT(*) FROM datasets;
```

## When You're Done

When you want to stop the service:

```bash
# Stop everything but keep your data
docker compose down

# Or stop and delete everything (start fresh next time)
docker compose down -v

# Or stop just one service
docker compose stop api
```

## Configuration

You can customize the service by creating a `.env` file in the project root:

```env
# Database
DATABASE_URL=mysql+pymysql://metadata_user:metadata_password@localhost:3306/metadata_db

# API  
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=False
LOG_LEVEL=INFO
```

## License

MIT
