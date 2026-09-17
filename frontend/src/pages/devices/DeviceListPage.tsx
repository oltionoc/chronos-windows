import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { HardDrive, Plus } from 'lucide-react';
import { devicesApi, locationsApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { FilterBar } from '../../components/ui/FilterBar';
import { SearchInput } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/Table';
import type { Column } from '../../components/ui/Table';
import { ActiveBadge } from '../../components/ui/Badge';
import { CodeChip } from '../../components/ui/CodeChip';
import { formatRelativeSync } from '../../lib/format';
import type { Device } from '../../api/types';

// /devices (T1) — DESIGN_SPEC §5.8
export function DeviceListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  usePageTitle(t('devices.title'));

  const [locationId, setLocationId] = useState('');
  const [isActive, setIsActive] = useState('');
  const [search, setSearch] = useState('');
  const { data: locations } = useFetch(() => locationsApi.list(), []);
  const params = useMemo(
    () => ({
      location_id: locationId ? Number(locationId) : undefined,
      is_active: isActive ? isActive === 'true' : undefined,
      search: search || undefined,
    }),
    [locationId, isActive, search]
  );
  const { data, loading } = useFetch(() => devicesApi.list(params), [JSON.stringify(params)]);
  const hasActiveFilters = !!(locationId || isActive || search);
  function clearFilters() {
    setLocationId('');
    setIsActive('');
    setSearch('');
  }

  const columns: Column<Device>[] = [
    { key: 'label', header: t('devices.label'), render: (d) => <span className="font-medium">{d.label}</span> },
    { key: 'location', header: t('devices.location'), render: (d) => d.location_name ?? '–' },
    { key: 'deviceType', header: t('devices.deviceType'), render: (d) => t(`devices.deviceTypes.${d.device_type}`) },
    { key: 'ip', header: t('devices.ipPort'), render: (d) => <CodeChip>{d.ip_address}:{d.port}</CodeChip> },
    { key: 'serial', header: t('devices.serialNumber'), render: (d) => (d.serial_number ? <CodeChip>{d.serial_number}</CodeChip> : '–') },
    {
      key: 'status',
      header: t('devices.status'),
      render: (d) => <ActiveBadge active={d.is_active} />,
    },
    { key: 'lastSynced', header: t('devices.lastSynced'), render: (d) => <span className="font-mono">{formatRelativeSync(d.last_synced_at, t)}</span> },
  ];

  return (
    <div>
      <PageHeader
        title={t('devices.title')}
        actions={
          <Button leftIcon={<Plus size={16} />} onClick={() => navigate('/devices/new')}>
            {t('devices.newDevice')}
          </Button>
        }
      />

      <div className="mb-4">
        <FilterBar hasActiveFilters={hasActiveFilters} onClearFilters={clearFilters}>
          <SearchInput value={search} onChange={setSearch} placeholder={t('common.search')} className="w-56" />
          <Select
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
            placeholder={t('common.all')}
            options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
            containerClassName="w-48"
            aria-label={t('devices.location')}
          />
          <Select
            value={isActive}
            onChange={(e) => setIsActive(e.target.value)}
            placeholder={t('common.all')}
            options={[
              { value: 'true', label: t('common.active') },
              { value: 'false', label: t('common.inactive') },
            ]}
            containerClassName="w-40"
            aria-label={t('devices.status')}
          />
        </FilterBar>
      </div>

      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(d) => d.id}
        loading={loading}
        onRowClick={(d) => navigate(`/devices/${d.id}`)}
        emptyIcon={<HardDrive size={24} />}
        emptyMessage={t('devices.emptyMessage')}
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearFilters}
        mobileCard={(d) => ({
          title: d.label,
          subtitle: <CodeChip>{d.ip_address}:{d.port}</CodeChip>,
          badge: <ActiveBadge active={d.is_active} />,
          rows: [
            { label: t('devices.deviceType'), value: t(`devices.deviceTypes.${d.device_type}`) },
            { label: t('devices.location'), value: d.location_name ?? '–' },
            { label: t('devices.lastSynced'), value: <span className="font-mono">{formatRelativeSync(d.last_synced_at, t)}</span> },
          ],
        })}
      />
    </div>
  );
}
