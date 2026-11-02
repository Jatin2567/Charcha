import type { ReactNode } from 'react';
import { X, Check, ArrowUpRight, LoaderCircle } from 'lucide-react';
import { LANGUAGES, SCRIPTED_LANGUAGES, languageName } from '../types/domain';
import type { Language } from '../types/domain';
import { useEffect, useId, useRef } from 'react';
export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="brand" role="img" aria-label="Artha-Mesh">
      <span
        className="brand-mark"
        aria-hidden="true"
        style={{
          maskImage: `url("${import.meta.env.BASE_URL}artha-waveform.svg")`,
          WebkitMaskImage: `url("${import.meta.env.BASE_URL}artha-waveform.svg")`,
        }}
      />
      {!compact && (
        <span className="brand-wordmark" aria-hidden="true">
          Artha<span className="brand-light">-Mesh</span>
        </span>
      )}
    </span>
  );
}
export function LanguageSelect({
  value,
  onChange,
  id = 'language',
  label = 'I want to hear',
  scriptedOnly = false,
  disabled = false,
}: {
  value: Language;
  onChange: (l: Language) => void;
  id?: string;
  label?: string;
  scriptedOnly?: boolean;
  disabled?: boolean;
}) {
  const choices = scriptedOnly ? SCRIPTED_LANGUAGES : LANGUAGES;
  return (
    <label className="field" htmlFor={id}>
      <span>{label}</span>
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value as Language)}
      >
        {!choices.some((entry) => entry.code === value) && (
          <option value={value} disabled>
            {languageName(value)} · requires live setup
          </option>
        )}
        {choices.map((l) => (
          <option key={l.code} value={l.code}>
            {l.name} · {l.native}
          </option>
        ))}
      </select>
    </label>
  );
}
export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: 'green' | 'orange' | 'neutral' | 'dark';
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function ErrorNotice({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return message ? (
    <div className="notice error" role="alert">
      <span>{message}</span>
      {onDismiss && (
        <button className="icon-button" aria-label="Dismiss error" onClick={onDismiss}>
          <X size={16} />
        </button>
      )}
    </div>
  ) : null;
}
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={22} />
      {label}
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      className={`modal ${wide ? 'modal-wide' : ''}`}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="modal-heading">
        <h2 id={titleId}>{title}</h2>
        <button onClick={onClose} className="icon-button" aria-label="Close dialog">
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Toast({ message, onDone }: { message: string; onDone: () => void }) {
  const dismiss = useRef(onDone);
  useEffect(() => {
    dismiss.current = onDone;
  }, [onDone]);
  useEffect(() => {
    const t = setTimeout(() => dismiss.current(), 4500);
    return () => clearTimeout(t);
  }, [message]);
  return (
    <div className="toast" role="status">
      <Check size={17} />
      {message}
    </div>
  );
}
export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">{icon}</span>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function TextLink({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button className="text-link" onClick={onClick}>
      {children}
      <ArrowUpRight size={15} />
    </button>
  );
}
export function initials(name: string) {
  return (
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((s) => s[0] || '')
      .join('')
      .toUpperCase() || 'Y'
  );
}
export function Avatar({
  name,
  index = 0,
  large = false,
}: {
  name: string;
  index?: number;
  large?: boolean;
}) {
  return (
    <span className={`avatar avatar-${index % 4} ${large ? 'avatar-large' : ''}`}>
      {initials(name)}
    </span>
  );
}
export function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <label className="toggle-row">
      <span>
        <strong>{label}</strong>
        {description && <small>{description}</small>}
      </span>
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="toggle-track" aria-hidden="true" />
    </label>
  );
}
export function downloadJson(name: string, value: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }),
  );
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function downloadText(name: string, value: string) {
  const url = URL.createObjectURL(new Blob([value], { type: 'text/plain;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
