const icons = {
  logo: (
    <>
      <defs>
        <mask id="logo-bite">
          <rect width="24" height="24" fill="#fff" />
          <circle cx="17" cy="12.5" r="3.1" fill="#000" />
        </mask>
      </defs>
      <g mask="url(#logo-bite)">
        <path
          d="M12 7.2 C 10.5 5.9 8.5 5.7 7.2 6.7 C 6 7.7 5.5 9.8 5.5 11.6 C 5.5 15 7.6 18.2 12 18.2 C 16.4 18.2 18.5 15 18.5 11.6 C 18.5 9.8 18 7.7 16.8 6.7 C 16.2 6.2 15.5 6.1 14.8 6.2 Z"
          fill="currentColor"
        />
      </g>
      <path
        d="M12 7.2 C 11.9 6 11.7 4.8 11 3.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M7.1 4.9 C 6.4 3.7 6.7 2.2 8.1 1.9 C 8.2 3 8 4 7.1 4.9 Z"
        fill="currentColor"
      />
    </>
  ),
  pancakes: (
    <>
      <ellipse cx="12" cy="9" rx="7" ry="2.2" />
      <ellipse cx="12" cy="12.6" rx="7.5" ry="2.2" />
      <ellipse cx="12" cy="16.2" rx="7" ry="2.2" />
      <path d="M12 6.8 C 11 5.4 11.5 4 13 3.4" />
    </>
  ),
  shakshuka: (
    <>
      <circle cx="9.5" cy="13.5" r="5.2" />
      <path d="M14.8 11.5 L21 9.6" />
      <circle cx="9.5" cy="13.5" r="2.3" />
      <circle cx="9.5" cy="13.5" r="1" fill="currentColor" stroke="none" />
    </>
  ),
  fish: (
    <>
      <path d="M3 12 C 4 8 9 7 13 9 L 19 6.5 C 17.5 10.5 17.5 13.5 19 17.5 L 13 15 C 9 17 4 16 3 12 Z" />
      <path d="M9 9.6 C 10.5 10.8 12 10.8 13.5 9.6" />
      <circle cx="6.2" cy="10.6" r="0.5" fill="currentColor" stroke="none" />
    </>
  ),
  stirfry: (
    <>
      <path d="M4 13 H20" />
      <path d="M4 13 A 8 8 0 0 0 20 13" />
      <path d="M20 11 L23.5 9.5" />
      <path d="M9 8 C 10 10.2 13 10.2 15 8.8" />
      <path d="M11 5 C 12 7.2 15 7.2 17 5.8" />
    </>
  ),
  salad: (
    <>
      <path d="M4 12 H20" />
      <path d="M4 12 A 8 8 0 0 0 20 12" />
      <path d="M12 6.5 V4" />
      <path d="M8 9 C 9.5 7.2 10.8 6.5 12 6.5" />
      <path d="M16 9 C 14.5 7.2 13.2 6.5 12 6.5" />
    </>
  ),
  rice: (
    <>
      <path d="M4 12 H20" />
      <path d="M4 12 A 8 8 0 0 0 20 12" />
      <path d="M8 9.5 C 9 8.4 10.5 8.4 11.5 9.5 C 12.5 10.6 14 10.6 15 9.5 C 16 8.4 16.8 9 17 9.5" />
    </>
  ),
  smoothie: (
    <>
      <path d="M7 8 L 8.5 19 H 15.5 L 17 8 Z" />
      <path d="M7 8 H 17" />
      <path d="M15 8 C 15 5.4 14 3.6 12.4 2.8" />
      <path d="M12.4 2.8 L 12.8 1.6" />
      <path d="M10 12.5 C 11.5 11.3 13.5 13.2 15 12" />
    </>
  ),
  noodles: (
    <>
      <path d="M4 12 H20" />
      <path d="M4 12 A 8 8 0 0 0 20 12" />
      <path d="M9 9.6 C 10 10.6 11 9.2 12 9.8 C 13 10.4 14 9 15 9.6" />
      <path d="M10.4 11.2 C 11.4 12.2 12.6 10.8 13.6 11.4" />
    </>
  ),
  bowl: (
    <>
      <path d="M4 12 H20" />
      <path d="M4 12 A 8 8 0 0 0 20 12" />
      <path d="M8.5 9 C 10.5 6.6 13.5 6.6 15.5 9" />
      <path d="M10 4.2 C 10.6 5.2 11.6 5.2 12.2 4.2 C 12.8 5.2 13.8 5.2 14.4 4.2" />
    </>
  ),
  jar: (
    <>
      <path d="M7 6 H17 V19 H7 Z" />
      <path d="M8 3.5 H16 V6 H8 Z" />
      <circle cx="10.5" cy="10" r="1" fill="currentColor" stroke="none" />
      <circle cx="13.6" cy="12.2" r="1" fill="currentColor" stroke="none" />
      <circle cx="11.4" cy="14.5" r="1" fill="currentColor" stroke="none" />
      <path d="M12 6 V8.5" />
    </>
  ),
}

export default function RecipeIcon({ name, className = '' }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {icons[name]}
    </svg>
  )
}
