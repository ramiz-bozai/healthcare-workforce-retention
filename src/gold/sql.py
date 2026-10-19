"""Gold Spark-flavored SQL. Tokens: __AS_OF__ __HISTORY_START__ __FUTURE_END__
__COVERAGE_THRESHOLD__ __OPEN_SHIFT_THRESHOLD__ __ATTRITION_HORIZON__
__SHORTAGE_PRIMARY__ __SHORTAGE_SECONDARY__.
"""

from __future__ import annotations

SNAPSHOT_CALENDAR = """
CREATE OR REPLACE TABLE gold.snapshot_calendar AS
SELECT snapshot_date,
       CASE WHEN snapshot_date = DATE '__AS_OF__' THEN TRUE ELSE FALSE END AS is_inference_snapshot
FROM (
    SELECT last_day(CAST(d AS DATE)) AS snapshot_date
    FROM generate_series(
        date_trunc('month', DATE '__HISTORY_START__'),
        date_trunc('month', DATE '__AS_OF__') - INTERVAL 1 MONTH,
        INTERVAL 1 MONTH
    ) AS t(d)
    UNION ALL
    SELECT DATE '__AS_OF__'
)
WHERE snapshot_date >= DATE '__HISTORY_START__'
"""

ROLE_COST = """
CREATE OR REPLACE TABLE gold.role_cost_assumptions AS
SELECT * FROM silver.role_cost_assumptions
"""

METRIC_CATALOG = """
CREATE OR REPLACE TABLE gold.metric_catalog AS
SELECT * FROM (
    VALUES
      ('active_headcount', 'executive_kpis', 'as_of', 'Count of employees active at as_of (hire_date <= as_of and employment end > as_of)', 0),
      ('vacancy_rate', 'executive_kpis', 'as_of', 'open_fte / (active_headcount + open_fte)', 0),
      ('overtime_hours_30d', 'executive_kpis', 'as_of', 'Sum of time_cards.overtime_hours in (as_of-29, as_of]', 0),
      ('unplanned_absence_rate_30d', 'executive_kpis', 'as_of', 'unplanned_absence_hours_30d / (productive_hours_30d + unplanned_absence_hours_30d)', 0),
      ('coverage_ratio_7d', 'executive_kpis', 'as_of', 'sum(productive_hours) / sum(required_hours) over last 7 days', 0),
      ('trailing_coverage_gap_hours_14d', 'executive_kpis', 'as_of', 'sum(greatest(required_hours - productive_hours, 0)) over last 14 days', 0),
      ('observed_attrition_rate_90d', 'executive_kpis', 'as_of', 'voluntary exits in (as_of-90, as_of] / active_headcount', 0),
      ('planning_open_salary_exposure_usd', 'executive_kpis', 'as_of', 'sum(open_fte * role avg annual salary). Planning assumption, not savings.', 0),
      ('planning_overtime_agency_usd_30d', 'executive_kpis', 'as_of', 'overtime_hours_30d * hours-weighted agency hourly. Planning assumption, not savings.', 0),
      ('coverage_ratio', 'unit_day_coverage', 'department x date', 'productive_hours / required_hours', 0),
      ('open_shift_share', 'unit_day_coverage', 'department x date', 'greatest(required_heads - assigned_heads, 0) / required_heads', 0),
      ('is_shortage_day', 'unit_day_coverage', 'department x date', 'coverage_ratio < __COVERAGE_THRESHOLD__ OR open_shift_share > __OPEN_SHIFT_THRESHOLD__', 0),
      ('label_voluntary_90d', 'employee_month_features', 'employee x snapshot', '1 if voluntary separation in (snapshot, snapshot+90d]', 0),
      ('label_shortage_next_14d', 'unit_week_features', 'department x week', '1 if any shortage day in (week_end, week_end+14d]; trainable only when week_end+14 <= as_of', 0)
) AS t(metric_name, table_name, grain, formula, includes_model)
"""

UNIT_DAY = """
CREATE OR REPLACE TABLE gold.unit_day_coverage AS
WITH days AS (
    SELECT CAST(d AS DATE) AS coverage_date
    FROM generate_series(DATE '__HISTORY_START__', DATE '__AS_OF__', INTERVAL 1 DAY) AS t(d)
),
req AS (
    SELECT department_id,
           requirement_date AS coverage_date,
           SUM(required_heads) AS required_heads,
           SUM(required_hours) AS required_hours
    FROM silver.staffing_requirements
    GROUP BY 1, 2
),
assigned AS (
    SELECT department_id,
           shift_date AS coverage_date,
           COUNT(*) AS assigned_heads,
           SUM(scheduled_hours) AS assigned_hours
    FROM silver.schedule_assignments
    GROUP BY 1, 2
),
worked AS (
    SELECT department_id,
           work_date AS coverage_date,
           SUM(hours_worked) AS productive_hours,
           SUM(overtime_hours) AS overtime_hours
    FROM silver.time_cards
    GROUP BY 1, 2
),
unplanned AS (
    SELECT department_id,
           absence_date AS coverage_date,
           SUM(hours_missed) AS unplanned_absence_hours
    FROM silver.absences
    WHERE absence_type = 'unplanned_callout'
    GROUP BY 1, 2
),
census AS (
    SELECT department_id, census_date AS coverage_date, demand_index, flu_season_flag
    FROM silver.census_proxy
)
SELECT
    d.department_id,
    days.coverage_date,
    COALESCE(req.required_heads, 0) AS required_heads,
    COALESCE(req.required_hours, 0) AS required_hours,
    COALESCE(assigned.assigned_heads, 0) AS assigned_heads,
    COALESCE(assigned.assigned_hours, 0) AS assigned_hours,
    COALESCE(worked.productive_hours, 0) AS productive_hours,
    COALESCE(worked.overtime_hours, 0) AS overtime_hours,
    COALESCE(unplanned.unplanned_absence_hours, 0) AS unplanned_absence_hours,
    GREATEST(COALESCE(req.required_heads, 0) - COALESCE(assigned.assigned_heads, 0), 0) AS open_heads,
    CASE WHEN COALESCE(req.required_heads, 0) = 0 THEN NULL
         ELSE GREATEST(COALESCE(req.required_heads, 0) - COALESCE(assigned.assigned_heads, 0), 0)
              / req.required_heads
    END AS open_shift_share,
    CASE WHEN COALESCE(req.required_hours, 0) = 0 THEN NULL
         ELSE COALESCE(worked.productive_hours, 0) / req.required_hours
    END AS coverage_ratio,
    census.demand_index,
    COALESCE(census.flu_season_flag, 0) AS flu_season_flag,
    CASE
        WHEN COALESCE(req.required_hours, 0) = 0 THEN FALSE
        WHEN (COALESCE(worked.productive_hours, 0) / req.required_hours) < __COVERAGE_THRESHOLD__ THEN TRUE
        WHEN COALESCE(req.required_heads, 0) > 0
             AND (GREATEST(req.required_heads - COALESCE(assigned.assigned_heads, 0), 0) / req.required_heads)
                 > __OPEN_SHIFT_THRESHOLD__ THEN TRUE
        ELSE FALSE
    END AS is_shortage_day
FROM silver.departments d
CROSS JOIN days
LEFT JOIN req
  ON req.department_id = d.department_id AND req.coverage_date = days.coverage_date
LEFT JOIN assigned
  ON assigned.department_id = d.department_id AND assigned.coverage_date = days.coverage_date
LEFT JOIN worked
  ON worked.department_id = d.department_id AND worked.coverage_date = days.coverage_date
LEFT JOIN unplanned
  ON unplanned.department_id = d.department_id AND unplanned.coverage_date = days.coverage_date
LEFT JOIN census
  ON census.department_id = d.department_id AND census.coverage_date = days.coverage_date
"""

UNIT_WEEK = """
CREATE OR REPLACE TABLE gold.unit_week_features AS
WITH base AS (
    SELECT
        department_id,
        CAST(date_trunc('week', coverage_date) AS DATE) AS week_start,
        coverage_date,
        coverage_ratio,
        open_shift_share,
        overtime_hours,
        unplanned_absence_hours,
        demand_index,
        is_shortage_day
    FROM gold.unit_day_coverage
),
weeks AS (
    SELECT
        department_id,
        week_start,
        week_start + INTERVAL 6 DAY AS week_end,
        AVG(coverage_ratio) AS avg_coverage_ratio,
        AVG(open_shift_share) AS avg_open_shift_share,
        SUM(overtime_hours) AS overtime_hours,
        SUM(unplanned_absence_hours) AS unplanned_absence_hours,
        AVG(demand_index) AS avg_demand_index,
        SUM(CASE WHEN is_shortage_day THEN 1 ELSE 0 END) AS shortage_day_count,
        MAX(CASE WHEN is_shortage_day THEN 1 ELSE 0 END) = 1 AS is_shortage_week
    FROM base
    GROUP BY 1, 2
)
SELECT
    w.department_id,
    w.week_start,
    CAST(w.week_end AS DATE) AS week_end,
    w.avg_coverage_ratio,
    w.avg_open_shift_share,
    w.overtime_hours,
    w.unplanned_absence_hours,
    w.avg_demand_index,
    w.shortage_day_count,
    w.is_shortage_week,
    CASE WHEN EXISTS (
        SELECT 1 FROM gold.unit_day_coverage d
        WHERE d.department_id = w.department_id
          AND d.coverage_date > CAST(w.week_end AS DATE)
          AND d.coverage_date <= CAST(w.week_end AS DATE) + INTERVAL __SHORTAGE_PRIMARY__ DAY
          AND d.is_shortage_day
    ) THEN 1 ELSE 0 END AS label_shortage_next_14d,
    CASE WHEN EXISTS (
        SELECT 1 FROM gold.unit_day_coverage d
        WHERE d.department_id = w.department_id
          AND d.coverage_date > CAST(w.week_end AS DATE)
          AND d.coverage_date <= CAST(w.week_end AS DATE) + INTERVAL __SHORTAGE_SECONDARY__ DAY
          AND d.is_shortage_day
    ) THEN 1 ELSE 0 END AS label_shortage_next_28d,
    CAST(w.week_end AS DATE) + INTERVAL __SHORTAGE_PRIMARY__ DAY <= DATE '__AS_OF__' AS label_window_complete_14d,
    CAST(w.week_end AS DATE) + INTERVAL __SHORTAGE_SECONDARY__ DAY <= DATE '__AS_OF__' AS label_window_complete_28d
FROM weeks w
"""

EMPLOYEE_MONTH = """
CREATE OR REPLACE TABLE gold.employee_month_features AS
WITH employment AS (
    SELECT
        e.employee_id,
        e.role_code,
        e.department_id,
        e.facility_id,
        e.primary_shift_code,
        e.compensation_band,
        e.fte,
        e.hire_date,
        e.manager_employee_id,
        COALESCE(e.termination_date, a.first_separation) AS employment_end
    FROM silver.employees e
    LEFT JOIN (
        SELECT employee_id, MIN(separation_date) AS first_separation
        FROM silver.attrition_events
        GROUP BY employee_id
    ) a ON e.employee_id = a.employee_id
),
active AS (
    SELECT emp.*, cal.snapshot_date, cal.is_inference_snapshot
    FROM employment emp
    CROSS JOIN gold.snapshot_calendar cal
    WHERE emp.hire_date <= cal.snapshot_date
      AND (emp.employment_end IS NULL OR emp.employment_end > cal.snapshot_date)
),
span AS (
    SELECT snapshot_date, manager_employee_id AS manager_id, COUNT(*) AS manager_span
    FROM active
    WHERE manager_employee_id IS NOT NULL
    GROUP BY 1, 2
),
open_pos AS (
    SELECT
        cal.snapshot_date,
        p.department_id,
        SUM(p.fte) AS open_fte_in_unit
    FROM gold.snapshot_calendar cal
    JOIN silver.open_positions p
      ON p.opened_date <= cal.snapshot_date
     AND (p.filled_date IS NULL OR p.filled_date > cal.snapshot_date)
     AND p.status = 'open'
    GROUP BY 1, 2
),
ot AS (
    SELECT
        a.employee_id,
        a.snapshot_date,
        SUM(CASE WHEN t.work_date > a.snapshot_date - INTERVAL 30 DAY AND t.work_date <= a.snapshot_date THEN t.overtime_hours ELSE 0 END) AS ot_hours_30d,
        SUM(CASE WHEN t.work_date > a.snapshot_date - INTERVAL 90 DAY AND t.work_date <= a.snapshot_date THEN t.overtime_hours ELSE 0 END) AS ot_hours_90d
    FROM active a
    LEFT JOIN silver.time_cards t
      ON t.employee_id = a.employee_id AND t.work_date <= a.snapshot_date
    GROUP BY 1, 2
),
sch AS (
    SELECT
        a.employee_id,
        a.snapshot_date,
        SUM(CASE WHEN s.shift_date > a.snapshot_date - INTERVAL 30 DAY AND s.shift_date <= a.snapshot_date THEN s.is_extra_shift ELSE 0 END) AS extra_shift_count_30d,
        SUM(CASE WHEN s.shift_date > a.snapshot_date - INTERVAL 90 DAY AND s.shift_date <= a.snapshot_date THEN s.is_swap ELSE 0 END) AS swap_count_90d,
        AVG(CASE WHEN s.shift_date > a.snapshot_date - INTERVAL 90 DAY AND s.shift_date <= a.snapshot_date
                 THEN CASE WHEN s.shift_code = 'NIGHTS' THEN 1.0 ELSE 0.0 END END) AS nights_share_90d
    FROM active a
    LEFT JOIN silver.schedule_assignments s
      ON s.employee_id = a.employee_id AND s.shift_date <= a.snapshot_date
    GROUP BY 1, 2
),
absn AS (
    SELECT
        a.employee_id,
        a.snapshot_date,
        SUM(CASE WHEN b.absence_date > a.snapshot_date - INTERVAL 90 DAY AND b.absence_date <= a.snapshot_date
                  AND b.absence_type = 'unplanned_callout' THEN b.hours_missed ELSE 0 END) AS unplanned_absence_hours_90d,
        SUM(CASE WHEN b.absence_date > a.snapshot_date - INTERVAL 90 DAY AND b.absence_date <= a.snapshot_date
                 THEN b.hours_missed ELSE 0 END) AS absence_hours_90d
    FROM active a
    LEFT JOIN silver.absences b
      ON b.employee_id = a.employee_id AND b.absence_date <= a.snapshot_date
    GROUP BY 1, 2
)
SELECT
    a.employee_id,
    a.snapshot_date,
    a.is_inference_snapshot,
    a.role_code,
    a.department_id,
    a.facility_id,
    a.primary_shift_code,
    a.compensation_band,
    b.band_rank,
    a.fte,
    ROUND(date_diff('day', a.hire_date, a.snapshot_date) / 30.44, 2) AS tenure_months,
    CASE
        WHEN date_diff('day', a.hire_date, a.snapshot_date) / 30.44 < 12 THEN '0-12'
        WHEN date_diff('day', a.hire_date, a.snapshot_date) / 30.44 < 24 THEN '12-24'
        WHEN date_diff('day', a.hire_date, a.snapshot_date) / 30.44 < 60 THEN '24-60'
        ELSE '60+'
    END AS tenure_band,
    COALESCE(sp.manager_span, 0) AS manager_span,
    d.vacancy_rate AS unit_vacancy_rate,
    COALESCE(op.open_fte_in_unit, 0) AS open_fte_in_unit,
    COALESCE(ot.ot_hours_30d, 0) AS ot_hours_30d,
    COALESCE(ot.ot_hours_90d, 0) AS ot_hours_90d,
    COALESCE(sch.extra_shift_count_30d, 0) AS extra_shift_count_30d,
    COALESCE(sch.swap_count_90d, 0) AS swap_count_90d,
    COALESCE(sch.nights_share_90d, 0) AS nights_share_90d,
    COALESCE(absn.unplanned_absence_hours_90d, 0) AS unplanned_absence_hours_90d,
    CASE WHEN COALESCE(absn.absence_hours_90d, 0) = 0 THEN 0
         ELSE COALESCE(absn.unplanned_absence_hours_90d, 0) / absn.absence_hours_90d
    END AS unplanned_absence_rate_90d,
    CASE WHEN EXISTS (
        SELECT 1 FROM silver.attrition_events ev
        WHERE ev.employee_id = a.employee_id
          AND ev.separation_type = 'voluntary'
          AND ev.separation_date > a.snapshot_date
          AND ev.separation_date <= a.snapshot_date + INTERVAL __ATTRITION_HORIZON__ DAY
    ) THEN 1 ELSE 0 END AS label_voluntary_90d,
    a.snapshot_date + INTERVAL __ATTRITION_HORIZON__ DAY <= DATE '__FUTURE_END__' AS label_window_complete
FROM active a
LEFT JOIN silver.compensation_bands b
  ON a.role_code = b.role_code AND a.compensation_band = b.band_code
LEFT JOIN span sp
  ON a.snapshot_date = sp.snapshot_date
 AND COALESCE(a.manager_employee_id, a.employee_id) = sp.manager_id
LEFT JOIN silver.departments d ON a.department_id = d.department_id
LEFT JOIN open_pos op
  ON a.snapshot_date = op.snapshot_date AND a.department_id = op.department_id
LEFT JOIN ot ON a.employee_id = ot.employee_id AND a.snapshot_date = ot.snapshot_date
LEFT JOIN sch ON a.employee_id = sch.employee_id AND a.snapshot_date = sch.snapshot_date
LEFT JOIN absn ON a.employee_id = absn.employee_id AND a.snapshot_date = absn.snapshot_date
"""

EXEC_KPIS = """
CREATE OR REPLACE TABLE gold.executive_kpis AS
WITH active AS (
    SELECT e.employee_id, e.role_code, e.department_id
    FROM silver.employees e
    LEFT JOIN (
        SELECT employee_id, MIN(separation_date) AS first_separation
        FROM silver.attrition_events
        GROUP BY employee_id
    ) a ON e.employee_id = a.employee_id
    WHERE e.hire_date <= DATE '__AS_OF__'
      AND (COALESCE(e.termination_date, a.first_separation) IS NULL
           OR COALESCE(e.termination_date, a.first_separation) > DATE '__AS_OF__')
),
ot AS (
    SELECT SUM(overtime_hours) AS overtime_hours_30d
    FROM silver.time_cards
    WHERE work_date > DATE '__AS_OF__' - INTERVAL 30 DAY
      AND work_date <= DATE '__AS_OF__'
),
prod AS (
    SELECT SUM(hours_worked) AS productive_hours_30d
    FROM silver.time_cards
    WHERE work_date > DATE '__AS_OF__' - INTERVAL 30 DAY
      AND work_date <= DATE '__AS_OF__'
),
unp AS (
    SELECT SUM(hours_missed) AS unplanned_absence_hours_30d
    FROM silver.absences
    WHERE absence_type = 'unplanned_callout'
      AND absence_date > DATE '__AS_OF__' - INTERVAL 30 DAY
      AND absence_date <= DATE '__AS_OF__'
),
cov7 AS (
    SELECT SUM(productive_hours) AS productive_hours,
           SUM(required_hours) AS required_hours
    FROM gold.unit_day_coverage
    WHERE coverage_date > DATE '__AS_OF__' - INTERVAL 7 DAY
      AND coverage_date <= DATE '__AS_OF__'
),
gap14 AS (
    SELECT SUM(GREATEST(required_hours - productive_hours, 0)) AS trailing_coverage_gap_hours_14d
    FROM gold.unit_day_coverage
    WHERE coverage_date > DATE '__AS_OF__' - INTERVAL 14 DAY
      AND coverage_date <= DATE '__AS_OF__'
),
exits AS (
    SELECT COUNT(*) AS observed_voluntary_exits_90d
    FROM silver.attrition_events
    WHERE separation_type = 'voluntary'
      AND separation_date > DATE '__AS_OF__' - INTERVAL 90 DAY
      AND separation_date <= DATE '__AS_OF__'
),
openp AS (
    SELECT COALESCE(SUM(p.fte), 0) AS open_fte,
           COALESCE(SUM(p.fte * c.avg_annual_salary_usd), 0) AS planning_open_salary_exposure_usd
    FROM silver.open_positions p
    JOIN gold.role_cost_assumptions c ON p.role_code = c.role_code
    WHERE p.status = 'open'
      AND p.opened_date <= DATE '__AS_OF__'
      AND (p.filled_date IS NULL OR p.filled_date > DATE '__AS_OF__')
),
agency AS (
    SELECT
        SUM(t.overtime_hours * c.agency_hourly_usd)
            / NULLIF(SUM(t.overtime_hours), 0) AS weighted_agency_hourly
    FROM silver.time_cards t
    JOIN silver.employees e ON t.employee_id = e.employee_id
    JOIN gold.role_cost_assumptions c ON e.role_code = c.role_code
    WHERE t.work_date > DATE '__AS_OF__' - INTERVAL 30 DAY
      AND t.work_date <= DATE '__AS_OF__'
      AND t.overtime_hours > 0
)
SELECT
    DATE '__AS_OF__' AS as_of_date,
    (SELECT COUNT(*) FROM active) AS active_headcount,
    (SELECT open_fte FROM openp) AS open_fte,
    (SELECT open_fte FROM openp)
        / NULLIF((SELECT COUNT(*) FROM active) + (SELECT open_fte FROM openp), 0) AS vacancy_rate,
    COALESCE((SELECT overtime_hours_30d FROM ot), 0) AS overtime_hours_30d,
    COALESCE((SELECT unplanned_absence_hours_30d FROM unp), 0) AS unplanned_absence_hours_30d,
    COALESCE((SELECT unplanned_absence_hours_30d FROM unp), 0)
        / NULLIF(
            COALESCE((SELECT productive_hours_30d FROM prod), 0)
            + COALESCE((SELECT unplanned_absence_hours_30d FROM unp), 0),
            0
        ) AS unplanned_absence_rate_30d,
    (SELECT productive_hours FROM cov7) / NULLIF((SELECT required_hours FROM cov7), 0) AS coverage_ratio_7d,
    COALESCE((SELECT trailing_coverage_gap_hours_14d FROM gap14), 0) AS trailing_coverage_gap_hours_14d,
    COALESCE((SELECT observed_voluntary_exits_90d FROM exits), 0) AS observed_voluntary_exits_90d,
    COALESCE((SELECT observed_voluntary_exits_90d FROM exits), 0)
        / NULLIF((SELECT COUNT(*) FROM active), 0) AS observed_attrition_rate_90d,
    COALESCE((SELECT planning_open_salary_exposure_usd FROM openp), 0) AS planning_open_salary_exposure_usd,
    COALESCE((SELECT overtime_hours_30d FROM ot), 0)
        * COALESCE((SELECT weighted_agency_hourly FROM agency), 0) AS planning_overtime_agency_usd_30d,
    (SELECT assumption_note FROM gold.role_cost_assumptions LIMIT 1) AS assumption_note
"""

STATEMENTS: tuple[tuple[str, str], ...] = (
    ("snapshot_calendar", SNAPSHOT_CALENDAR),
    ("role_cost_assumptions", ROLE_COST),
    ("metric_catalog", METRIC_CATALOG),
    ("unit_day_coverage", UNIT_DAY),
    ("unit_week_features", UNIT_WEEK),
    ("employee_month_features", EMPLOYEE_MONTH),
    ("executive_kpis", EXEC_KPIS),
)
