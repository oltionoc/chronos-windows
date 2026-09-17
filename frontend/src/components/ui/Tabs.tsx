import clsx from 'clsx';

export interface TabItem {
  key: string;
  label: string;
}

interface TabsProps {
  tabs: TabItem[];
  active: string;
  onChange: (key: string) => void;
}

// Tabs — DESIGN_SPEC §6.16
export function Tabs({ tabs, active, onChange }: TabsProps) {
  return (
    <div className="border-b border-neutral-200">
      <nav className="flex overflow-x-auto">
        {tabs.map((tab) => {
          const isActive = tab.key === active;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => onChange(tab.key)}
              className={clsx(
                'mr-6 whitespace-nowrap border-b-2 px-1 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-neutral-500 hover:text-neutral-800'
              )}
            >
              {tab.label}
            </button>
          );
        })}
      </nav>
    </div>
  );
}
