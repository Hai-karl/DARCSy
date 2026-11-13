# Defect Rate Trend Analysis and Root Cause Identification System

A web system for manufacturing quality control. It stores defect records, shows how the defect rate changes over time, sends alerts, and suggests the likely root cause of defects.

This guide shows how to start the software and how to use it. The demo data is made up, so the numbers do not reflect a real factory.

---

## 0A. New in this version: accounts, the new website and going live

- **Request an account:** on the sign-in page click **Request an account**. An IT Administrator approves it under **Users** and can change the role before approving.
- **Passwords:** at least 10 characters with a letter and a number, not containing your username. Five wrong passwords lock an account for 15 minutes. Change your password under **Account**. That also signs you out on other devices.
- **New website (folder `frontend`):** a responsive React and Tailwind app with a side menu that shows only the pages your role may use. It has the dashboard (control chart, Pareto and root cause suggestions), defect logging and CSV upload, user approval and password management. Run it with `cd frontend`, `npm install`, `npm run dev`, then open http://localhost:5173 while the API runs on port 5000.
- **Classic page:** alerts, corrective actions, thresholds, reports, the dataset prediction form and the SUS survey still live in the page served by the API at http://127.0.0.1:5000. The new website links to it under **More tools**.
- **Going live:** see `docs/DEPLOYMENT.md` for the step-by-step guide and `docs/ARCHITECTURE.md` for the design decisions.
- **Updating an old database:** users have new columns. Delete `defect_qc.db` and run `python -m backend.seed` again.

---

## 1. Start the software

You need **Python 3.11 or newer**. Open a terminal inside the folder that contains `backend` and `defect_analysis`, then run these commands one at a time.

**Windows**
```
python -m venv venv
venv\Scripts\activate
pip install -r backend/requirements.txt
python -m backend.seed
flask --app backend.app run
```

**Mac or Linux**: use `source venv/bin/activate` instead of the second line.

Then open **http://127.0.0.1:5000** in your browser. To stop the software, press **Ctrl+C** in the terminal.

- `python -m backend.seed` creates the database, the demo users and about 5,500 sample records. You only need it the first time.
- Next time, you only need to activate the environment and run the last command.
- To start again with fresh demo data, delete the file `defect_qc.db` and run `python -m backend.seed` again.

---

## 2. Sign in

Every demo account uses the password **Password123!**

| Username | Role | Main job |
|---|---|---|
| `qc.engineer` | QC Engineer | Records defects and corrective actions |
| `supervisor` | Line Supervisor | Watches Line A and acknowledges alerts |
| `manager` | Quality Manager | Sets thresholds, approves actions, trains the model |
| `admin` | IT Administrator | Manages user accounts |

Use **Sign out** at the top right to switch accounts. The page only shows what the signed-in role is allowed to do.

---

## 3. What each role can do

| Feature | QC Engineer | Line Supervisor | Quality Manager | IT Administrator |
|---|:---:|:---:|:---:|:---:|
| Log defects and upload CSV files | Yes | | | |
| View the dashboard and charts | Yes | Own line only | Yes | |
| See root cause suggestions and investigate patterns | Yes | Yes | Yes | |
| See alerts | Yes | Yes | Yes | |
| Acknowledge alerts | | Yes | Yes | |
| Set alert thresholds | | | Yes | |
| Log a corrective action and mark it implemented | Yes | | | |
| Approve a corrective action | | | Yes | |
| Train the model and see model quality | | | Yes | |
| Download Excel and PDF reports | Yes | | Yes | |
| Manage user accounts | | | | Yes |
| See SUS survey results | | | Yes | Yes |
| Fill in the SUS survey | Yes | Yes | Yes | Yes |

---

## 4. Using the dashboard

**Control chart (top of the page).** The headline says how many days, weeks or months went outside the control limits. The line shows the defect rate, the dashed lines are the upper and lower limits, and orange points are above the upper limit. The green dotted line is a moving average.

- Use **Daily, Weekly or Monthly** to change the time step.
- Use **All, Last 30, Last 12 or Last 6** to zoom in on recent periods.
- Use the **Line A, B or C** buttons to look at one production line.

**Pareto analysis.** Bars show which defect types, machines or severity levels cause the most defects. Dark bars are the "vital few" that make up the first 80%. Switch the view with **Defect type, Machine or Severity**. Narrow it down with the **Shift, From and To** filters.

**What moves the defect rate and the heatmap.** These show which factors move together with the defect rate, such as humidity, machine age, shift or machine. Teal means a positive link and orange means a negative link. A link is not proof of a cause.

**Investigate a defect pattern.** Choose a defect type and a line, then click **Find likely causes**. You get the most likely root causes with a confidence percentage. If the system says "low confidence", check the Pareto chart and the heatmap too. The model must be trained first (see section 6).

**Suggested root causes.** A table of recent defects, each with the model's top suggestion and the next most likely causes. These are leads to check, not confirmed causes.

---

## 5. Log a defect (QC Engineer)

Sign in as `qc.engineer`. The **Log a defect** form is at the top of the page.

1. Fill in the date, production line, product, shift, machine, batch number, defect type, severity, units inspected and defects found.
2. Click **Save record**. The charts update straight away.

Rules:
- **Defects found** is the quantity and cannot be higher than **Units inspected**.
- Enter `0` defects for a clean batch. The defect type and severity are then saved as `None`.
- If there are defects, you must choose a severity: **Minor, Major, Critical or Safety-Critical**.
- A **Safety-Critical** defect raises an alert immediately.

Example: Line A, Housing, Morning, machine M-01, batch B-TEST-1, defect type Scratch, severity Minor, 200 units, 5 defects.

**Upload many records at once.** Under **Alerts, import and reports**, choose a CSV or Excel file and click **Upload**. If any row is wrong, nothing is saved and the message tells you what to fix. The file needs these columns:

```
inspection_date, production_line, product_type, shift, machine_id,
defect_type, batch_number, severity, units_inspected, defect_count
```
Optional columns: `temperature`, `humidity`, `machine_age_months`, `root_cause`. Use `None` for defect type and severity when `defect_count` is 0.

---

## 6. Train the model (Quality Manager)

Sign in as `manager`, scroll to **Suggested root causes**, and click **Train on current records**. It takes a few seconds. Afterwards you see:

- the accuracy, precision, recall and F1 of the decision tree
- the result of a Random Forest used as a comparison
- the most influential features
- the share of the model's suggestions that engineers confirmed when logging corrective actions

Train the model again after you add many new records.

---

## 6A. Predict from the defect dataset

The panel **Predict from defect data** uses models trained on `data/defects_data.csv` (1,000 defect records). Pick what to predict with the buttons **Severity, Defect type or Repair cost**, fill in the fields and click **Predict**.

- Severity and defect type are predicted from the product, date, location, inspection method and the other of those two fields. **Repair cost is never an input for them**, because it is only known after the repair.
- Repair cost is predicted from the product, date, defect type, location, severity and inspection method.
- The form only accepts values that appear in the dataset: the listed options, product IDs 1 to 100, and dates from 2024-01-01 to 2024-06-30. Anything else shows a clear message.
- Under the form you see how well the model did on rows it had not seen. **If it says the model is no better than guessing, believe it.** With the current dataset all three models score about the same as always guessing the most common answer (severity 31% against 36%, defect type 32% against 35%, repair cost R² of about 0), so the features carry almost no signal. The percentages shown are not real certainty.

**First time:** sign in as `manager` and click **Train models** (about 15 seconds), or run `python -m defect_analysis.train_model` from the project folder. The models are saved in the `models` folder.

**When `defects_data.csv` changes:**
1. Replace `data/defects_data.csv` with the new file. It needs the same 8 columns, no missing values, and dates written as M/D/YYYY.
2. Run `python -m defect_analysis.train_model` (or click **Train models** as the Quality Manager).
3. Refresh the page. The valid options, ranges and the quality summary update by themselves.

The script prints accuracy, precision, recall, F1 and the confusion matrix for severity and defect type, and MAE, RMSE and R² for repair cost, next to the "always guess" baseline. Add `--targets severity` to train one target only.

---

## 7. Alerts

An alert is raised in two cases:
- a **Safety-Critical** defect is logged, or
- a line's defect rate over the last 7 days goes **above its threshold** (the demo starts at 2% for each line).

Open alerts appear in a box at the top of the page. A Line Supervisor or Quality Manager clicks **Acknowledge** when they have seen it. If an alert for the same line is still open, no second one is created.

**Change a threshold (Quality Manager).** Under **Alerts, import and reports**, enter the line and the percentage, then click **Save threshold**.

**Email is optional.** Without a mail server, alerts only show in the app and the alert says the email is not configured. To send emails, set these before starting the software: `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USER`, `MAIL_PASSWORD`, `MAIL_FROM`. If the mail server is down, the alert still shows in the app and the email is retried later.

---

## 8. Corrective actions

1. **QC Engineer:** under **Corrective actions**, fill in the line, the confirmed root cause and what will be done. You can also say what the model suggested, which feeds the agreement rate. Click **Save action**.
2. **Quality Manager:** click **Approve**.
3. **QC Engineer:** after the fix is made, click **Mark implemented**.
4. Click **Check effect**. It compares the defect rate for 28 days before and after the action. With the demo data this usually says "not enough data yet", because 28 days of new records are needed after the action.

---

## 9. Reports

QC Engineers and Quality Managers can click **Download Excel report** or **Download PDF report** under **Alerts, import and reports**. The report has the overall defect rate, the trend, the Pareto tables and the correlations.

---

## 10. Manage users (IT Administrator)

Sign in as `admin`. The **User accounts** table lets you:
- change a person's role
- disable or enable an account
- add a user with a username, name, email, role and password of at least 8 characters
- give a user an **assigned line** so that they only see that line

The administrator cannot disable their own account.

---

## 11. Rate the system (SUS survey)

Anyone signed in can click **Rate this system** in the header, answer the 10 statements from 1 to 5, and click **Submit**. You get a score out of 100. The Quality Manager and IT Administrator can see the average and range of all responses. Use this for your usability evaluation.

---

## 12. Optional: use MySQL instead of the built-in database

1. Create the database with the script: `mysql -u root -p < backend/schema.sql`
2. Set the environment variables before starting the software.

   Windows: `set DATABASE_URL=mysql+pymysql://user:password@localhost:3306/defect_qc`
   Mac or Linux: `export DATABASE_URL=mysql+pymysql://user:password@localhost:3306/defect_qc`

   Also set `SECRET_KEY` to a long random text.
3. Run `python -m backend.seed` and then `flask --app backend.app run`.

Or run everything with Docker: `docker compose up --build`, then open http://localhost:5000.

---

## 13. Run the tests

```
python -m pytest
```
All tests should pass. On GitHub, every push runs the same tests automatically. Open the **Actions** tab of the repository and look for a green tick.

---

## 14. Fix common problems

| Problem | What to do |
|---|---|
| `flask is not recognized` | Activate the environment again: `venv\Scripts\activate` |
| `No module named backend` | Go to the folder that contains `backend` and `defect_analysis` |
| Port 5000 is already used | Run `flask --app backend.app run -p 5055` and open http://127.0.0.1:5055 |
| The page is empty after signing in | Run `python -m backend.seed`, then refresh the page |
| Errors after updating the software | Delete `defect_qc.db`, then run `python -m backend.seed` again |
| "Model not trained yet" | Sign in as `manager` and click **Train on current records** |
| Wrong password | Demo accounts use `Password123!`. Change these passwords before any real use. |

---

## Folder guide

- `defect_analysis/` holds the calculations: validation, trends, Pareto, correlation, control chart, decision tree, access rules and the dataset prediction code (`preprocess.py`, `train_model.py`, `predictor.py`).
- `data/` holds `defects_data.csv`, and `models/` (created by training) holds the saved models.
- `backend/` holds the web server, database setup (`schema.sql`) and the dashboard page (`backend/static/index.html`).
- `dashboard_prototype/` is an early version of the dashboard with fixed data.

## Limits to remember

- The root cause output is a suggestion with a confidence level, not a confirmed cause. Engineers should check it before acting.
- The system works with defect records that people enter. It does not read images or machine sensors.
- Not included: HTTPS and online hosting, password reset and login attempt limits.
