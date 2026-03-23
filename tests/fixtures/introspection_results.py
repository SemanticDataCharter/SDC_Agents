"""Sample introspection outputs for SQL and CSV datasources."""


def make_sql_introspection() -> dict:
    """Sample SQL introspection result."""
    return {
        "datasource": "lab_db",
        "type": "sql",
        "tables": [
            {
                "name": "lab_results",
                "columns": [
                    {"name": "id", "data_type": "integer", "nullable": False},
                    {"name": "patient_id", "data_type": "string", "nullable": False},
                    {"name": "test_name", "data_type": "string", "nullable": False},
                    {"name": "result_value", "data_type": "decimal", "nullable": True},
                    {"name": "units", "data_type": "string", "nullable": True},
                    {"name": "collected_at", "data_type": "datetime", "nullable": False},
                    {"name": "is_abnormal", "data_type": "boolean", "nullable": False},
                ],
                "row_count": 1500,
            },
            {
                "name": "patients",
                "columns": [
                    {"name": "id", "data_type": "integer", "nullable": False},
                    {"name": "patient_id", "data_type": "string", "nullable": False},
                    {"name": "first_name", "data_type": "string", "nullable": False},
                    {"name": "last_name", "data_type": "string", "nullable": False},
                    {"name": "dob", "data_type": "date", "nullable": False},
                    {"name": "email", "data_type": "string", "nullable": True},
                ],
                "row_count": 250,
            },
        ],
    }


def _col(name, data_type, sample_values=None, **overrides):
    """Build a 13-field column dict for fixture use."""
    col = {
        "name": name,
        "data_type": data_type,
        "sample_values": sample_values or [],
        "description": "",
        "enumeration": None,
        "units": "",
        "nullable": None,
        "constraints": {},
        "range_values": "",
        "relationships": "",
        "business_rules": "",
        "examples": "",
        "metadata": {},
    }
    col.update(overrides)
    return col


def make_csv_introspection() -> dict:
    """Sample CSV introspection result."""
    return {
        "datasource": "lab_results_csv",
        "type": "csv",
        "columns": [
            _col("test_id", "integer", ["1", "2", "3"]),
            _col("patient_email", "email", ["a@b.com", "c@d.org"]),
            _col("test_name", "string", ["CBC", "BMP", "Lipid Panel"]),
            _col("result", "decimal", ["98.6", "120.5", "85.0"]),
            _col("is_critical", "boolean", ["true", "false", "true"]),
            _col("collected_date", "date", ["2026-01-15", "2026-01-16"]),
        ],
        "row_count": 50,
    }


def make_json_introspection() -> dict:
    """Sample JSON introspection result."""
    return {
        "datasource": "records_json",
        "type": "json",
        "columns": [
            _col("test_id", "integer", [1, 2, 3]),
            _col("patient_email", "email", ["alice@example.com", "bob@example.com"]),
            _col("test_name", "string", ["CBC", "BMP", "Lipid Panel"]),
            _col("result", "decimal", [98.6, 120.5, 85.0]),
            _col("is_critical", "boolean", [True, False, True]),
            _col("collected_date", "date", ["2026-01-15", "2026-01-16"]),
        ],
        "row_count": 5,
    }


def make_mongodb_introspection() -> dict:
    """Sample MongoDB introspection result."""
    return {
        "datasource": "clinical_db",
        "collection": "lab_results",
        "fields": [
            {
                **_col(
                    "_id",
                    "objectId",
                    ["507f1f77bcf86cd799439011"],
                    nullable=False,
                    metadata={"bson_type": "objectId"},
                ),
                "bson_type": "objectId",
            },
            {
                **_col(
                    "test_name",
                    "string",
                    ["CBC", "BMP"],
                    nullable=False,
                    metadata={"bson_type": "string"},
                ),
                "bson_type": "string",
            },
            {
                **_col(
                    "result_value",
                    "decimal",
                    [98.6, 120.5],
                    nullable=True,
                    metadata={"bson_type": "double"},
                ),
                "bson_type": "double",
            },
            {
                **_col(
                    "is_abnormal",
                    "boolean",
                    [True, False],
                    nullable=False,
                    metadata={"bson_type": "bool"},
                ),
                "bson_type": "bool",
            },
            {
                **_col(
                    "collected_at",
                    "datetime",
                    ["2026-01-15T08:30:00Z"],
                    nullable=False,
                    metadata={"bson_type": "date"},
                ),
                "bson_type": "date",
            },
        ],
        "document_count": 100,
    }


def make_bigquery_introspection() -> dict:
    """Sample BigQuery introspection result."""
    return {
        "datasource": "analytics_bq",
        "type": "bigquery",
        "dataset": "clinical_data",
        "table": "lab_results",
        "columns": [
            _col(
                "test_id",
                "integer",
                ["1", "2", "3"],
                nullable=False,
                metadata={"bigquery_type": "INT64", "bigquery_mode": "REQUIRED"},
            ),
            _col(
                "patient_name",
                "string",
                ["Alice", "Bob", "Carol"],
                nullable=True,
                metadata={"bigquery_type": "STRING", "bigquery_mode": "NULLABLE"},
            ),
            _col(
                "result_value",
                "decimal",
                ["98.6", "120.5", "85.0"],
                nullable=True,
                metadata={"bigquery_type": "FLOAT64", "bigquery_mode": "NULLABLE"},
            ),
            _col(
                "is_critical",
                "boolean",
                ["True", "False", "True"],
                nullable=True,
                metadata={"bigquery_type": "BOOL", "bigquery_mode": "NULLABLE"},
            ),
            _col(
                "collected_date",
                "date",
                ["2026-01-15", "2026-01-16", "2026-01-17"],
                nullable=True,
                metadata={"bigquery_type": "DATE", "bigquery_mode": "NULLABLE"},
            ),
            _col(
                "collected_at",
                "datetime",
                ["2026-01-15 08:30:00+00:00", "2026-01-16 09:15:00+00:00"],
                nullable=True,
                metadata={"bigquery_type": "TIMESTAMP", "bigquery_mode": "NULLABLE"},
            ),
        ],
        "row_count": 1500,
    }
