import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { devicesApi, locationsApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Modal, ConfirmDialog } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { ActiveBadge } from '../../components/ui/Badge';
import { CodeChip } from '../../components/ui/CodeChip';
import { formatDateTime, formatRelativeSync } from '../../lib/format';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import { KeyValueGridSkeleton } from '../../components/ui/Skeleton';
import { useAuth } from '../../auth/AuthContext';
import type { DeviceType } from '../../api/types';
import { DeviceUsersPanel } from './DeviceUsersPanel';

type TestState = 'idle' | 'checking' | 'reachable' | 'unreachable';
const DEVICE_TYPE_VALUES: DeviceType[] = ['zkteco', 'hikvision', 'hikvision_cloud'];

// /devices/:id (T2, no tabs) — DESIGN_SPEC §5.10
export function DeviceDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const { id } = useParams();
  const deviceId = Number(id);

  const { data: device, loading, reload } = useFetch(() => devicesApi.get(deviceId), [deviceId]);
  const { data: locations } = useFetch(() => locationsApi.list(), []);

  usePageTitle(device?.label ?? '…', [{ label: t('devices.title'), to: '/devices' }, { label: device?.label ?? '' }]);

  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [testState, setTestState] = useState<TestState>('idle');
  const [testDetail, setTestDetail] = useState<string | undefined>();
  const [syncPending, setSyncPending] = useState(false);

  // Edit modal form state
  const [label, setLabel] = useState('');
  const [locationId, setLocationId] = useState('');
  const [deviceType, setDeviceType] = useState<DeviceType>('zkteco');
  const [ipAddress, setIpAddress] = useState('');
  const [port, setPort] = useState(4370);
  const [serialNumber, setSerialNumber] = useState('');
  const [authUsername, setAuthUsername] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const isCloud = deviceType === 'hikvision_cloud';

  function openEdit() {
    if (!device) return;
    setLabel(device.label);
    setLocationId(String(device.location_id));
    setDeviceType(device.device_type);
    setIpAddress(device.ip_address);
    setPort(device.port);
    setSerialNumber(device.serial_number ?? '');
    setAuthUsername(device.auth_username ?? '');
    setAuthPassword('');
    setEditOpen(true);
  }

  async function handleEditSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await devicesApi.update(deviceId, {
        label,
        location_id: Number(locationId),
        device_type: deviceType,
        ip_address: ipAddress,
        port,
        serial_number: serialNumber || null,
        ...(deviceType !== 'zkteco'
          ? { auth_username: authUsername || null, ...(authPassword ? { auth_password: authPassword } : {}) }
          : {}),
      });
      showToast('success', t('toast.saved'));
      setEditOpen(false);
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      await devicesApi.remove(deviceId);
      showToast('success', t('toast.deleted'));
      navigate('/devices');
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
      setDeleting(false);
    }
  }

  async function handleTestConnection() {
    setTestState('checking');
    setTestDetail(undefined);
    try {
      const result = await devicesApi.testConnection(deviceId);
      setTestState(result.reachable ? 'reachable' : 'unreachable');
      setTestDetail(result.detail);
      reload();
    } catch (err) {
      setTestState('unreachable');
      setTestDetail(err instanceof ApiError ? err.message : undefined);
    }
  }

  async function handleSync() {
    setSyncPending(true);
    try {
      await devicesApi.sync(deviceId);
      showToast('info', t('devices.syncStarted'));
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSyncPending(false);
    }
  }

  if (loading || !device) {
    return (
      <div>
        <PageHeader title="…" />
        <Card>
          <KeyValueGridSkeleton rows={4} />
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={
          <span className="flex items-center gap-3">
            {device.label}
            <ActiveBadge active={device.is_active} />
          </span>
        }
        actions={
          <>
            <Button variant="secondary" onClick={openEdit}>{t('common.edit')}</Button>
            <Button variant="danger" onClick={() => setDeleteOpen(true)}>{t('common.delete')}</Button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title={t('devices.connectionSection')}>
          <dl className="mb-5 grid grid-cols-1 gap-4">
            <div>
              <dt className="text-caption text-neutral-500">{t('devices.deviceType')}</dt>
              <dd className="text-body text-neutral-800">{t(`devices.deviceTypes.${device.device_type}`)}</dd>
            </div>
            <div>
              <dt className="text-caption text-neutral-500">{t('devices.ipPort')}</dt>
              <dd className="text-body text-neutral-800"><CodeChip>{device.ip_address}:{device.port}</CodeChip></dd>
            </div>
            <div>
              <dt className="text-caption text-neutral-500">{t('devices.serialNumber')}</dt>
              <dd className="text-body text-neutral-800">
                {device.serial_number ? <CodeChip>{device.serial_number}</CodeChip> : '–'}
              </dd>
            </div>
            <div>
              <dt className="text-caption text-neutral-500">{t('devices.lastSynced')}</dt>
              <dd className="font-mono text-body text-neutral-800">
                {device.last_synced_at ? formatDateTime(device.last_synced_at) : t('common.never')}
              </dd>
              {device.last_synced_at && (
                <dd className="font-mono text-caption text-neutral-500">{formatRelativeSync(device.last_synced_at, t)}</dd>
              )}
            </div>
            <div>
              <dt className="text-caption text-neutral-500">{t('devices.clockSkew')}</dt>
              <dd
                className={`text-body ${
                  device.clock_skew_seconds !== null && Math.abs(device.clock_skew_seconds) > 120
                    ? 'font-medium text-danger-700'
                    : 'text-neutral-800'
                }`}
              >
                {device.clock_skew_seconds === null
                  ? t('devices.clockSkewUnknown')
                  : Math.abs(device.clock_skew_seconds) <= 120
                    ? t('devices.clockSkewOk')
                    : t('devices.clockSkewOff', { minutes: Math.abs(Math.round(device.clock_skew_seconds / 60)) })}
              </dd>
              {device.clock_checked_at && (
                <dd className="font-mono text-caption text-neutral-500">{formatDateTime(device.clock_checked_at)}</dd>
              )}
            </div>
          </dl>
          {/* Both live here together: testing the connection is also what
              measures the device clock, and syncing is the other thing
              anyone standing in front of a device wants to do. */}
          <div className="flex flex-wrap gap-3">
            <Button onClick={handleTestConnection} loading={testState === 'checking'}>
              {t('common.testConnection')}
            </Button>
            <div title={syncPending ? t('devices.syncInProgress') : undefined}>
              <Button variant="secondary" onClick={handleSync} loading={syncPending} disabled={syncPending}>
                {t('common.syncNow')}
              </Button>
            </div>
          </div>
          {testState !== 'idle' && testState !== 'checking' && (
            <div className={`mt-3 rounded-md px-3 py-2 text-sm ${testState === 'reachable' ? 'bg-success-50 text-success-700' : 'bg-danger-50 text-danger-700'}`}>
              {testState === 'reachable' ? t('common.reachable') : t('common.unreachable')}
              {testDetail && <div className="mt-0.5 text-caption">{testDetail}</div>}
            </div>
          )}
        </Card>

        {device.device_type !== 'hikvision_cloud' && (
          <DeviceUsersPanel deviceId={deviceId} locationId={device.location_id} isAdmin={isAdmin} />
        )}
      </div>

      <Modal open={editOpen} onClose={() => setEditOpen(false)} title={t('common.edit')}>
        <form onSubmit={handleEditSubmit} className="flex flex-col gap-5">
          <Input label={t('devices.label')} required value={label} onChange={(e) => setLabel(e.target.value)} />
          <Select
            label={t('devices.location')}
            required
            placeholder={t('common.select')}
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
            options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
          />
          <Select
            label={t('devices.deviceType')}
            required
            value={deviceType}
            onChange={(e) => setDeviceType(e.target.value as DeviceType)}
            options={DEVICE_TYPE_VALUES.map((v) => ({ value: v, label: t(`devices.deviceTypes.${v}`) }))}
          />
          <Input
            label={isCloud ? t('devices.cloudHost') : t('devices.ipAddress')}
            required
            value={ipAddress}
            onChange={(e) => setIpAddress(e.target.value)}
            hint={isCloud ? t('devices.cloudHostHint') : t('devices.ipAddressHint')}
          />
          <Input label={t('devices.port')} type="number" value={port} onChange={(e) => setPort(Number(e.target.value))} />
          <Input
            label={t('devices.serialNumber')}
            required={isCloud}
            value={serialNumber}
            onChange={(e) => setSerialNumber(e.target.value)}
            hint={isCloud ? t('devices.serialNumberCloudHint') : undefined}
          />
          {deviceType !== 'zkteco' && (
            <>
              <Input
                label={isCloud ? t('devices.appKey') : t('devices.authUsername')}
                value={authUsername}
                onChange={(e) => setAuthUsername(e.target.value)}
              />
              <Input
                label={`${isCloud ? t('devices.appSecret') : t('devices.authPassword')} (${t('common.optional')})`}
                type="password"
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                hint={t('devices.authPasswordHint')}
              />
            </>
          )}
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setEditOpen(false)}>{t('common.cancel')}</Button>
            <Button type="submit" loading={submitting}>{t('common.save')}</Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onConfirm={handleDelete}
        title={t('common.delete')}
        description={t('devices.deleteWarning')}
        loading={deleting}
        destructive
      />
    </div>
  );
}
