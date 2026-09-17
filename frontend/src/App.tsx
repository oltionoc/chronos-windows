import { Routes, Route } from 'react-router-dom';
import { ProtectedRoute, RoleRoute } from './auth/ProtectedRoute';
import { AppLayout } from './layout/AppLayout';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { AlertsPage } from './pages/AlertsPage';
import { Forbidden } from './pages/Forbidden';
import { NotFound } from './pages/NotFound';
import { EmployeeListPage } from './pages/employees/EmployeeListPage';
import { EmployeeFormPage } from './pages/employees/EmployeeFormPage';
import { EmployeeDetailPage } from './pages/employees/EmployeeDetailPage';
import { ShiftScheduleListPage } from './pages/shiftSchedules/ShiftScheduleListPage';
import { ShiftScheduleFormPage } from './pages/shiftSchedules/ShiftScheduleFormPage';
import { DeviceListPage } from './pages/devices/DeviceListPage';
import { DeviceFormPage } from './pages/devices/DeviceFormPage';
import { DeviceDetailPage } from './pages/devices/DeviceDetailPage';
import { LocationListPage } from './pages/locations/LocationListPage';
import { AttendanceDailyStatusPage } from './pages/attendance/AttendanceDailyStatusPage';
import { AttendanceLogsPage } from './pages/attendance/AttendanceLogsPage';
import { LeaveListPage } from './pages/leave/LeaveListPage';
import { LeaveFormPage } from './pages/leave/LeaveFormPage';
import { LeaveDetailPage } from './pages/leave/LeaveDetailPage';
import { PayrollRunsListPage } from './pages/payroll/PayrollRunsListPage';
import { PayrollRunNewPage } from './pages/payroll/PayrollRunNewPage';
import { PayrollRunDetailPage } from './pages/payroll/PayrollRunDetailPage';
import { PayrollLineDetailPage } from './pages/payroll/PayrollLineDetailPage';
import { PenaltiesConfigPage } from './pages/config/PenaltiesConfigPage';
import { OvertimeConfigPage } from './pages/config/OvertimeConfigPage';
import { AbsenceRuleConfigPage } from './pages/config/AbsenceRuleConfigPage';
import { HolidaysConfigPage } from './pages/config/HolidaysConfigPage';
import { LeaveTypesConfigPage } from './pages/config/LeaveTypesConfigPage';
import { UsersPage } from './pages/settings/UsersPage';
import { ProfilePage } from './pages/settings/ProfilePage';

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/403" element={<Forbidden />} />

        <Route element={<AppLayout />}>
          {/* Routes available to both admin and manager */}
          <Route element={<RoleRoute allow={['admin', 'manager']} />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/attendance" element={<AttendanceDailyStatusPage />} />
            <Route path="/attendance/logs" element={<AttendanceLogsPage />} />
            <Route path="/leave" element={<LeaveListPage />} />
            <Route path="/leave/new" element={<LeaveFormPage />} />
            <Route path="/leave/:id" element={<LeaveDetailPage />} />
            <Route path="/settings/profile" element={<ProfilePage />} />
          </Route>

          {/* full access for admin, or a manager for their own location
              (enforced server-side — see app/deps.py assert_location_access) */}
          <Route element={<RoleRoute allow={['admin', 'manager']} />}>
            <Route path="/employees" element={<EmployeeListPage />} />
            <Route path="/employees/new" element={<EmployeeFormPage />} />
            <Route path="/employees/:id" element={<EmployeeDetailPage />} />
            <Route path="/employees/:id/edit" element={<EmployeeFormPage />} />
            <Route path="/shift-schedules" element={<ShiftScheduleListPage />} />
            <Route path="/shift-schedules/new" element={<ShiftScheduleFormPage />} />
            <Route path="/shift-schedules/:id/edit" element={<ShiftScheduleFormPage />} />
            <Route path="/devices" element={<DeviceListPage />} />
            <Route path="/devices/new" element={<DeviceFormPage />} />
            <Route path="/devices/:id" element={<DeviceDetailPage />} />
            <Route path="/payroll/runs" element={<PayrollRunsListPage />} />
            <Route path="/payroll/runs/new" element={<PayrollRunNewPage />} />
            <Route path="/payroll/runs/:id" element={<PayrollRunDetailPage />} />
            <Route path="/payroll/runs/:id/employees/:employeeId" element={<PayrollLineDetailPage />} />
            <Route path="/config/penalties" element={<PenaltiesConfigPage />} />
            <Route path="/config/overtime" element={<OvertimeConfigPage />} />
            <Route path="/config/absence-rule" element={<AbsenceRuleConfigPage />} />
            <Route path="/config/holidays" element={<HolidaysConfigPage />} />
          </Route>

          {/* admin-only routes */}
          <Route element={<RoleRoute allow={['admin']} />}>
            <Route path="/locations" element={<LocationListPage />} />
            <Route path="/config/leave-types" element={<LeaveTypesConfigPage />} />
            <Route path="/settings/users" element={<UsersPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

export default App;
