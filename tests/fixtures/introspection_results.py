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
            {"name": "test_id", "inferred_type": "integer", "sample_values": ["1", "2", "3"]},
            {
                "name": "patient_email",
                "inferred_type": "email",
                "sample_values": ["a@b.com", "c@d.org"],
            },
            {
                "name": "test_name",
                "inferred_type": "string",
                "sample_values": ["CBC", "BMP", "Lipid Panel"],
            },
            {
                "name": "result",
                "inferred_type": "decimal",
                "sample_values": ["98.6", "120.5", "85.0"],
            },
            {
                "name": "is_critical",
                "inferred_type": "boolean",
                "sample_values": ["true", "false", "true"],
            },
            {
                "name": "collected_date",
                "inferred_type": "date",
                "sample_values": ["2026-01-15", "2026-01-16"],
            },
        ],
        "row_count": 50,
    }
