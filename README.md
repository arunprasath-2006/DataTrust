# DataTrust -- Intelligent Data Quality & Analytics Platform

DataTrust is a web-based platform for analyzing, validating, cleaning,
and visualizing datasets. It helps users identify common data-quality
issues, review cleaning results, and understand datasets through
analytical summaries and visualizations.

## Live Demo

**Website:** https://datatrust-2025.onrender.com/

## Features

-   **Dataset Upload:** Upload supported CSV and Excel datasets.
-   **Data Overview:** View dataset dimensions and summary information.
-   **Data Quality Analysis:** Identify missing values, duplicate
    records, and other data-quality indicators.
-   **Smart Validation:** Run validation checks on uploaded data.
-   **Automatic Data Cleaning:** Apply available cleaning operations,
    including handling missing values, removing duplicate rows, and
    trimming extra spaces.
-   **Cleaning Preview:** Review the cleaning output before downloading.
-   **Cleaned Dataset Download:** Download the processed dataset.
-   **Visual Analytics:** Explore data through charts and dashboard
    summaries.
-   **Data Intelligence:** Review anomaly-related insights and data
    recommendations.
-   **Analysis History:** Review previous analyses, where supported by
    the deployed application.

> Note: The features available to users may depend on the deployed
> version and the dataset being analyzed.

## Technology Stack

-   **Python** -- application logic
-   **Flask** -- web framework
-   **Pandas** -- data loading and processing
-   **NumPy** -- numerical operations
-   **Scikit-learn / SciPy** -- analytical and machine-learning support
-   **HTML, CSS, JavaScript** -- user interface and interactivity
-   **Render** -- deployment

## How It Works

1.  Open the DataTrust website.
2.  Upload a supported dataset.
3.  Run the data analysis.
4.  Review the data overview and quality indicators.
5.  Review validation results and available recommendations.
6.  Choose the available cleaning operations.
7.  Generate and inspect the cleaning preview.
8.  Download the cleaned dataset.
9.  Explore the available visual analytics.

## Run Locally

### Prerequisites

-   Python installed
-   Git (optional, for cloning the repository)

### 1. Clone the repository

Replace `YOUR_GITHUB_REPOSITORY_URL` with the URL of your GitHub
repository.

``` bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd DataTrust
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**

``` powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**

``` bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

If the repository contains a `requirements.txt` file:

``` bash
pip install -r requirements.txt
```

Otherwise, install the packages used by the application:

``` bash
pip install Flask pandas numpy scikit-learn scipy openpyxl joblib
```

### 4. Start the application

``` bash
python app.py
```

Open this address in your browser:

``` text
http://127.0.0.1:5000/
```

## Project Structure

The exact files may vary by repository version. A typical Flask project
structure is:

``` text
DataTrust/
├── app.py
├── templates/
│   └── index.html
├── requirements.txt
└── README.md
```

## Screenshots

Add screenshots of the live application in this section. Upload the
images to your repository (for example, into a `screenshots/` folder),
then update the paths below.

``` markdown
![DataTrust Dashboard](screenshots/dashboard.png)
![DataTrust Data Quality Analysis](screenshots/data-quality.png)
![DataTrust Data Cleaning Preview](screenshots/data-cleaning.png)
```

## Project Objectives

-   Make common data-quality issues easier to identify.
-   Reduce repetitive manual data-cleaning work.
-   Provide a preview of cleaning results before download.
-   Present dataset information through clear visual summaries.
-   Support more informed decisions about dataset quality.

## Future Enhancements

Potential future improvements include:

-   Additional file-format support.
-   More configurable validation rules.
-   Expanded anomaly-detection methods.
-   More visualization and reporting options.
-   Exportable analysis reports.

## Deployment

DataTrust is deployed on Render:

**Live URL:** https://datatrust-2025.onrender.com/

## Project Information

-   **Project:** DataTrust -- Intelligent Data Quality & Analytics
    Platform
-   **Program:** B.Sc. Computer Science with Data Science
-   **Project Type:** Final-Year Major Project
-   **Author:** Arun prasath M

## License

This Project is licensed under the MIT License

------------------------------------------------------------------------

**DataTrust -- Making Data Cleaner, Smarter, and More Reliable.**
