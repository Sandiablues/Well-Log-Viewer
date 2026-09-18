import type { ReactNode } from 'react';

interface ManagedDataPageHeaderProps {
  title: string;
  subtitle: string;
  actions?: ReactNode;
}

export function ManagedDataPageHeader({ title, subtitle, actions }: ManagedDataPageHeaderProps) {
  return (
    <header className="mv-managed-page-header">
      <div className="mv-managed-page-header__copy">
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      {actions ? <div className="mv-managed-page-header__actions">{actions}</div> : null}
    </header>
  );
}
