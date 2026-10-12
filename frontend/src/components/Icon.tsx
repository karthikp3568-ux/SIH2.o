/**
 * Inline stroke icons.
 *
 * Kept in-repo rather than pulled from a package so the app keeps working
 * fully offline and ships only the glyphs it uses. Every icon is decorative
 * (aria-hidden) — meaning is always carried by adjacent text.
 */

const PATHS: Record<string, string> = {
  mic: 'M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z M19 10v2a7 7 0 0 1-14 0v-2 M12 19v3',
  keyboard:
    'M3 6h18a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z M6 10h.01 M10 10h.01 M14 10h.01 M18 10h.01 M7 14h10',
  globe: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z M2 12h20 M12 2a15 15 0 0 1 0 20 M12 2a15 15 0 0 0 0 20',
  user: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2 M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
  users:
    'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z M22 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75',
  check: 'M20 6 9 17l-5-5',
  checkCircle: 'M22 11.08V12a10 10 0 1 1-5.93-9.14 M22 4 12 14.01l-3-3',
  circle: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z',
  dot: 'M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z',
  arrowRight: 'M5 12h14 M12 5l7 7-7 7',
  arrowLeft: 'M19 12H5 M12 19l-7-7 7-7',
  arrowUp: 'M12 19V5 M5 12l7-7 7 7',
  arrowDown: 'M12 5v14 M19 12l-7 7-7-7',
  chevronRight: 'M9 18l6-6-6-6',
  chevronDown: 'M6 9l6 6 6-6',
  pin: 'M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z M12 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  route:
    'M6 19a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M18 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M9 16h5.5a3.5 3.5 0 0 0 0-7H9.5a3.5 3.5 0 0 1 0-7H15',
  cap: 'M22 10 12 5 2 10l10 5 10-5Z M6 12v5c3 3 9 3 12 0v-5',
  briefcase:
    'M20 7H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2Z M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16',
  store:
    'M3 9l1.5-5h15L21 9 M3 9v11h18V9 M3 9a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0 M9 20v-6h6v6',
  wrench:
    'M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76Z',
  sprout:
    'M7 20h10 M10 20c5.5-2.5.8-6.4 3-10 M9.5 9.4c1.1.8 1.8 2.2 2.3 3.7-2 .4-3.5.4-4.8-.3-1.2-.6-2.3-1.9-3-4.2 2.8-.5 4.4 0 5.5.8Z M14.1 6a7 7 0 0 0-1.1 4c1.9-.1 3.3-.6 4.3-1.4 1-1 1.6-2.3 1.7-4.6-2.7.1-4 1-4.9 2Z',
  home: 'M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1v-9.5Z',
  bus: 'M8 6v6 M16 6v6 M3 12h18 M5 18h14a2 2 0 0 0 2-2V6a3 3 0 0 0-3-3H6a3 3 0 0 0-3 3v10a2 2 0 0 0 2 2Z M7 18v3 M17 18v3',
  train:
    'M8 3h8a4 4 0 0 1 4 4v8a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V7a4 4 0 0 1 4-4Z M4 11h16 M12 3v8 M8 22l2-4 M16 22l-2-4',
  target: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z M12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12Z M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z M12 16v-4 M12 8h.01',
  alert: 'M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z M12 9v4 M12 17h.01',
  shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z M9 12l2 2 4-4',
  clock: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z M12 6v6l4 2',
  x: 'M18 6 6 18 M6 6l12 12',
  xCircle: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z M15 9l-6 6 M9 9l6 6',
  edit: 'M12 20h9 M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z',
  compare: 'M16 3h5v5 M8 3H3v5 M21 3l-7 7 M3 3l7 7 M16 21h5v-5 M8 21H3v-5 M21 21l-7-7 M3 21l7-7',
  columns: 'M4 4h6v16H4z M14 4h6v16h-6z',
  map: 'M1 6v16l7-4 8 4 7-4V2l-7 4-8-4-7 4Z M8 2v16 M16 6v16',
  list: 'M8 6h13 M8 12h13 M8 18h13 M3 6h.01 M3 12h.01 M3 18h.01',
  chart: 'M3 3v18h18 M7 16v-4 M12 16V8 M17 16v-7',
  file: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8',
  inbox: 'M22 12h-6l-2 3h-4l-2-3H2 M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z',
  refresh: 'M3 12a9 9 0 0 1 15-6.7L21 8 M21 3v5h-5 M21 12a9 9 0 0 1-15 6.7L3 16 M3 21v-5h5',
  power: 'M18.36 6.64a9 9 0 1 1-12.73 0 M12 2v10',
  send: 'M22 2 11 13 M22 2l-7 20-4-9-9-4 20-7Z',
  volume: 'M11 5 6 9H2v6h4l5 4V5Z M15.54 8.46a5 5 0 0 1 0 7.07 M19.07 4.93a10 10 0 0 1 0 14.14',
  volumeOff: 'M11 5 6 9H2v6h4l5 4V5Z M23 9l-6 6 M17 9l6 6',
  stop: 'M6 6h12v12H6z',
  play: 'M6 4l14 8-14 8V4Z',
  compass: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z M16.24 7.76l-2.12 6.36-6.36 2.12 2.12-6.36 6.36-2.12Z',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z M21 21l-4.35-4.35',
  plus: 'M12 5v14 M5 12h14',
  logout: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4 M16 17l5-5-5-5 M21 12H9',
  flag: 'M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z M4 22v-7',
  book: 'M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z',
  trending: 'M23 6l-9.5 9.5-5-5L1 18 M17 6h6v6',
  activity: 'M22 12h-4l-3 9L9 3l-3 9H2',
  layers: 'M12 2 2 7l10 5 10-5-10-5Z M2 17l10 5 10-5 M2 12l10 5 10-5',
  graph:
    'M12 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M5 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M19 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M12 8v4 M12 12l-5.5 4.5 M12 12l5.5 4.5',
  smile: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z M8 14s1.5 2 4 2 4-2 4-2 M9 9h.01 M15 9h.01',
  meh: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z M8 15h8 M9 9h.01 M15 9h.01',
  frown: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z M16 16s-1.5-2-4-2-4 2-4 2 M9 9h.01 M15 9h.01',
  lock: 'M19 11H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2Z M7 11V7a5 5 0 0 1 10 0v4',
  eye: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12Z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  sparkle: 'M12 3l1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2L12 3Z',
  gauge: 'M12 14l4-4 M3.34 19a10 10 0 1 1 17.32 0',
  hammer: 'M15 12l-8.5 8.5a2.12 2.12 0 0 1-3-3L12 9 M17.64 15 22 10.64 M20.91 11.7l-1.25-1.25a2 2 0 0 1-.6-1.44V7.86L16.2 5a5.5 5.5 0 0 0-7.78 0L8 5.4l4 4 3-3',
  undo: 'M3 7v6h6 M21 17a9 9 0 0 0-15-6.7L3 13',
}

export type IconName = keyof typeof PATHS

export function Icon({
  name,
  size = 20,
  strokeWidth = 2,
  className,
  style,
}: {
  name: IconName | string
  size?: number
  strokeWidth?: number
  className?: string
  style?: React.CSSProperties
}) {
  const d = PATHS[name] ?? PATHS.dot
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
      style={style}
    >
      {d.split(' M').map((segment, index) => (
        <path key={index} d={index === 0 ? segment : `M${segment}`} />
      ))}
    </svg>
  )
}

/** Opportunity type → icon + plain-language label. */
export const OPPORTUNITY_TYPE: Record<string, { icon: IconName; label: string }> = {
  training: { icon: 'cap', label: 'Training' },
  apprenticeship: { icon: 'hammer', label: 'Apprenticeship' },
  job: { icon: 'briefcase', label: 'Job' },
  enterprise: { icon: 'store', label: 'Own enterprise' },
  self_employment: { icon: 'store', label: 'Self-employment' },
}
