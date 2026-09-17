import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Users, Plus, Upload } from 'lucide-react';
import { employeesApi, locationsApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { BulkImportModal } from '../../components/BulkImportModal';
import { FilterBar } from '../../components/ui/FilterBar';
import { SearchInput } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/Table';
import type { Column } from '../../components/ui/Table';
import { Pagination } from '../../components/ui/Table';
import { EmploymentStatusBadge } from '../../components/ui/Badge';
import { CodeChip } from '../../components/ui/CodeChip';
import { formatCurrency, formatDate } from '../../lib/format';
import type { Employee, EmploymentStatus } from '../../api/types';

const STATUS_VALUES: EmploymentStatus[] = ['active', 'inactive', 'terminated'];

export function EmployeeListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  usePageTitle(t('employees.title'));

  const [search, setSearch] = useState('');
  const [locationId, setLocationId] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const { data: locations } = useFetch(() => locationsApi.list(), []);

  const params = useMemo(
    () => ({
      search: search || undefined,
      location_id: locationId ? Number(locationId) : undefined,
      status: status || undefined,
      page,
      page_size: pageSize,
    }),
    [search, locationId, status, page, pageSize]
  );

  const { data, loading, reload } = useFetch(() => employeesApi.list(params), [JSON.stringify(params)]);
  const [importOpen, setImportOpen] = useState(false);

  const hasActiveFilters = !!(search || locationId || status);
  function clearFilters() {
    setSearch('');
    setLocationId('');
    setStatus('');
    setPage(1);
  }

  const columns: Column<Employee>[] = [
    { key: 'code', header: t('employees.code'), render: (e) => <CodeChip>{e.employee_code}</CodeChip> },
    {
      key: 'name',
      header: t('employees.name'),
      render: (e) => <span className="font-medium">{e.first_name} {e.last_name}</span>,
    },
    { key: 'jobTitle', header: t('employees.jobTitle'), render: (e) => e.job_title ?? '–' },
    { key: 'location', header: t('employees.location'), render: (e) => e.location_name ?? '–' },
    { key: 'hireDate', header: t('employees.hireDate'), render: (e) => <span className="font-mono">{formatDate(e.hire_date)}</span> },
    {
      key: 'salary',
      header: t('employees.baseSalary'),
      align: 'right',
      render: (e) => <span className="font-mono">{formatCurrency(e.base_salary_eur)}</span>,
    },
    { key: 'status', header: t('employees.status'), render: (e) => <EmploymentStatusBadge status={e.employment_status} /> },
    { key: 'manager', header: t('employees.manager'), render: (e) => e.manager_name || t('employees.noManager') },
  ];

  return (
    <div>
      <PageHeader
        title={t('employees.title')}
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" leftIcon={<Upload size={16} />} onClick={() => setImportOpen(true)}>
              {t('bulkImport.button')}
            </Button>
            <Button leftIcon={<Plus size={16} />} onClick={() => navigate('/employees/new')}>
              {t('employees.newEmployee')}
            </Button>
          </div>
        }
      />

      <BulkImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        resourceLabel={t('employees.title')}
        columns={['location_id', 'employee_code', 'first_name', 'last_name', 'national_id', 'job_title', 'hire_date', 'base_salary_eur', 'manager_user_id', 'employment_status']}
        onImport={(file) => employeesApi.bulkImport(file)}
        onDone={reload}
      />

      <div className="mb-4">
        <FilterBar hasActiveFilters={hasActiveFilters} onClearFilters={clearFilters}>
          <SearchInput
            value={search}
            onChange={(v) => {
              setSearch(v);
              setPage(1);
            }}
            placeholder={t('employees.searchPlaceholder')}
            className="w-64"
          />
          <Select
            value={locationId}
            onChange={(e) => {
              setLocationId(e.target.value);
              setPage(1);
            }}
            placeholder={t('common.all')}
            options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
            containerClassName="w-48"
            aria-label={t('employees.location')}
          />
          <Select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
            placeholder={t('common.all')}
            options={STATUS_VALUES.map((s) => ({ value: s, label: t(`status.employment.${s}`) }))}
            containerClassName="w-48"
            aria-label={t('employees.status')}
          />
        </FilterBar>
      </div>

      <DataTable
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(e) => e.id}
        loading={loading}
        onRowClick={(e) => navigate(`/employees/${e.id}`)}
        emptyIcon={<Users size={24} />}
        emptyMessage={t('employees.emptyMessage')}
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearFilters}
        mobileCard={(e) => ({
          title: `${e.first_name} ${e.last_name}`,
          subtitle: <CodeChip>{e.employee_code}</CodeChip>,
          badge: <EmploymentStatusBadge status={e.employment_status} />,
          rows: [
            { label: t('employees.jobTitle'), value: e.job_title ?? '–' },
            { label: t('employees.baseSalary'), value: <span className="font-mono">{formatCurrency(e.base_salary_eur)}</span> },
            { label: t('employees.hireDate'), value: <span className="font-mono">{formatDate(e.hire_date)}</span> },
            { label: t('employees.location'), value: e.location_name ?? '–' },
          ],
        })}
        footer={
          data && (
            <Pagination
              page={page}
              pageSize={pageSize}
              total={data.total}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setPage(1);
              }}
            />
          )
        }
      />
    </div>
  );
}
