// Endpoint functions grouped by resource. Paths mirror BLUEPRINT.md Section 4
// exactly, except where explicitly noted as an assumption in FRONTEND_NOTES.md
// (marked "ASSUMED" below — these are gaps in BLUEPRINT's documented API
// surface that backend must implement to match this contract, or the frontend
// must be updated once backend's actual shape is known).
import { apiRequest, apiDownload, apiUpload } from './client';
import type {
  AbsenceRuleConfig,
  Alerts,
  Analytics,
  AppUser,
  AttendanceDailyStatus,
  AttendanceLog,
  BulkImportResult,
  CurrentUser,
  DashboardSummary,
  Device,
  DeviceTestConnectionResult,
  DeviceUsers,
  Employee,
  EmployeeDeviceEnrollment,
  EmployeeShiftAssignment,
  Holiday,
  LeaveRecord,
  LeaveType,
  LicenseStatus,
  Location,
  OvertimeConfig,
  Paginated,
  PayrollAdjustment,
  PayrollRun,
  PayrollRunLine,
  PenaltyConfig,
  Role,
  ShiftSchedule,
  ShiftScheduleDay,
} from './types';

// ---- Auth (4.1) ----
export const authApi = {
  // Response body is not specified by BLUEPRINT.md §4.1 beyond "sets httpOnly
  // cookie" — the frontend does not rely on this response's shape and always
  // follows up with GET /auth/me to read the authenticated user/role.
  login: (username: string, password: string) =>
    apiRequest<void>('/auth/login', { method: 'POST', body: { username, password } }),
  logout: () => apiRequest<void>('/auth/logout', { method: 'POST' }),
  me: () => apiRequest<CurrentUser>('/auth/me'),
  changePassword: (current_password: string, new_password: string) =>
    apiRequest<void>('/auth/me/password', {
      method: 'PATCH',
      body: { current_password, new_password },
    }),
};

// ---- Locations (4.2) ----
export const locationsApi = {
  list: () => apiRequest<Location[]>('/locations'),
  create: (data: Partial<Location>) =>
    apiRequest<Location>('/locations', { method: 'POST', body: data }),
  get: (id: number) => apiRequest<Location>(`/locations/${id}`),
  update: (id: number, data: Partial<Location>) =>
    apiRequest<Location>(`/locations/${id}`, { method: 'PUT', body: data }),
};

// ---- Devices (4.3) ----
export const devicesApi = {
  list: (params: { location_id?: number; is_active?: boolean; search?: string } = {}) =>
    apiRequest<Device[]>('/devices', { query: params }),
  create: (data: Partial<Device> & { auth_password?: string }) =>
    apiRequest<Device>('/devices', { method: 'POST', body: data }),
  get: (id: number) => apiRequest<Device>(`/devices/${id}`),
  update: (id: number, data: Partial<Device> & { auth_password?: string }) =>
    apiRequest<Device>(`/devices/${id}`, { method: 'PUT', body: data }),
  remove: (id: number) => apiRequest<void>(`/devices/${id}`, { method: 'DELETE' }),
  testConnection: (id: number) =>
    apiRequest<DeviceTestConnectionResult>(`/devices/${id}/test-connection`, { method: 'POST' }),
  sync: (id: number) => apiRequest<void>(`/devices/${id}/sync`, { method: 'POST' }),
  readUsers: (id: number) => apiRequest<DeviceUsers>(`/devices/${id}/users`, { method: 'POST' }),
};

export const licenseApi = {
  status: () => apiRequest<LicenseStatus>('/license/status'),
  install: (key: string) => apiRequest<LicenseStatus>('/license/status', { method: 'POST', body: { key } }),
};

// ---- Employees & enrollments (4.4) ----
export const employeesApi = {
  list: (params: {
    location_id?: number;
    status?: string;
    search?: string;
    page?: number;
    page_size?: number;
  } = {}) => apiRequest<Paginated<Employee>>('/employees', { query: params }),
  create: (data: Partial<Employee>) =>
    apiRequest<Employee>('/employees', { method: 'POST', body: data }),
  get: (id: number) => apiRequest<Employee>(`/employees/${id}`),
  update: (id: number, data: Partial<Employee>) =>
    apiRequest<Employee>(`/employees/${id}`, { method: 'PUT', body: data }),
  bulkImport: (file: File) => apiUpload<BulkImportResult>('/employees/bulk-import', file),
  deviceEnrollments: (id: number) =>
    apiRequest<EmployeeDeviceEnrollment[]>(`/employees/${id}/device-enrollments`),
  addDeviceEnrollment: (id: number, data: { device_id: number; device_user_id: string }) =>
    apiRequest<EmployeeDeviceEnrollment>(`/employees/${id}/device-enrollments`, {
      method: 'POST',
      body: data,
    }),
  removeDeviceEnrollment: (id: number, enrollmentId: number) =>
    apiRequest<void>(`/employees/${id}/device-enrollments/${enrollmentId}`, { method: 'DELETE' }),
  shiftAssignments: (id: number) =>
    apiRequest<EmployeeShiftAssignment[]>(`/employees/${id}/shift-assignments`),
  addShiftAssignment: (
    id: number,
    data: { shift_schedule_id: number; effective_from: string; effective_to?: string | null }
  ) =>
    apiRequest<EmployeeShiftAssignment>(`/employees/${id}/shift-assignments`, {
      method: 'POST',
      body: data,
    }),
  updateShiftAssignment: (
    id: number,
    assignmentId: number,
    data: Partial<EmployeeShiftAssignment>
  ) =>
    apiRequest<EmployeeShiftAssignment>(`/employees/${id}/shift-assignments/${assignmentId}`, {
      method: 'PUT',
      body: data,
    }),
  removeShiftAssignment: (id: number, assignmentId: number) =>
    apiRequest<void>(`/employees/${id}/shift-assignments/${assignmentId}`, { method: 'DELETE' }),
};

// ---- Shift schedules (4.5) ----
export const shiftSchedulesApi = {
  list: (params: { location_id?: number } = {}) =>
    apiRequest<ShiftSchedule[]>('/shift-schedules', { query: params }),
  create: (data: Partial<ShiftSchedule>) =>
    apiRequest<ShiftSchedule>('/shift-schedules', { method: 'POST', body: data }),
  get: (id: number) => apiRequest<ShiftSchedule>(`/shift-schedules/${id}`),
  update: (id: number, data: Partial<ShiftSchedule>) =>
    apiRequest<ShiftSchedule>(`/shift-schedules/${id}`, { method: 'PUT', body: data }),
  remove: (id: number) => apiRequest<void>(`/shift-schedules/${id}`, { method: 'DELETE' }),
  putDays: (id: number, days: ShiftScheduleDay[]) =>
    apiRequest<ShiftScheduleDay[]>(`/shift-schedules/${id}/days`, { method: 'PUT', body: { days } }),
};

// ---- Attendance (4.6) ----
export const attendanceApi = {
  logs: (params: {
    employee_id?: number;
    device_id?: number;
    date_from?: string;
    date_to?: string;
    unresolved_only?: boolean;
    page?: number;
    page_size?: number;
  } = {}) => apiRequest<Paginated<AttendanceLog>>('/attendance/logs', { query: params }),
  resolveLog: (id: number, employee_id: number) =>
    apiRequest<AttendanceLog>(`/attendance/logs/${id}/resolve`, {
      method: 'PATCH',
      body: { employee_id },
    }),
  dailyStatus: (params: {
    employee_id?: number;
    location_id?: number;
    date_from?: string;
    date_to?: string;
    status?: string;
    page?: number;
    page_size?: number;
  } = {}) => apiRequest<Paginated<AttendanceDailyStatus>>('/attendance/daily-status', { query: params }),
  recompute: (data: { date_from: string; date_to: string; employee_id?: number }) =>
    apiRequest<void>('/attendance/recompute', { method: 'POST', body: data }),
  // ASSUMED endpoint — BLUEPRINT §4.6 does not list a write route for
  // `is_absence_excused`, but DESIGN_SPEC §5.12 requires HR to toggle it
  // inline. See FRONTEND_NOTES.md.
  setExcused: (dailyStatusId: number, is_absence_excused: boolean) =>
    apiRequest<AttendanceDailyStatus>(`/attendance/daily-status/${dailyStatusId}/excused`, {
      method: 'PATCH',
      body: { is_absence_excused },
    }),
  setOvertimeApproval: (dailyStatusId: number, approved: boolean) =>
    apiRequest<AttendanceDailyStatus>(`/attendance/daily-status/${dailyStatusId}/overtime-approval`, {
      method: 'PATCH',
      body: { approved },
    }),
};

// ---- Holidays (public holiday calendar, 2026-09-17) ----
export const holidaysApi = {
  list: (params: { year?: number; location_id?: number } = {}) =>
    apiRequest<Holiday[]>('/holidays', { query: params }),
  create: (data: Partial<Holiday>) => apiRequest<Holiday>('/holidays', { method: 'POST', body: data }),
  update: (id: number, data: Partial<Holiday>) =>
    apiRequest<Holiday>(`/holidays/${id}`, { method: 'PUT', body: data }),
  remove: (id: number) => apiRequest<void>(`/holidays/${id}`, { method: 'DELETE' }),
};

// ---- Leave (4.7) ----
export const leaveApi = {
  leaveTypes: () => apiRequest<LeaveType[]>('/leave-types'),
  createLeaveType: (data: Partial<LeaveType>) =>
    apiRequest<LeaveType>('/leave-types', { method: 'POST', body: data }),
  updateLeaveType: (id: number, data: Partial<LeaveType>) =>
    apiRequest<LeaveType>(`/leave-types/${id}`, { method: 'PUT', body: data }),
  list: (params: {
    employee_id?: number;
    location_id?: number;
    status?: string;
    date_from?: string;
    date_to?: string;
    page?: number;
    page_size?: number;
  } = {}) => apiRequest<Paginated<LeaveRecord>>('/leave-records', { query: params }),
  // ASSUMED endpoint — BLUEPRINT §4.7 does not list GET /leave-records/{id}
  // explicitly, but DESIGN_SPEC §5.16 requires a detail route. See
  // FRONTEND_NOTES.md.
  get: (id: number) => apiRequest<LeaveRecord>(`/leave-records/${id}`),
  create: (data: {
    employee_id: number;
    leave_type_id: number;
    start_date: string;
    end_date: string;
    notes?: string;
  }) => apiRequest<LeaveRecord>('/leave-records', { method: 'POST', body: data }),
  bulkImport: (file: File) => apiUpload<BulkImportResult>('/leave-records/bulk-import', file),
  remove: (id: number) => apiRequest<void>(`/leave-records/${id}`, { method: 'DELETE' }),
};

// ---- Config (4.8) ----
export const configApi = {
  penalty: {
    list: (params: { location_id?: number } = {}) =>
      apiRequest<PenaltyConfig[]>('/config/penalty', { query: params }),
    create: (data: Partial<PenaltyConfig>) =>
      apiRequest<PenaltyConfig>('/config/penalty', { method: 'POST', body: data }),
    get: (id: number) => apiRequest<PenaltyConfig>(`/config/penalty/${id}`),
    update: (id: number, data: Partial<PenaltyConfig>) =>
      apiRequest<PenaltyConfig>(`/config/penalty/${id}`, { method: 'PUT', body: data }),
  },
  overtime: {
    list: (params: { location_id?: number } = {}) =>
      apiRequest<OvertimeConfig[]>('/config/overtime', { query: params }),
    create: (data: Partial<OvertimeConfig>) =>
      apiRequest<OvertimeConfig>('/config/overtime', { method: 'POST', body: data }),
    get: (id: number) => apiRequest<OvertimeConfig>(`/config/overtime/${id}`),
    update: (id: number, data: Partial<OvertimeConfig>) =>
      apiRequest<OvertimeConfig>(`/config/overtime/${id}`, { method: 'PUT', body: data }),
  },
  absenceRule: {
    list: (params: { location_id?: number } = {}) =>
      apiRequest<AbsenceRuleConfig[]>('/config/absence-rule', { query: params }),
    create: (data: Partial<AbsenceRuleConfig>) =>
      apiRequest<AbsenceRuleConfig>('/config/absence-rule', { method: 'POST', body: data }),
    get: (id: number) => apiRequest<AbsenceRuleConfig>(`/config/absence-rule/${id}`),
    update: (id: number, data: Partial<AbsenceRuleConfig>) =>
      apiRequest<AbsenceRuleConfig>(`/config/absence-rule/${id}`, { method: 'PUT', body: data }),
  },
};

// ---- Payroll (4.9) ----
export const payrollApi = {
  runs: (params: { location_id?: number; year?: number; status?: string } = {}) =>
    apiRequest<PayrollRun[]>('/payroll/runs', { query: params }),
  createRun: (data: { period_year: number; period_month: number; location_id: number }) =>
    apiRequest<PayrollRun>('/payroll/runs', { method: 'POST', body: data }),
  getRun: (id: number) => apiRequest<PayrollRun>(`/payroll/runs/${id}`),
  deleteRun: (id: number) => apiRequest<void>(`/payroll/runs/${id}`, { method: 'DELETE' }),
  lines: (id: number) => apiRequest<PayrollRunLine[]>(`/payroll/runs/${id}/lines`),
  lineDetail: (id: number, employeeId: number) =>
    apiRequest<PayrollRunLine & { adjustments: PayrollAdjustment[] }>(
      `/payroll/runs/${id}/lines/${employeeId}`
    ),
  addAdjustment: (
    id: number,
    employeeId: number,
    data: { type: 'bonus' | 'deduction'; amount_eur: number; reason: string }
  ) =>
    apiRequest<PayrollAdjustment>(`/payroll/runs/${id}/lines/${employeeId}/adjustments`, {
      method: 'POST',
      body: data,
    }),
  finalize: (id: number) => apiRequest<PayrollRun>(`/payroll/runs/${id}/finalize`, { method: 'POST' }),
  payslip: (id: number, employeeId: number) =>
    apiDownload(`/payroll/runs/${id}/lines/${employeeId}/payslip.xlsx`),
  exportExcel: (id: number) => apiDownload(`/payroll/runs/${id}/export.xlsx`),
};

// ---- Users (settings/users) ----
// ASSUMED resource — BLUEPRINT §4 has no `/users` CRUD section, but
// DESIGN_SPEC §5.23 requires a full user-account management page. See
// FRONTEND_NOTES.md.
export const usersApi = {
  list: (params: { role?: Role; page?: number; page_size?: number } = {}) =>
    apiRequest<Paginated<AppUser>>('/users', { query: params }),
  create: (data: {
    username: string;
    password: string;
    role: Role;
    location_id?: number | null;
    employee_id?: number | null;
    is_active?: boolean;
  }) => apiRequest<AppUser>('/users', { method: 'POST', body: data }),
  update: (id: number, data: Partial<Pick<AppUser, 'role' | 'location_id' | 'employee_id' | 'is_active'>>) =>
    apiRequest<AppUser>(`/users/${id}`, { method: 'PATCH', body: data }),
  resetPassword: (id: number, new_password: string) =>
    apiRequest<void>(`/users/${id}/reset-password`, { method: 'PATCH', body: { new_password } }),
};

// ---- Reports (4.11) ----
export const reportsApi = {
  dashboardSummary: (params: { location_id?: number; date?: string } = {}) =>
    apiRequest<DashboardSummary>('/reports/dashboard-summary', { query: params }),
  analytics: (params: { days?: number; location_id?: number } = {}) =>
    apiRequest<Analytics>('/reports/analytics', { query: params }),
  alerts: (params: { days?: number; location_id?: number } = {}) =>
    apiRequest<Alerts>('/reports/alerts', { query: params }),
};
