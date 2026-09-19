// Shared API types — mirrors BLUEPRINT.md Section 3 (Data Model) and Section 4 (API Surface).
// See FRONTEND_NOTES.md for the exact request/response contract assumptions backend must honor.

export type Role = 'admin' | 'manager';

export interface Paginated<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface BulkImportError {
  row: number;
  message: string;
}

export interface BulkImportResult {
  created: number;
  errors: BulkImportError[];
}

export interface CurrentUser {
  id: number;
  username: string;
  role: Role;
  employee_id: number | null;
  employee_name: string | null;
  location_id: number | null;
  location_name: string | null;
  is_active: boolean;
  last_login_at: string | null;
  // SECURITY: true when HR/Admin set this account's password on its behalf
  // (initial creation, reset, or the seeded bootstrap admin account) — the
  // backend enforces a redirect-to-change-password gate on every other
  // endpoint until this is cleared. See SECURITY_REPORT.md.
  must_change_password: boolean;
}

// ---- Locations ----
export interface Location {
  id: number;
  name: string;
  address: string | null;
  timezone: string;
  is_active: boolean;
}

// ---- Devices ----
export type DeviceType = 'zkteco' | 'hikvision' | 'hikvision_cloud';

export interface Device {
  id: number;
  location_id: number;
  location_name?: string;
  label: string;
  ip_address: string;
  port: number;
  serial_number: string | null;
  device_type: DeviceType;
  auth_username: string | null;
  is_active: boolean;
  last_synced_at: string | null;
  // Device clock vs server clock, in seconds ahead (negative = behind).
  // null means never measured, which is not the same as measured zero.
  clock_skew_seconds: number | null;
  clock_checked_at: string | null;
}

export interface DeviceTestConnectionResult {
  reachable: boolean;
  detail?: string;
}

// ---- Employees ----
export type EmploymentStatus = 'active' | 'inactive' | 'terminated';

export interface Employee {
  id: number;
  location_id: number;
  location_name?: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  national_id: string | null;
  job_title: string | null;
  hire_date: string;
  base_salary_eur: number;
  manager_user_id: number | null;
  manager_name?: string | null;
  employment_status: EmploymentStatus;
}

export interface EmployeeDeviceEnrollment {
  id: number;
  employee_id: number;
  device_id: number;
  device_label?: string;
  device_user_id: string;
  enrolled_at: string | null;
}

export interface EmployeeShiftAssignment {
  id: number;
  employee_id: number;
  shift_schedule_id: number;
  shift_schedule_name?: string;
  effective_from: string;
  effective_to: string | null;
}

// ---- Shift Schedules ----
export interface ShiftBreakWindow {
  id?: number;
  break_start_time: string;
  break_end_time: string;
  is_paid: boolean;
}

export interface ShiftWorkWindow {
  id?: number;
  work_start_time: string;
  work_end_time: string;
}

export interface ShiftScheduleDay {
  id?: number;
  day_of_week: number; // 0 = Monday
  is_working_day: boolean;
  // Derived outer bounds of the day, sent back by the API. A split shift
  // (08:00-12:00 + 17:00-21:00) cannot be expressed by these two alone —
  // `work_windows` is the list that is actually edited and saved.
  work_start_time: string | null;
  work_end_time: string | null;
  work_windows: ShiftWorkWindow[];
  break_windows: ShiftBreakWindow[];
}

export interface ShiftSchedule {
  id: number;
  location_id: number | null;
  location_name?: string;
  name: string;
  grace_minutes_late: number;
  is_active: boolean;
  days?: ShiftScheduleDay[];
}

// ---- Attendance ----
export type PunchType =
  | 'check_in_work'
  | 'check_out_work'
  | 'check_in_break'
  | 'check_out_break'
  // Badged on the device ("start overtime" / "end overtime"), as opposed to
  // overtime inferred from the schedule.
  | 'check_in_overtime'
  | 'check_out_overtime'
  | 'unclassified';

export interface AttendanceLog {
  id: number;
  device_id: number;
  device_label?: string;
  device_user_id: string;
  employee_id: number | null;
  employee_name?: string | null;
  punch_timestamp: string;
  raw_status_code: number;
  punch_type: PunchType | null;
  synced_at: string;
}

export type DailyStatusValue =
  | 'present'
  | 'late'
  | 'absent'
  | 'on_leave'
  | 'holiday'
  | 'not_scheduled';

export interface AttendanceDailyStatus {
  id: number;
  employee_id: number;
  employee_name?: string;
  work_date: string;
  shift_schedule_id: number | null;
  scheduled_start: string | null;
  scheduled_end: string | null;
  actual_first_in: string | null;
  actual_last_out: string | null;
  late_minutes: number;
  early_departure_minutes: number;
  overtime_minutes: number;
  break_minutes_taken: number;
  status: DailyStatusValue;
  is_absence_excused: boolean | null;
  // Overtime pre-approval. `overtime_requires_approval` is true only where
  // the location's overtime config gates payment on approval; elsewhere
  // overtime pays regardless and no pending state is shown.
  overtime_approved_at: string | null;
  overtime_requires_approval: boolean;
  recompute_version: number;
  computed_at: string;
}

// ---- Holidays ----
export interface Holiday {
  id: number;
  // null = every location, same convention as the config tables.
  location_id: number | null;
  location_name?: string | null;
  holiday_date: string;
  name_en: string;
  name_sq: string;
  // Fixed-date holidays repeat every year; moving ones (Eid, Easter) are
  // entered per year with this off.
  recurs_annually: boolean;
}

// ---- Leave ----
export interface LeaveType {
  id: number;
  name_en: string;
  name_sq: string;
  is_paid: boolean;
  annual_entitlement_days: number | null;
  requires_approval: boolean;
  is_active: boolean;
}

export type LeaveStatus = 'pending' | 'approved' | 'rejected' | 'cancelled';

export interface LeaveRecord {
  id: number;
  employee_id: number;
  employee_name?: string;
  leave_type_id: number;
  leave_type_name_en?: string;
  leave_type_name_sq?: string;
  start_date: string;
  end_date: string;
  status: LeaveStatus;
  requested_by_user_id: number;
  requested_by_name?: string;
  approved_by_user_id: number | null;
  approved_by_name?: string | null;
  approved_at: string | null;
  notes: string | null;
}

// ---- Config ----
export type PenaltyRuleType = 'flat_per_minute' | 'threshold_allowance';

export interface PenaltyConfig {
  id: number;
  location_id: number | null;
  location_name?: string;
  rule_type: PenaltyRuleType;
  rate_per_minute_eur: number | null;
  allowance_minutes: number | null;
  flat_amount_eur: number | null;
  max_daily_penalty_eur: number | null;
  early_departure_rate_per_minute_eur: number | null;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
}

export type OvertimeThresholdBasis = 'daily' | 'weekly';

export interface OvertimeConfig {
  id: number;
  location_id: number | null;
  location_name?: string;
  threshold_basis: OvertimeThresholdBasis;
  daily_threshold_minutes: number | null;
  weekly_threshold_minutes: number | null;
  rate_per_hour_eur: number;
  weekend_rate_per_hour_eur: number | null;
  holiday_rate_per_hour_eur: number | null;
  requires_preapproval: boolean;
  monthly_cap_minutes: number | null;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
}

export type AbsenceDeductionBasis = 'flat_amount' | 'full_day_salary_fraction';

export interface AbsenceRuleConfig {
  id: number;
  location_id: number | null;
  location_name?: string;
  rule_type: string;
  deduction_basis: AbsenceDeductionBasis;
  deduction_value: number;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
}

// ---- Users ----
export interface AppUser {
  id: number;
  username: string;
  role: Role;
  location_id: number | null;
  location_name?: string | null;
  employee_id: number | null;
  employee_name?: string | null;
  is_active: boolean;
  last_login_at: string | null;
  must_change_password: boolean;
}

// ---- Payroll ----
export type PayrollRunStatus = 'draft' | 'finalized';

export interface PayrollRun {
  id: number;
  location_id: number | null;
  location_name?: string;
  period_year: number;
  period_month: number;
  status: PayrollRunStatus;
  generated_by_user_id: number;
  generated_by_name?: string;
  finalized_at: string | null;
  line_count?: number;
  total_net_pay_eur?: number;
}

export interface PayrollRunLine {
  id: number;
  payroll_run_id: number;
  employee_id: number;
  employee_name?: string;
  base_salary_eur: number;
  total_late_minutes: number;
  total_lateness_penalty_eur: number;
  total_overtime_minutes: number;
  total_overtime_bonus_eur: number;
  total_absence_days: number;
  total_absence_deduction_eur: number;
  paid_leave_days: number;
  unpaid_leave_days: number;
  net_pay_eur: number;
}

export type AdjustmentType = 'bonus' | 'deduction';

export interface PayrollAdjustment {
  id: number;
  payroll_run_line_id: number;
  type: AdjustmentType;
  amount_eur: number;
  reason: string;
  created_by_user_id: number;
  created_by_name?: string;
}

// ---- Reports ----
export interface OnBreakEmployee {
  employee_id: number;
  employee_name: string;
  break_started_at: string;
}

export interface OnLeaveEmployee {
  employee_id: number;
  employee_name: string;
  leave_type_name_en: string;
  leave_type_name_sq: string;
  start_date: string;
  end_date: string;
}

export interface DashboardSummary {
  present_today: number;
  on_site_now: number;
  late_today: number;
  absent_today: number;
  on_leave_today: number;
  on_leave_employees: OnLeaveEmployee[];
  on_break_now: number;
  on_break_employees: OnBreakEmployee[];
  pending_leave_count: number;
  pending_leave: LeaveRecord[];
  pending_leave_total: number;
}

export interface AttendanceTrendDay {
  work_date: string;
  present: number;
  late: number;
  absent: number;
  on_leave: number;
}

export interface TopLateEmployee {
  employee_id: number;
  employee_name: string;
  total_late_minutes: number;
  late_days: number;
}

export interface TopOvertimeEmployee {
  employee_id: number;
  employee_name: string;
  total_overtime_minutes: number;
  overtime_days: number;
}

export interface AlertItem {
  type: string;
  severity: 'warning' | 'danger';
  message: string;
  employee_id: number | null;
  employee_name: string | null;
  work_date: string | null;
  occurred_at: string | null;
  link: string | null;
  count: number | null;
  device_label: string | null;
  username: string | null;
}

export interface Alerts {
  alerts: AlertItem[];
  count: number;
}

export interface Analytics {
  attendance_trend: AttendanceTrendDay[];
  avg_late_minutes: number;
  total_overtime_minutes: number;
  top_late_employees: TopLateEmployee[];
  top_overtime_employees: TopOvertimeEmployee[];
}


// ---- Device users (read-only import) ----
export interface DeviceUserRow {
  device_user_id: string;
  name: string;
  linked_employee_id: number | null;
  linked_employee_name: string | null;
}
export interface DeviceUsers {
  location_id: number;
  users: DeviceUserRow[];
}

// ---- Licence ----
export interface LicenseStatus {
  issued_to: string;
  edition: string;
  expires: string;
  days_left: number;
  expired: boolean;
  expiring_soon: boolean;
}


// ---- Rota ----
export interface ShiftTemplate {
  id: number;
  location_id: number | null;
  location_name?: string | null;
  name: string;
  work_start_time: string;
  work_end_time: string;
  break_start_time: string | null;
  break_end_time: string | null;
  break_is_paid: boolean;
  grace_minutes_late: number;
  is_active: boolean;
}
export interface RosterEmployeeRow {
  employee_id: number;
  employee_name: string;
  assignments: Record<string, number | null>; // date -> template id, or null (day off)
}
export interface Roster {
  location_id: number;
  week_start: string;
  dates: string[];
  employees: RosterEmployeeRow[];
}
export interface RosterEntryIn {
  employee_id: number;
  work_date: string;
  shift_template_id?: number | null;
  clear?: boolean;
}
