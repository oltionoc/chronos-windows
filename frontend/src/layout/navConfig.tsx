import {
  LayoutDashboard,
  Users,
  CalendarClock,
  HardDrive,
  MapPin,
  ClipboardList,
  FileClock,
  CalendarCheck,
  CalendarDays,
  CalendarRange,
  Wallet,
  Percent,
  Timer,
  UserX,
  Tags,
  UserCog,
  UserCircle,
  AlertTriangle,
  KeyRound
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { CurrentUser } from '../api/types';

export interface NavLeaf {
  type: 'link';
  labelKey: string;
  to: string;
  icon: LucideIcon;
}

export interface NavGroup {
  type: 'group';
  labelKey: string;
  items: NavLeaf[];
}

export interface NavSeparator {
  type: 'separator';
}

export type NavNode = NavLeaf | NavGroup | NavSeparator;

const adminNav: NavNode[] = [
  { type: 'link', labelKey: 'nav.dashboard', to: '/', icon: LayoutDashboard },
  { type: 'link', labelKey: 'nav.alerts', to: '/alerts', icon: AlertTriangle },
  { type: 'separator' },
  { type: 'link', labelKey: 'nav.employees', to: '/employees', icon: Users },
  { type: 'link', labelKey: 'nav.shiftSchedules', to: '/shift-schedules', icon: CalendarClock },
  { type: 'link', labelKey: 'nav.rota', to: '/rota', icon: CalendarRange },
  { type: 'link', labelKey: 'nav.devices', to: '/devices', icon: HardDrive },
  { type: 'link', labelKey: 'nav.locations', to: '/locations', icon: MapPin },
  { type: 'separator' },
  {
    type: 'group',
    labelKey: 'nav.attendance',
    items: [
      { type: 'link', labelKey: 'nav.attendanceDaily', to: '/attendance', icon: ClipboardList },
      { type: 'link', labelKey: 'nav.attendanceLogs', to: '/attendance/logs', icon: FileClock },
    ],
  },
  { type: 'link', labelKey: 'nav.leave', to: '/leave', icon: CalendarCheck },
  { type: 'link', labelKey: 'nav.payroll', to: '/payroll/runs', icon: Wallet },
  { type: 'separator' },
  {
    type: 'group',
    labelKey: 'nav.configuration',
    items: [
      { type: 'link', labelKey: 'nav.configPenalties', to: '/config/penalties', icon: Percent },
      { type: 'link', labelKey: 'nav.configOvertime', to: '/config/overtime', icon: Timer },
      { type: 'link', labelKey: 'nav.configAbsenceRule', to: '/config/absence-rule', icon: UserX },
      { type: 'link', labelKey: 'nav.configHolidays', to: '/config/holidays', icon: CalendarDays },
      { type: 'link', labelKey: 'nav.configLeaveTypes', to: '/config/leave-types', icon: Tags },
    ],
  },
  { type: 'separator' },
  {
    type: 'group',
    labelKey: 'nav.settings',
    items: [
      { type: 'link', labelKey: 'nav.settingsUsers', to: '/settings/users', icon: UserCog },
      { type: 'link', labelKey: 'nav.settingsLicense', to: '/settings/license', icon: KeyRound },
      { type: 'link', labelKey: 'nav.settingsProfile', to: '/settings/profile', icon: UserCircle },
    ],
  },
];

// 2026-08-25: managers get total access (employees/shift-schedules/devices/
// payroll/config) for their own location — backend enforces the location
// scoping (see app/deps.py assert_location_access). Leave Types config
// stays admin-only (org-wide policy, not location-specific), same as
// Locations and User Accounts.
const managerNav: NavNode[] = [
  { type: 'link', labelKey: 'nav.dashboard', to: '/', icon: LayoutDashboard },
  { type: 'link', labelKey: 'nav.alerts', to: '/alerts', icon: AlertTriangle },
  { type: 'separator' },
  { type: 'link', labelKey: 'nav.employees', to: '/employees', icon: Users },
  { type: 'link', labelKey: 'nav.shiftSchedules', to: '/shift-schedules', icon: CalendarClock },
  { type: 'link', labelKey: 'nav.rota', to: '/rota', icon: CalendarRange },
  { type: 'link', labelKey: 'nav.devices', to: '/devices', icon: HardDrive },
  { type: 'separator' },
  {
    type: 'group',
    labelKey: 'nav.attendance',
    items: [
      { type: 'link', labelKey: 'nav.attendanceDaily', to: '/attendance', icon: ClipboardList },
      { type: 'link', labelKey: 'nav.attendanceLogs', to: '/attendance/logs', icon: FileClock },
    ],
  },
  { type: 'link', labelKey: 'nav.leave', to: '/leave', icon: CalendarCheck },
  { type: 'link', labelKey: 'nav.payroll', to: '/payroll/runs', icon: Wallet },
  { type: 'separator' },
  {
    type: 'group',
    labelKey: 'nav.configuration',
    items: [
      { type: 'link', labelKey: 'nav.configPenalties', to: '/config/penalties', icon: Percent },
      { type: 'link', labelKey: 'nav.configOvertime', to: '/config/overtime', icon: Timer },
      { type: 'link', labelKey: 'nav.configAbsenceRule', to: '/config/absence-rule', icon: UserX },
      { type: 'link', labelKey: 'nav.configHolidays', to: '/config/holidays', icon: CalendarDays },
    ],
  },
  { type: 'separator' },
  { type: 'link', labelKey: 'nav.settingsProfile', to: '/settings/profile', icon: UserCircle },
];

export function navForRole(user: CurrentUser): NavNode[] {
  return user.role === 'admin' ? adminNav : managerNav;
}
