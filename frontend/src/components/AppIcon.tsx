const paths = {
  feather: 'M20 12a6 6 0 0 0-8-8L3 13v8h8Z M16 8 2 22 M9 15H3 M14 10h7',
  home: 'm3 10 9-7 9 7 M5 9v12h5v-7h4v7h5V9',
  inbox: 'M4 4h16v16H4Z M4 13h5l2 3h2l2-3h5',
  history: 'M3 11a9 9 0 1 1 2 7 M3 4v7h7 M12 7v5l3 2',
  note: 'M14 3H5v18h14V10 M14 3v7h5 M8 14h8 M8 17h5',
  check: 'm5 12 4 4L19 6',
  message: 'M4 4h16v13H9l-5 4V4 M8 8h8 M8 12h5',
  users: 'M16 21v-3a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v3 M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M17 4a4 4 0 0 1 0 7 M22 21v-3a4 4 0 0 0-3-4',
  shield: 'M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6Z m-5 10 3 3 7-7',
  settings: 'M4 6h16 M4 12h16 M4 18h16 M8 3v6 M16 9v6 M10 15v6',
  bell: 'M4 17h16l-2-3V8a6 6 0 0 0-12 0v6Z M10 21h4',
  upload: 'M4 16v5h16v-5 M12 16V3 m-5 5 5-5 5 5',
  plus: 'M12 5v14 M5 12h14',
  scan: 'M8 3H3v5 M16 3h5v5 M3 16v5h5 M21 16v5h-5 M7 12h10',
  flask: 'M9 3h6 M10 3v7L4 20v1h16v-1l-6-10V3 M7 16h10',
  logout: 'M9 3H4v18h5 M9 12h12 m-5-5 5 5-5 5',
  left: 'm15 5-7 7 7 7',
  right: 'm9 5 7 7-7 7',
  close: 'm6 6 12 12 M6 18 18 6',
  menu: 'M4 6h16 M4 12h16 M4 18h16',
} as const;

export type IconName = keyof typeof paths;

/** Shared decorative line icons; the enclosing control supplies its accessible name. */
export default function AppIcon({ name }: { name: IconName }) {
  return <svg className="ui-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={paths[name]} /></svg>;
}
