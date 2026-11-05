
from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import numpy as np
import io
import uuid
import os
import sqlite3
import json
import re
from datetime import datetime
from sklearn.ensemble import IsolationForest
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

CLEANED_STORE = {}
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

DATABASE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "datatrust_history.db"
)


# --------------------------------------------------
# DATABASE SETUP
# --------------------------------------------------

def get_db_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_history_db():
    connection = get_db_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS analysis_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            analyzed_at TEXT NOT NULL,
            total_rows INTEGER,
            total_columns INTEGER,
            total_sheets INTEGER,
            missing_values INTEGER,
            duplicate_rows INTEGER,
            total_issues INTEGER,
            high_issues INTEGER,
            medium_issues INTEGER,
            low_issues INTEGER,
            details TEXT
        )
    """)

    connection.commit()
    connection.close()


def save_analysis_history(data):
    details = {
        "validation_summary": data["validation_summary"],
        "smart_recommendations": data["smart_recommendations"],
        "validation_checks": data["validation_checks"],
        "anomaly_results": data["anomaly_results"],
        "quality_score": data["quality_score"]
    }

    connection = get_db_connection()

    connection.execute("""
        INSERT INTO analysis_history (
            filename, analyzed_at, total_rows, total_columns,
            total_sheets, missing_values, duplicate_rows,
            total_issues, high_issues, medium_issues,
            low_issues, details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["filename"],
        datetime.now().astimezone().isoformat(timespec="seconds"),
        data["total_rows"],
        data["total_columns"],
        data["total_sheets"],
        data["missing_values"],
        data["duplicate_rows"],
        data["validation_summary"]["total_issues"],
        data["validation_summary"]["high"],
        data["validation_summary"]["medium"],
        data["validation_summary"]["low"],
        json.dumps(details, ensure_ascii=False)
    ))

    connection.commit()
    connection.close()


init_history_db()


# --------------------------------------------------
# DATASET READING
# --------------------------------------------------

def read_dataset(file):
    original_name = secure_filename(file.filename or "")
    extension = os.path.splitext(original_name)[1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Please upload a CSV or Excel file.")

    content = file.read()

    if not content:
        raise ValueError("The uploaded file is empty.")

    if extension == ".csv":
        try:
            df = pd.read_csv(io.BytesIO(content))
        except UnicodeDecodeError:
            df = pd.read_csv(
                io.BytesIO(content),
                encoding="latin1"
            )

        return {"Dataset": df}

    if extension == ".xlsx":
        return pd.read_excel(
            io.BytesIO(content),
            sheet_name=None,
            engine="openpyxl"
        )

    if extension == ".xls":
        return pd.read_excel(
            io.BytesIO(content),
            sheet_name=None
        )

    raise ValueError("Unsupported file format.")


def safe_value(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        return float(value)

    if isinstance(value, np.bool_):
        return bool(value)

    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def make_preview(df, limit=10):
    preview = df.head(limit).copy()
    preview = preview.astype(object).where(
        pd.notna(preview), None
    )

    return [
        {
            str(key): safe_value(value)
            for key, value in row.items()
        }
        for row in preview.to_dict(orient="records")
    ]


# --------------------------------------------------
# ADVANCED DATA CONSISTENCY DETECTION
# --------------------------------------------------

def detect_data_consistency(df, sheet_name):
    issues = []

    for column in df.columns:
        series = df[column].dropna()

        if series.empty:
            continue

        column_name = str(column)
        column_lower = column_name.lower()
        text_values = series.astype(str)

        if (
            series.dtype == "object"
            and "date" not in column_lower
            and "time" not in column_lower
            and "email" not in column_lower
        ):
            groups = {}

            for value in text_values:
                cleaned = value.strip()
                normalized = cleaned.casefold()
                groups.setdefault(normalized, set()).add(cleaned)

            affected_values = sum(
                len(variants)
                for variants in groups.values()
                if len(variants) > 1
            )

            if affected_values:
                issues.append({
                    "sheet_name": sheet_name,
                    "column_name": column_name,
                    "severity": "Medium",
                    "issue": "Inconsistent category formatting",
                    "affected_count": affected_values,
                    "suggestion": (
                        "Standardize category capitalization "
                        "after reviewing original values."
                    )
                })

        if any(word in column_lower for word in [
            "date", "time", "dob", "birth"
        ]):
            values = text_values.str.strip()

            parsed = pd.to_datetime(
                values,
                format="mixed",
                errors="coerce"
            )

            valid_values = values[parsed.notna()]
            patterns = set()

            for value in valid_values:
                if re.match(r"^\d{4}-\d{1,2}-\d{1,2}", value):
                    patterns.add("YYYY-MM-DD")
                elif re.match(r"^\d{1,2}/\d{1,2}/\d{4}", value):
                    patterns.add("Slash date format")
                elif re.match(r"^\d{1,2}-\d{1,2}-\d{4}", value):
                    patterns.add("Dash date format")
                elif re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}", value):
                    patterns.add("Dot date format")
                else:
                    patterns.add("Other date format")

            if len(patterns) > 1:
                issues.append({
                    "sheet_name": sheet_name,
                    "column_name": column_name,
                    "severity": "Medium",
                    "issue": "Inconsistent date formats",
                    "affected_count": len(valid_values),
                    "suggestion": (
                        "Standardize dates into one format "
                        "after checking ambiguous dates."
                    )
                })

            invalid_dates = int(parsed.isna().sum())

            if invalid_dates:
                issues.append({
                    "sheet_name": sheet_name,
                    "column_name": column_name,
                    "severity": "Medium",
                    "issue": "Invalid date values",
                    "affected_count": invalid_dates,
                    "suggestion": "Review invalid date entries."
                })

        if "email" in column_lower:
            email_pattern = (
                r"^[A-Za-z0-9._%+-]+@"
                r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
            )

            invalid_count = int(
                (~text_values.str.strip().str.match(
                    email_pattern
                )).sum()
            )

            if invalid_count:
                issues.append({
                    "sheet_name": sheet_name,
                    "column_name": column_name,
                    "severity": "Medium",
                    "issue": "Invalid email format",
                    "affected_count": invalid_count,
                    "suggestion": "Review invalid email addresses."
                })

        if any(word in column_lower for word in [
            "phone", "mobile", "contact", "telephone"
        ]):
            invalid_count = sum(
                not 7 <= len(re.sub(r"\D", "", value)) <= 15
                for value in text_values
            )

            if invalid_count:
                issues.append({
                    "sheet_name": sheet_name,
                    "column_name": column_name,
                    "severity": "Medium",
                    "issue": "Inconsistent phone number format",
                    "affected_count": int(invalid_count),
                    "suggestion": (
                        "Review phone numbers and verify country codes."
                    )
                })

    return issues


# --------------------------------------------------
# DATA VALIDATION
# --------------------------------------------------

def validate_dataset(df, sheet_name):
    issues = []

    for column in df.columns:
        series = df[column]
        missing = int(series.isna().sum())

        if series.isna().all() and len(df) > 0:
            issues.append({
                "sheet_name": sheet_name,
                "column_name": str(column),
                "severity": "High",
                "issue": "Entire column is empty",
                "affected_count": missing,
                "suggestion": (
                    "Check whether this column is required."
                )
            })

        elif missing:
            issues.append({
                "sheet_name": sheet_name,
                "column_name": str(column),
                "severity": "Medium",
                "issue": "Missing values detected",
                "affected_count": missing,
                "suggestion": (
                    "Review missing entries before filling them."
                )
            })

        if series.dtype == "object":
            text_series = series.dropna().astype(str)

            spaces = int(
                text_series.map(
                    lambda x: x != x.strip()
                ).sum()
            )

            if spaces:
                issues.append({
                    "sheet_name": sheet_name,
                    "column_name": str(column),
                    "severity": "Low",
                    "issue": "Leading or trailing spaces",
                    "affected_count": spaces,
                    "suggestion": "Trim unnecessary spaces."
                })

            numeric_values = pd.to_numeric(
                text_series,
                errors="coerce"
            )

            mixed_count = int(numeric_values.notna().sum())

            if 0 < mixed_count < len(text_series):
                issues.append({
                    "sheet_name": sheet_name,
                    "column_name": str(column),
                    "severity": "Medium",
                    "issue": "Mixed numeric and text values",
                    "affected_count": len(text_series) - mixed_count,
                    "suggestion": (
                        "Review the column and standardize its format."
                    )
                })

    duplicates = int(df.duplicated().sum())

    if duplicates:
        issues.append({
            "sheet_name": sheet_name,
            "column_name": "Entire row",
            "severity": "Medium",
            "issue": "Duplicate records detected",
            "affected_count": duplicates,
            "suggestion": (
                "Review repeated records before removing them."
            )
        })

    numeric_columns = df.select_dtypes(
        include=np.number
    ).columns

    for column in numeric_columns:
        values = df[column].dropna()

        if len(values) < 4 or values.nunique() < 2:
            continue

        q1 = values.quantile(0.25)
        q3 = values.quantile(0.75)
        iqr = q3 - q1

        if iqr == 0:
            continue

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        count = int(
            ((values < lower) | (values > upper)).sum()
        )

        if count:
            issues.append({
                "sheet_name": sheet_name,
                "column_name": str(column),
                "severity": "Low",
                "issue": "Potential statistical outliers detected",
                "affected_count": count,
                "suggestion": (
                    "Inspect unusual values. Do not remove automatically."
                )
            })

    issues.extend(
        detect_data_consistency(df, sheet_name)
    )

    return issues


# --------------------------------------------------
# ANOMALY DETECTION
# --------------------------------------------------

def detect_anomalies(df, sheet_name):
    try:
        numeric_df = df.select_dtypes(
            include=np.number
        ).copy()

        usable_columns = [
            column for column in numeric_df.columns
            if not any(word in str(column).lower()
                       for word in [
                           "postal", "postcode", "zip",
                           "pincode", "identifier", "code"
                       ])
            and str(column).lower() != "id"
        ]

        numeric_df = numeric_df[usable_columns]
        numeric_df = numeric_df.replace(
            [np.inf, -np.inf], np.nan
        )
        numeric_df = numeric_df.dropna(axis=1, how="all")

        if len(df) < 20 or numeric_df.empty:
            return {
                "sheet_name": str(sheet_name),
                "status": "Not enough numeric data",
                "records_checked": len(df),
                "anomalies_found": 0,
                "anomaly_percentage": 0,
                "anomaly_records": []
            }

        numeric_df = numeric_df.fillna(
            numeric_df.median()
        )

        numeric_df = numeric_df.loc[
            :, numeric_df.nunique() > 1
        ]

        if numeric_df.empty:
            return {
                "sheet_name": str(sheet_name),
                "status": "No variable numeric columns",
                "records_checked": len(df),
                "anomalies_found": 0,
                "anomaly_percentage": 0,
                "anomaly_records": []
            }

        model = IsolationForest(
            n_estimators=150,
            contamination="auto",
            random_state=42
        )

        predictions = model.fit_predict(numeric_df)
        scores = model.decision_function(numeric_df)

        anomaly_positions = np.where(predictions == -1)[0]
        anomaly_records = []

        for position in anomaly_positions[:50]:
            anomaly_records.append({
                "row_number": int(position + 1),
                "anomaly_score": round(
                    float(scores[position]), 5
                ),
                "values": {
                    str(column): safe_value(
                        numeric_df.iloc[position][column]
                    )
                    for column in numeric_df.columns
                }
            })

        count = len(anomaly_positions)

        return {
            "sheet_name": str(sheet_name),
            "status": "Completed",
            "records_checked": int(len(numeric_df)),
            "anomalies_found": int(count),
            "anomaly_percentage": round(
                count / len(numeric_df) * 100, 2
            ),
            "anomaly_records": anomaly_records
        }

    except Exception:
        app.logger.exception(
            "Anomaly detection failed for %s", sheet_name
        )

        return {
            "sheet_name": str(sheet_name),
            "status": "Detection unavailable",
            "records_checked": int(len(df)),
            "anomalies_found": 0,
            "anomaly_percentage": 0,
            "anomaly_records": []
        }


# --------------------------------------------------
# DATA QUALITY SCORE
# --------------------------------------------------

def calculate_quality_score(df, issues, anomaly_result):
    if df.empty or len(df.columns) == 0:
        return {
            "score": 0,
            "completeness": 0,
            "uniqueness": 0,
            "validity": 0,
            "anomaly_rate": 0
        }

    total_cells = df.shape[0] * df.shape[1]
    missing_cells = int(df.isna().sum().sum())

    completeness = (
        100 * (1 - missing_cells / total_cells)
        if total_cells else 0
    )

    duplicate_count = int(df.duplicated().sum())

    uniqueness = (
        100 * (1 - duplicate_count / len(df))
        if len(df) else 0
    )

    relevant_issues = len(issues)

    validity = max(
        0,
        100 - (relevant_issues / max(len(df), 1) * 100)
    )

    anomaly_rate = anomaly_result.get(
        "anomaly_percentage", 0
    )

    score = (
        completeness * 0.35
        + uniqueness * 0.20
        + validity * 0.35
        + max(0, 100 - anomaly_rate) * 0.10
    )

    return {
        "score": round(max(0, min(100, score)), 2),
        "completeness": round(completeness, 2),
        "uniqueness": round(uniqueness, 2),
        "validity": round(validity, 2),
        "anomaly_rate": round(anomaly_rate, 2)
    }


# --------------------------------------------------
# SMART RECOMMENDATIONS - UPDATED
# --------------------------------------------------

def build_smart_recommendations(issues, anomaly_results):
    recommendations = []

    for item in issues:
        issue_title = item.get(
            "issue", "Data quality issue"
        )

        severity = item.get("severity", "Low")

        suggestion = item.get(
            "suggestion", "Review this data."
        )

        recommendations.append({
            "sheet_name": item.get("sheet_name", "Dataset"),
            "issue": issue_title,
            "title": issue_title,
            "column_name": item.get("column_name", "N/A"),
            "severity": severity,
            "priority": severity,
            "affected_count": item.get("affected_count", 0),
            "suggestion": suggestion,
            "recommendation": suggestion
        })

    for result in anomaly_results:
        count = result.get("anomalies_found", 0)

        if count > 0:
            message = (
                f"{count} unusual record(s) were detected. "
                "Review them before deciding whether they are errors."
            )

            recommendations.append({
                "sheet_name": result.get("sheet_name", "Dataset"),
                "issue": "Unusual numeric records detected",
                "title": "Unusual numeric records detected",
                "column_name": "Numeric columns",
                "severity": "Medium",
                "priority": "Medium",
                "affected_count": count,
                "suggestion": message,
                "recommendation": message
            })

    if not recommendations:
        message = (
            "No major issues detected. Continue monitoring "
            "data quality as new records are added."
        )

        recommendations.append({
            "sheet_name": "Dataset",
            "issue": "No major issues detected",
            "title": "No major issues detected",
            "column_name": "N/A",
            "severity": "Low",
            "priority": "Low",
            "affected_count": 0,
            "suggestion": message,
            "recommendation": message
        })

    return recommendations


# --------------------------------------------------
# VISUAL ANALYTICS
# --------------------------------------------------

def build_analytics(df):
    numeric_data = {}
    category_data = {}

    for column in df.select_dtypes(
        include=np.number
    ).columns:
        values = df[column].dropna()

        if values.empty:
            continue

        histogram_counts, histogram_edges = np.histogram(
            values,
            bins=min(10, max(3, values.nunique()))
        )

        numeric_data[str(column)] = {
            "count": int(values.count()),
            "mean": round(float(values.mean()), 2),
            "median": round(float(values.median()), 2),
            "min": round(float(values.min()), 2),
            "max": round(float(values.max()), 2),
            "sum": round(float(values.sum()), 2),
            "histogram": {
                "labels": [
                    f"{histogram_edges[i]:.2f}–"
                    f"{histogram_edges[i + 1]:.2f}"
                    for i in range(len(histogram_counts))
                ],
                "values": histogram_counts.astype(int).tolist()
            }
        }

    numeric_columns = set(
        df.select_dtypes(include=np.number).columns
    )

    for column in df.columns:
        if column in numeric_columns:
            continue

        values = df[column].dropna().astype(str)

        if values.empty or values.nunique() > 100:
            continue

        counts = values.value_counts().head(8)

        category_data[str(column)] = {
            "labels": counts.index.tolist(),
            "values": counts.astype(int).tolist()
        }

    return {
        "numeric": numeric_data,
        "categories": category_data
    }


# --------------------------------------------------
# RELATIONSHIP VALIDATION
# --------------------------------------------------

def validate_relationships(sheets):
    issues = []

    if "Returns" in sheets and "Orders" in sheets:
        returns = sheets["Returns"]
        orders = sheets["Orders"]

        if (
            "Order ID" in returns.columns
            and "Order ID" in orders.columns
        ):
            order_ids = set(
                orders["Order ID"].dropna().astype(str).str.strip()
            )

            return_ids = returns[
                "Order ID"
            ].dropna().astype(str).str.strip()

            unmatched = int(
                (~return_ids.isin(order_ids)).sum()
            )

            if unmatched:
                issues.append({
                    "sheet_name": "Returns",
                    "column_name": "Order ID",
                    "severity": "High",
                    "issue": "Unmatched order references",
                    "affected_count": unmatched,
                    "suggestion": (
                        "Check whether each returned order "
                        "exists in the Orders sheet."
                    )
                })

    if "People" in sheets and "Orders" in sheets:
        people = sheets["People"]
        orders = sheets["Orders"]

        if (
            "Region" in people.columns
            and "Region" in orders.columns
        ):
            known_regions = set(
                people["Region"].dropna().astype(str)
                .str.strip().str.casefold()
            )

            order_regions = orders[
                "Region"
            ].dropna().astype(str).str.strip().str.casefold()

            unmatched = int(
                (~order_regions.isin(known_regions)).sum()
            )

            if unmatched:
                issues.append({
                    "sheet_name": "Orders",
                    "column_name": "Region",
                    "severity": "Medium",
                    "issue": "Region values not found in People sheet",
                    "affected_count": unmatched,
                    "suggestion": (
                        "Review region names and check spelling "
                        "or mapping differences."
                    )
                })

    return issues


# --------------------------------------------------
# AUTOMATIC DATA CLEANING
# --------------------------------------------------

def clean_dataframe(df, options):
    cleaned = df.copy()
    actions = []

    if options.get("trim_spaces", True):
        for column in cleaned.select_dtypes(
            include="object"
        ).columns:
            before = cleaned[column].copy()

            cleaned[column] = cleaned[column].map(
                lambda x: x.strip() if isinstance(x, str) else x
            )

            count = int(
                (
                    before.fillna("").astype(str)
                    != cleaned[column].fillna("").astype(str)
                ).sum()
            )

            if count:
                actions.append({
                    "action": "Trimmed spaces",
                    "column": str(column),
                    "count": count
                })

    if options.get("fill_missing", True):
        for column in cleaned.columns:
            missing = int(cleaned[column].isna().sum())

            if not missing:
                continue

            if pd.api.types.is_numeric_dtype(cleaned[column]):
                fill_value = cleaned[column].median()

                if pd.isna(fill_value):
                    fill_value = 0
            else:
                mode = cleaned[column].mode(dropna=True)

                fill_value = (
                    mode.iloc[0]
                    if not mode.empty
                    else "Not provided"
                )

            cleaned[column] = cleaned[column].fillna(fill_value)

            actions.append({
                "action": "Filled missing values",
                "column": str(column),
                "count": missing
            })

    if options.get("remove_duplicates", True):
        before = len(cleaned)
        cleaned = cleaned.drop_duplicates()
        removed = before - len(cleaned)

        if removed:
            actions.append({
                "action": "Removed duplicate rows",
                "column": "Entire row",
                "count": removed
            })

    return cleaned, actions


# --------------------------------------------------
# HOME PAGE
# --------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


# --------------------------------------------------
# DATASET UPLOAD AND ANALYSIS
# --------------------------------------------------

@app.route("/upload", methods=["POST"])
def upload():
    try:
        uploaded_file = request.files.get("file")

        if not uploaded_file or not uploaded_file.filename:
            return jsonify({
                "success": False,
                "message": "Please select a dataset."
            }), 400

        sheets = read_dataset(uploaded_file)

        all_issues = []
        sheet_results = {}
        validation_checks = []
        anomaly_results = []
        quality_results = {}

        total_rows = 0
        total_columns = 0
        total_missing = 0
        total_duplicates = 0

        for sheet_name, df in sheets.items():
            df = df.copy()
            rows, columns = df.shape

            missing = int(df.isna().sum().sum())
            duplicates = int(df.duplicated().sum())

            total_rows += rows
            total_columns += columns
            total_missing += missing
            total_duplicates += duplicates

            issues = validate_dataset(df, str(sheet_name))
            all_issues.extend(issues)

            anomaly_result = detect_anomalies(
                df, str(sheet_name)
            )
            anomaly_results.append(anomaly_result)

            quality_results[str(sheet_name)] = (
                calculate_quality_score(
                    df, issues, anomaly_result
                )
            )

            sheet_results[str(sheet_name)] = {
                "rows": rows,
                "columns": columns,
                "column_names": [
                    str(c) for c in df.columns
                ],
                "preview": make_preview(df),
                "analytics": build_analytics(df),
                "quality_score": quality_results[
                    str(sheet_name)
                ]
            }

            validation_checks.append({
                "sheet_name": str(sheet_name),
                "rows": rows,
                "columns": columns,
                "missing_values": missing,
                "duplicate_rows": duplicates,
                "issues_found": len(issues)
            })

        all_issues.extend(validate_relationships(sheets))

        high = sum(
            i["severity"] == "High" for i in all_issues
        )
        medium = sum(
            i["severity"] == "Medium" for i in all_issues
        )
        low = sum(
            i["severity"] == "Low" for i in all_issues
        )

        total_cells = sum(
            df.shape[0] * df.shape[1]
            for df in sheets.values()
        )

        weighted_score = (
            sum(
                quality_results[name]["score"] * max(
                    sheets[name].shape[0] * sheets[name].shape[1], 1
                )
                for name in quality_results
            )
            / sum(
                max(
                    sheets[name].shape[0] * sheets[name].shape[1], 1
                )
                for name in quality_results
            )
        ) if quality_results else 0

        recommendations = build_smart_recommendations(
            all_issues, anomaly_results
        )

        result = {
            "success": True,
            "filename": secure_filename(uploaded_file.filename),
            "total_rows": total_rows,
            "total_columns": total_columns,
            "total_sheets": len(sheets),
            "missing_values": total_missing,
            "duplicate_rows": total_duplicates,
            "total_cells": total_cells,
            "quality_score": round(weighted_score, 2),
            "quality_details": quality_results,
            "sheets": sheet_results,
            "anomaly_results": anomaly_results,
            "validation_issues": all_issues,
            "validation_checks": validation_checks,
            "validation_summary": {
                "total_issues": len(all_issues),
                "high": high,
                "medium": medium,
                "low": low,
                "missing_values": total_missing,
                "duplicate_rows": total_duplicates
            },
            "smart_recommendations": recommendations
        }

        save_analysis_history(result)

        return jsonify(result)

    except Exception as error:
        app.logger.exception("Dataset analysis failed")

        return jsonify({
            "success": False,
            "message": str(error)
        }), 500


# --------------------------------------------------
# ANALYSIS HISTORY - VIEW ALL
# --------------------------------------------------

@app.route("/history", methods=["GET"])
def get_analysis_history():
    try:
        connection = get_db_connection()

        records = connection.execute("""
            SELECT
                id, filename, analyzed_at,
                total_rows, total_columns, total_sheets,
                missing_values, duplicate_rows,
                total_issues, high_issues,
                medium_issues, low_issues
            FROM analysis_history
            ORDER BY id DESC
        """).fetchall()

        connection.close()

        return jsonify({
            "success": True,
            "total_history": len(records),
            "history": [dict(record) for record in records]
        })

    except Exception:
        app.logger.exception("History retrieval failed")
        return jsonify({
            "success": False,
            "message": "Could not retrieve analysis history."
        }), 500


# --------------------------------------------------
# ANALYSIS HISTORY - VIEW ONE RECORD
# --------------------------------------------------

@app.route("/history/<int:history_id>", methods=["GET"])
def get_history_details(history_id):
    try:
        connection = get_db_connection()

        record = connection.execute("""
            SELECT *
            FROM analysis_history
            WHERE id = ?
        """, (history_id,)).fetchone()

        connection.close()

        if record is None:
            return jsonify({
                "success": False,
                "message": "Analysis history not found."
            }), 404

        result = dict(record)
        result["details"] = json.loads(
            result.pop("details") or "{}"
        )

        return jsonify({
            "success": True,
            "record": result
        })

    except Exception:
        app.logger.exception("History detail retrieval failed")
        return jsonify({
            "success": False,
            "message": "Could not retrieve history details."
        }), 500


# --------------------------------------------------
# ANALYSIS HISTORY - DELETE ONE RECORD
# --------------------------------------------------

@app.route("/history/<int:history_id>", methods=["DELETE"])
def delete_history(history_id):
    try:
        connection = get_db_connection()

        cursor = connection.execute("""
            DELETE FROM analysis_history
            WHERE id = ?
        """, (history_id,))

        connection.commit()
        deleted = cursor.rowcount
        connection.close()

        if deleted == 0:
            return jsonify({
                "success": False,
                "message": "Analysis history not found."
            }), 404

        return jsonify({
            "success": True,
            "message": "Analysis history deleted successfully."
        })

    except Exception:
        app.logger.exception("History deletion failed")
        return jsonify({
            "success": False,
            "message": "Could not delete history."
        }), 500


# --------------------------------------------------
# CLEANING PREVIEW
# --------------------------------------------------

@app.route("/clean-preview", methods=["POST"])
def clean_preview():
    try:
        uploaded_file = request.files.get("file")

        if not uploaded_file or not uploaded_file.filename:
            return jsonify({
                "success": False,
                "message": "Please select a dataset."
            }), 400

        options = {
            "trim_spaces": request.form.get(
                "trim_spaces", "true"
            ).lower() == "true",

            "fill_missing": request.form.get(
                "fill_missing", "true"
            ).lower() == "true",

            "remove_duplicates": request.form.get(
                "remove_duplicates", "true"
            ).lower() == "true"
        }

        sheets = read_dataset(uploaded_file)
        cleaned_sheets = {}
        preview_result = {}
        all_actions = []

        for sheet_name, df in sheets.items():
            cleaned, actions = clean_dataframe(df, options)
            cleaned_sheets[sheet_name] = cleaned

            for action in actions:
                action["sheet_name"] = str(sheet_name)
                all_actions.append(action)

            preview_result[str(sheet_name)] = {
                "before_rows": len(df),
                "after_rows": len(cleaned),
                "columns": [str(c) for c in cleaned.columns],
                "rows": make_preview(cleaned)
            }

        token = str(uuid.uuid4())

        CLEANED_STORE[token] = {
            "sheets": cleaned_sheets,
            "filename": secure_filename(uploaded_file.filename)
        }

        return jsonify({
            "success": True,
            "token": token,
            "preview": preview_result,
            "actions": all_actions,
            "message": "Cleaning preview generated successfully."
        })

    except Exception:
        app.logger.exception("Cleaning preview failed")
        return jsonify({
            "success": False,
            "message": "Could not generate cleaning preview."
        }), 500


# --------------------------------------------------
# DOWNLOAD CLEANED DATASET
# --------------------------------------------------

@app.route("/download-cleaned/<token>")
def download_cleaned(token):
    stored = CLEANED_STORE.get(token)

    if not stored:
        return jsonify({
            "success": False,
            "message": (
                "Cleaning session expired. "
                "Please generate the preview again."
            )
        }), 404

    sheets = stored["sheets"]
    original_name = stored["filename"]
    base_name = os.path.splitext(original_name)[0]

    output = io.BytesIO()

    if len(sheets) == 1:
        _, df = next(iter(sheets.items()))

        if original_name.lower().endswith(".csv"):
            df.to_csv(output, index=False)
            mimetype = "text/csv"
            download_name = base_name + "_cleaned.csv"
        else:
            df.to_excel(output, index=False, engine="openpyxl")
            mimetype = (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
            download_name = base_name + "_cleaned.xlsx"

    else:
        with pd.ExcelWriter(
            output, engine="openpyxl"
        ) as writer:
            for sheet_name, df in sheets.items():
                df.to_excel(
                    writer,
                    sheet_name=str(sheet_name)[:31],
                    index=False
                )

        mimetype = (
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
        download_name = base_name + "_cleaned.xlsx"

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=download_name,
        mimetype=mimetype
    )


# --------------------------------------------------
# FILE SIZE ERROR
# --------------------------------------------------

@app.errorhandler(413)
def file_too_large(error):
    return jsonify({
        "success": False,
        "message": "File is too large. Maximum size is 50 MB."
    }), 413


# --------------------------------------------------
# RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
