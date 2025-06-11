# Procedure for Generating a Large-Scale Astronomical Coordinate Dataset from SDSS

**Last Updated:** June 11, 2025

## 1. Objective

To generate a large-scale dataset containing the unique IDs and celestial coordinates (Right Ascension, Declination) for up to 100 million stars from the Sloan Digital Sky Survey (SDSS). The resulting dataset is intended for use in benchmarking data processing, sorting, and other computational algorithms.

## 2. Tools and Environment

* **Platform:** SciServer (`https://www.sciserver.org/`)
* **Application:** CasJobs (Catalog Archive Server Jobs System)
* **Database Context:** Sloan Digital Sky Survey (SDSS) Data Release 18 (DR18)
* **Credentials:** A registered SciServer user account.

## 3. Step-by-Step Procedure

1.  **Login to SciServer:** Access the SciServer portal and log in with your user credentials. You will be directed to the SciServer Dashboard.
2.  **Navigate to CasJobs:** From the dashboard, under the "SciServer Apps" section, click on the **CasJobs** application to launch the database query interface.
3.  **Set Database Context:** In the CasJobs "Query" tab, locate the **Context** dropdown menu. It is critical to select the correct data release for this query. Choose **`DR18`** from the list.
4.  **Enter SQL Query:** Copy the complete SQL query from the section below and paste it into the main query text area.
5.  **Submit the Job:** Click the **`Submit`** button to execute the query. This runs the job asynchronously in the background.
    * *Note:* Do not use the `Quick` button, as it is limited to short execution times and small result sets.
6.  **Monitor Job Status:** Navigate to the **`History`** tab. You can monitor the status of your submitted job here. The status will transition from `Ready` to `Executing` and finally to `Finished`. This process may take a significant amount of time (e.g., 15-30 minutes or more) due to the large data volume.
7.  **Download the Dataset:**
    * Once the job status is `Finished`, navigate to the **`MyDB`** tab.
    * You will find a new table named **`MySortTable`** (as specified in the SQL query).
    * Click on the table name `MySortTable`.
    * On the table details page, locate the download/export section (usually labeled **Download** or **Extract**).
    * Select **`CSV (GZIP)`** for efficient download, and click the **`Go`** button.
    * On the **Output** page, wait for the job to move from "Pending" to "Available", then click the link to download the file.

## 4. SQL Query

The following query selects the top 100 million objects classified as stars from the `PhotoObj` catalog and saves the result to a table named `MySortTable` in your personal MyDB space.

```sql
-- ===================================================================
-- Benchmark Query: Get 100 Million Star Coordinates
-- ===================================================================

SELECT TOP 100000000
    objID,    -- Unique ID (a 64-bit integer)
    ra,       -- Right Ascension (a float coordinate)
    dec       -- Declination (a float coordinate)
INTO mydb.MySortTable
FROM 
    PhotoObj  -- Query from the main Photo-Object table
WHERE 
    type = 6  -- The filter condition: type = 6 means it's a STAR
```

## 5. Expected Outcome

* A comma-separated values (`.csv`) file downloaded to your local computer (likely compressed as `.csv.gz`).
* The file will contain three columns: `objID`, `ra`, `dec`.
* The file will contain up to 100,000,000 rows. If the total number of objects matching the criteria in the database is less than 100 million, the file will contain all available matching rows.

## 6. Important Notes for Reproducibility

* **Character Encoding:** The CasJobs query parser may not correctly handle non-ASCII characters in SQL comments. To ensure successful execution, all comments in the SQL query should be in English.
* **Query Time:** Be aware that this is a resource-intensive query. Execution time will vary depending on server load.
* **Storage Limitation:** The user's `MyDB` storage quota was reached during execution. The final table `MySortTable` contains approximately **15,585,000** rows, which was the maximum number of rows that could be stored before the job was terminated. This is still a very large dataset suitable for benchmarking.
