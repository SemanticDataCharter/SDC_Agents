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


def make_csv_introspection() -> dict:
    """Sample CSV introspection result."""
    return {
        "datasource": "lab_results_csv",
        "type": "csv",
        "columns": [
            {
                "name": "test_id",
                "data_type": "integer",
                "sample_values": ["1", "2", "3"],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "patient_email",
                "data_type": "email",
                "sample_values": ["a@b.com", "c@d.org"],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "test_name",
                "data_type": "string",
                "sample_values": ["CBC", "BMP", "Lipid Panel"],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "result",
                "data_type": "decimal",
                "sample_values": ["98.6", "120.5", "85.0"],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "is_critical",
                "data_type": "boolean",
                "sample_values": ["true", "false", "true"],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "collected_date",
                "data_type": "date",
                "sample_values": ["2026-01-15", "2026-01-16"],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
        ],
        "row_count": 50,
    }


def make_json_introspection() -> dict:
    """Sample JSON introspection result."""
    return {
        "datasource": "records_json",
        "type": "json",
        "columns": [
            {
                "name": "test_id",
                "data_type": "integer",
                "sample_values": [1, 2, 3],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "patient_email",
                "data_type": "email",
                "sample_values": ["alice@example.com", "bob@example.com"],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "test_name",
                "data_type": "string",
                "sample_values": ["CBC", "BMP", "Lipid Panel"],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "result",
                "data_type": "decimal",
                "sample_values": [98.6, 120.5, 85.0],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "is_critical",
                "data_type": "boolean",
                "sample_values": [True, False, True],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "collected_date",
                "data_type": "date",
                "sample_values": ["2026-01-15", "2026-01-16"],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
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
                "name": "_id",
                "bson_type": "objectId",
                "data_type": "objectId",
                "nullable": False,
                "sample_values": ["507f1f77bcf86cd799439011"],
                "description": "",
                "enumeration": None,
                "units": "",
                "constraints": {},
            },
            {
                "name": "test_name",
                "bson_type": "string",
                "data_type": "string",
                "nullable": False,
                "sample_values": ["CBC", "BMP"],
                "description": "",
                "enumeration": None,
                "units": "",
                "constraints": {},
            },
            {
                "name": "result_value",
                "bson_type": "double",
                "data_type": "decimal",
                "nullable": True,
                "sample_values": [98.6, 120.5],
                "description": "",
                "enumeration": None,
                "units": "",
                "constraints": {},
            },
            {
                "name": "is_abnormal",
                "bson_type": "bool",
                "data_type": "boolean",
                "nullable": False,
                "sample_values": [True, False],
                "description": "",
                "enumeration": None,
                "units": "",
                "constraints": {},
            },
            {
                "name": "collected_at",
                "bson_type": "date",
                "data_type": "datetime",
                "nullable": False,
                "sample_values": ["2026-01-15T08:30:00Z"],
                "description": "",
                "enumeration": None,
                "units": "",
                "constraints": {},
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
            {
                "name": "test_id",
                "data_type": "integer",
                "sample_values": ["1", "2", "3"],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "patient_name",
                "data_type": "string",
                "sample_values": ["Alice", "Bob", "Carol"],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "result_value",
                "data_type": "decimal",
                "sample_values": ["98.6", "120.5", "85.0"],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "is_critical",
                "data_type": "boolean",
                "sample_values": ["True", "False", "True"],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "collected_date",
                "data_type": "date",
                "sample_values": ["2026-01-15", "2026-01-16", "2026-01-17"],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
            {
                "name": "collected_at",
                "data_type": "datetime",
                "sample_values": [
                    "2026-01-15 08:30:00+00:00",
                    "2026-01-16 09:15:00+00:00",
                ],
                "description": "",
                "enumeration": None,
                "units": "",
                "nullable": None,
                "constraints": {},
            },
        ],
        "row_count": 1500,
    }
