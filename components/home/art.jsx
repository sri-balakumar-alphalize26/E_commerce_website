/* Placeholder product illustrations — used only when an item has no `image`.
   viewBox 120x100, each drawn around the centre. `c` = product colour. */

const Pack = ({ c = "#1f7a4c", t = "", c2 = "#fff" }) => (
  <g>
    <ellipse cx="60" cy="92" rx="30" ry="4" fill="#000" opacity=".08" />
    <path d="M36 18h48l-2 6 2 6v54a6 6 0 0 1-6 6H40a6 6 0 0 1-6-6V30l2-6z" fill={c} />
    <path d="M36 18h48l-2 6 2 6H34l2-6z" fill="#000" opacity=".15" />
    <path d="M38 22h44" stroke="#fff" strokeOpacity=".35" strokeDasharray="3 3" />
    <rect x="40" y="42" width="40" height="30" rx="4" fill={c2} opacity=".95" />
    <text x="60" y="62" textAnchor="middle" fontSize="13" fontWeight="800" fill={c}>{t}</text>
    <path d="M42 34h8" stroke="#fff" strokeOpacity=".6" strokeWidth="3" strokeLinecap="round" />
  </g>
);

const Bottle = ({ c = "#d4a017", t = "" }) => (
  <g>
    <ellipse cx="60" cy="93" rx="20" ry="3.5" fill="#000" opacity=".08" />
    <rect x="53" y="6" width="14" height="10" rx="2" fill="#2b3a42" />
    <path d="M52 16h16v8c8 4 12 10 12 18v42a7 7 0 0 1-7 7H47a7 7 0 0 1-7-7V42c0-8 4-14 12-18z" fill={c} opacity=".9" />
    <path d="M46 36c0 0 2-6 8-9v58h-4a4 4 0 0 1-4-4z" fill="#fff" opacity=".25" />
    <rect x="42" y="50" width="36" height="24" rx="3" fill="#fff" />
    <text x="60" y="66" textAnchor="middle" fontSize="11" fontWeight="800" fill="#2b3a42">{t}</text>
  </g>
);

const Box = ({ c = "#8a4b2a", t = "" }) => (
  <g>
    <ellipse cx="60" cy="92" rx="36" ry="4" fill="#000" opacity=".08" />
    <path d="M26 34l34-12 34 12-34 12z" fill={c} />
    <path d="M26 34l34 12v42L26 76z" fill={c} opacity=".78" />
    <path d="M94 34L60 46v42l34-12z" fill={c} opacity=".92" />
    <path d="M26 34l34 12 34-12" stroke="#fff" strokeOpacity=".3" fill="none" />
    <path d="M65 58l24-8.5v18L65 76z" fill="#fff" opacity=".92" />
    <path d="M69 64l16-5.6M69 69l11-3.8" stroke={c} strokeWidth="2.4" strokeLinecap="round" />
  </g>
);

const Jar = ({ c = "#e59aa8", t = "" }) => (
  <g>
    <ellipse cx="60" cy="93" rx="24" ry="3.5" fill="#000" opacity=".08" />
    <rect x="40" y="14" width="40" height="12" rx="3" fill="#39434b" />
    <rect x="36" y="26" width="48" height="64" rx="10" fill={c} />
    <rect x="42" y="30" width="6" height="52" rx="3" fill="#fff" opacity=".35" />
    <rect x="40" y="48" width="40" height="22" rx="3" fill="#fff" />
    <text x="60" y="63" textAnchor="middle" fontSize="11" fontWeight="800" fill="#39434b">{t}</text>
  </g>
);

const Bar = ({ c = "#5a2e1c", t = "" }) => (
  <g>
    <ellipse cx="60" cy="90" rx="36" ry="4" fill="#000" opacity=".08" />
    <g transform="rotate(-12 60 55)">
      <rect x="24" y="30" width="72" height="50" rx="4" fill={c} />
      <path d="M24 30h30l-8 50H24z" fill="#3a1d11" opacity=".5" />
      <rect x="50" y="42" width="40" height="26" rx="3" fill="#f3d9a6" />
      <text x="70" y="59" textAnchor="middle" fontSize="11" fontWeight="800" fill={c}>{t}</text>
    </g>
  </g>
);

const Banana = () => (
  <g>
    <ellipse cx="60" cy="90" rx="38" ry="4" fill="#000" opacity=".08" />
    {[0, 1, 2].map((i) => (
      <g key={i} transform={`rotate(${-18 + i * 18} 72 30)`}>
        <path d="M70 28c-26 6-42 26-40 52 8-18 24-34 46-44z" fill={["#f6c945", "#f2bd2c", "#fad35c"][i]} />
        <path d="M30 80c2-3 3-4 5-6" stroke="#6b4b12" strokeWidth="3" strokeLinecap="round" />
      </g>
    ))}
    <rect x="68" y="22" width="10" height="12" rx="3" fill="#6f7d2c" />
  </g>
);

const Apple = ({ c = "#d8262e" }) => (
  <g>
    <ellipse cx="60" cy="90" rx="30" ry="4" fill="#000" opacity=".08" />
    <path d="M60 34c-6-6-28-6-30 16-2 22 12 38 22 38 4 0 6-2 8-2s4 2 8 2c10 0 24-16 22-38-2-22-24-22-30-16z" fill={c} />
    <path d="M40 46c2-8 10-10 14-8-6 2-10 8-10 14z" fill="#fff" opacity=".35" />
    <path d="M60 34c0-8 2-12 6-16" stroke="#5a3a1a" strokeWidth="3" strokeLinecap="round" fill="none" />
    <path d="M64 24c8-8 18-6 20-4-6 6-14 8-20 4z" fill="#4c9a2a" />
  </g>
);

const Pomegranate = () => (
  <g>
    <ellipse cx="60" cy="91" rx="30" ry="4" fill="#000" opacity=".08" />
    <circle cx="60" cy="58" r="30" fill="#b3122b" />
    <path d="M52 30l3-10 5 7 5-7 3 10z" fill="#8e0e22" />
    <circle cx="48" cy="48" r="7" fill="#fff" opacity=".18" />
  </g>
);

const Orange = () => (
  <g>
    <ellipse cx="60" cy="91" rx="30" ry="4" fill="#000" opacity=".08" />
    <circle cx="60" cy="58" r="30" fill="#f28c1b" />
    {[[48, 50], [66, 44], [72, 62], [54, 70], [44, 62], [60, 58]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="1.3" fill="#c96a0c" />)}
    <path d="M58 28c6-8 16-8 20-6-6 6-14 8-20 6z" fill="#3f8e2e" />
    <circle cx="48" cy="46" r="7" fill="#fff" opacity=".2" />
  </g>
);

const Grapes = () => (
  <g>
    <ellipse cx="60" cy="92" rx="22" ry="3.5" fill="#000" opacity=".08" />
    <path d="M60 14v12" stroke="#6b4b12" strokeWidth="3" strokeLinecap="round" />
    <path d="M62 20c8-6 16-4 18-2-6 4-12 6-18 2z" fill="#4c9a2a" />
    {[[48, 34], [60, 32], [72, 34], [42, 46], [54, 46], [66, 46], [78, 46], [48, 58], [60, 58], [72, 58], [54, 70], [66, 70], [60, 82]].map(([x, y], i) => (
      <circle key={i} cx={x} cy={y} r="8" fill={i % 3 ? "#9cc63b" : "#88b62f"} stroke="#fff" strokeOpacity=".25" />
    ))}
  </g>
);

const Headphones = ({ c = "#1b3a55" }) => (
  <g>
    <ellipse cx="60" cy="92" rx="34" ry="4" fill="#000" opacity=".08" />
    <path d="M30 62V52a30 30 0 0 1 60 0v10" stroke={c} strokeWidth="7" fill="none" strokeLinecap="round" />
    <rect x="22" y="56" width="18" height="32" rx="8" fill={c} />
    <rect x="80" y="56" width="18" height="32" rx="8" fill={c} />
    <rect x="26" y="62" width="4" height="20" rx="2" fill="#fff" opacity=".25" />
  </g>
);

const Speaker = ({ c = "#0f6a9c" }) => (
  <g>
    <ellipse cx="60" cy="92" rx="36" ry="4" fill="#000" opacity=".08" />
    <rect x="22" y="36" width="76" height="50" rx="22" fill={c} />
    <rect x="30" y="44" width="60" height="34" rx="16" fill="#0b2a3c" opacity=".35" />
    {[0, 1, 2, 3, 4, 5, 6].map((i) => <circle key={i} cx={38 + i * 7.5} cy={61} r="2.2" fill="#fff" opacity=".45" />)}
    <rect x="52" y="30" width="16" height="6" rx="3" fill={c} />
  </g>
);

const Charger = () => (
  <g>
    <ellipse cx="60" cy="92" rx="26" ry="4" fill="#000" opacity=".08" />
    <rect x="50" y="14" width="5" height="16" rx="1.5" fill="#9aa6ae" />
    <rect x="65" y="14" width="5" height="16" rx="1.5" fill="#9aa6ae" />
    <rect x="36" y="28" width="48" height="60" rx="12" fill="#f4f6f8" stroke="#d3dbe1" strokeWidth="2" />
    <rect x="50" y="62" width="20" height="6" rx="3" fill="#2b3a42" />
    <rect x="50" y="74" width="20" height="6" rx="3" fill="#2b3a42" />
    <text x="60" y="52" textAnchor="middle" fontSize="11" fontWeight="800" fill="#1a7f9a">65W</text>
  </g>
);

const Ssd = ({ c = "#155c86" }) => (
  <g>
    <ellipse cx="60" cy="88" rx="38" ry="4" fill="#000" opacity=".08" />
    <g transform="rotate(-10 60 55)">
      <rect x="26" y="32" width="68" height="46" rx="8" fill={c} />
      <rect x="32" y="38" width="56" height="34" rx="5" fill="#fff" opacity=".12" />
      <text x="60" y="60" textAnchor="middle" fontSize="12" fontWeight="800" fill="#fff">1TB</text>
      <circle cx="84" cy="70" r="2" fill="#7fe3a0" />
    </g>
  </g>
);

const Webcam = () => (
  <g>
    <ellipse cx="60" cy="92" rx="26" ry="4" fill="#000" opacity=".08" />
    <rect x="28" y="30" width="64" height="30" rx="15" fill="#1f2a31" />
    <circle cx="60" cy="45" r="11" fill="#33424b" />
    <circle cx="60" cy="45" r="6" fill="#2a86b8" />
    <circle cx="58" cy="43" r="2" fill="#fff" opacity=".7" />
    <path d="M60 60v18M44 88h32" stroke="#1f2a31" strokeWidth="5" strokeLinecap="round" />
  </g>
);

const Lamp = ({ c = "#b3561a" }) => (
  <g>
    <ellipse cx="60" cy="92" rx="30" ry="4" fill="#000" opacity=".08" />
    <rect x="34" y="80" width="52" height="10" rx="5" fill="#2b3a42" />
    <path d="M44 80l12-34 20-10" stroke="#2b3a42" strokeWidth="4" strokeLinecap="round" fill="none" />
    <path d="M70 22l24 8-8 18-24-8z" fill={c} />
    <path d="M74 44l10 14" stroke="#ffd36b" strokeWidth="8" strokeLinecap="round" opacity=".45" />
  </g>
);

const Plates = ({ c = "#b85a1c" }) => (
  <g>
    <ellipse cx="60" cy="90" rx="42" ry="5" fill="#000" opacity=".08" />
    {[0, 1, 2].map((i) => (
      <g key={i}>
        <ellipse cx="60" cy={78 - i * 10} rx="40" ry="11" fill="#fff" stroke="#dfe5ea" strokeWidth="2" />
        <ellipse cx="60" cy={78 - i * 10} rx="30" ry="7" fill="none" stroke={c} strokeWidth="2" opacity=".7" />
      </g>
    ))}
    <ellipse cx="60" cy="58" rx="16" ry="4" fill={c} opacity=".15" />
  </g>
);

const Flask = ({ c = "#a8561f" }) => (
  <g>
    <ellipse cx="60" cy="93" rx="18" ry="3.5" fill="#000" opacity=".08" />
    <rect x="48" y="8" width="24" height="14" rx="4" fill="#2b3a42" />
    <rect x="44" y="22" width="32" height="70" rx="10" fill="#c9d3da" />
    <rect x="44" y="40" width="32" height="30" fill={c} />
    <rect x="50" y="26" width="5" height="60" rx="2.5" fill="#fff" opacity=".5" />
  </g>
);

const Towels = ({ c = "#c07a45" }) => (
  <g>
    <ellipse cx="60" cy="90" rx="40" ry="4" fill="#000" opacity=".08" />
    {["#e7d5c3", c, "#f0e6da", "#8bb0c9"].map((col, i) => (
      <g key={i}>
        <rect x="22" y={70 - i * 14} width="76" height="16" rx="7" fill={col} />
        <path d={`M24 ${76 - i * 14}h72`} stroke="#fff" strokeOpacity=".35" />
      </g>
    ))}
  </g>
);

const Board = () => (
  <g>
    <ellipse cx="60" cy="90" rx="38" ry="4" fill="#000" opacity=".08" />
    <g transform="rotate(-14 60 55)">
      <rect x="24" y="22" width="60" height="64" rx="10" fill="#d9a766" />
      <rect x="40" y="28" width="68" height="56" rx="10" fill="#c38c49" />
      <circle cx="96" cy="40" r="5" fill="#fff" />
      {[0, 1, 2, 3].map((i) => <path key={i} d={`M${50 + i * 12} 34v44`} stroke="#a8743a" strokeOpacity=".5" />)}
    </g>
  </g>
);

const Basket = ({ c = "#c9a36b" }) => (
  <g>
    <ellipse cx="60" cy="92" rx="36" ry="4" fill="#000" opacity=".08" />
    <path d="M22 42h76l-8 46H30z" fill={c} />
    {[0, 1, 2, 3].map((i) => <path key={i} d={`M24 ${52 + i * 10}h72`} stroke="#8c6a3a" strokeOpacity=".45" strokeWidth="3" />)}
    <rect x="18" y="36" width="84" height="10" rx="5" fill="#a9844d" />
  </g>
);

const Tomato = ({ c = "#e03b2f" }) => (
  <g>
    <ellipse cx="60" cy="91" rx="32" ry="4" fill="#000" opacity=".08" />
    <path d="M60 32c20 0 32 12 32 28S80 88 60 88 28 76 28 60s12-28 32-28z" fill={c} />
    <path d="M40 48c3-6 9-9 14-9-6 4-9 9-10 15z" fill="#fff" opacity=".3" />
    <path d="M60 36l-9-8 7 2 2-8 2 8 7-2-9 8 10 2-10 1-3 5-3-5-10-1z" fill="#3f8e2e" />
  </g>
);

const Onion = ({ c = "#b2566e" }) => (
  <g>
    <ellipse cx="60" cy="91" rx="28" ry="4" fill="#000" opacity=".08" />
    <path d="M60 24c4 10 30 22 30 42 0 14-13 22-30 22S30 80 30 66c0-20 26-32 30-42z" fill={c} />
    <path d="M60 30c-6 14-14 26-14 40M60 30c6 14 14 26 14 40M60 30v56" stroke="#fff" strokeOpacity=".28" strokeWidth="2" fill="none" />
    <path d="M57 24c0-6 1-10 3-14 2 4 3 8 3 14z" fill="#8aa35a" />
  </g>
);

const Leafy = ({ c = "#2f8a3c" }) => (
  <g>
    <ellipse cx="60" cy="92" rx="30" ry="4" fill="#000" opacity=".08" />
    {[[-34, 0], [-14, -6], [8, -8], [28, -2]].map(([r, dy], i) => (
      <g key={i} transform={`rotate(${r} 60 88)`}>
        <path d={`M60 88C44 70 42 ${40 + dy} 60 ${22 + dy}c18 ${18 - dy} 16 48 0 66z`} fill={c} opacity={0.75 + i * 0.07} />
        <path d={`M60 86V${30 + dy}`} stroke="#d8f0c6" strokeOpacity=".7" strokeWidth="1.6" />
      </g>
    ))}
    <rect x="52" y="82" width="16" height="8" rx="3" fill="#c9a36b" />
  </g>
);

/* soap carton: flat box, colour band, leaf mark, label */
const Soap = ({ c = "#2e7d4f", t = "" }) => (
  <g>
    <ellipse cx="60" cy="88" rx="40" ry="4" fill="#000" opacity=".08" />
    <path d="M18 40l14-12h70l-14 12z" fill={c} opacity=".75" />
    <path d="M88 40l14-12v38l-14 14z" fill={c} opacity=".55" />
    <rect x="18" y="40" width="70" height="40" rx="3" fill={c} />
    <rect x="18" y="58" width="70" height="10" fill="#fff" opacity=".22" />
    <path d="M30 56c0-9 6-14 15-14 0 9-6 14-15 14z" fill="#fff" opacity=".85" />
    <path d="M30 56l10-9" stroke={c} strokeWidth="1.6" strokeLinecap="round" />
    <text x="66" y="56" textAnchor="middle" fontSize={t.length > 7 ? 8.5 : t.length > 5 ? 10 : 12} fontWeight="800" fill="#fff">{t}</text>
    <path d="M50 74h30" stroke="#fff" strokeOpacity=".55" strokeWidth="2.4" strokeLinecap="round" />
  </g>
);

/* unwrapped oval bar with a pressed mark */
const SoapBar = ({ c = "#d99a5b", t = "" }) => (
  <g>
    <ellipse cx="60" cy="86" rx="38" ry="4.5" fill="#000" opacity=".1" />
    <ellipse cx="60" cy="62" rx="40" ry="22" fill={c} />
    <ellipse cx="60" cy="56" rx="40" ry="22" fill={c} />
    <ellipse cx="60" cy="56" rx="40" ry="22" fill="#fff" opacity=".14" />
    <ellipse cx="60" cy="56" rx="28" ry="13" fill="none" stroke="#000" strokeOpacity=".14" strokeWidth="2" />
    <text x="60" y="60" textAnchor="middle" fontSize="10" fontWeight="800" fill="#000" fillOpacity=".28">{t}</text>
    <path d="M34 46c6-5 14-7 22-7" stroke="#fff" strokeOpacity=".5" strokeWidth="3" strokeLinecap="round" fill="none" />
  </g>
);


/* ---- computer parts ---- */
const Cpu = ({ c = "#1f6f8b", t = "" }) => (
  <g>
    <ellipse cx="60" cy="90" rx="30" ry="4" fill="#000" opacity=".08" />
    {[0, 1, 2, 3, 4, 5].map((i) => (
      <g key={i}>
        <rect x={34 + i * 9} y="22" width="4" height="8" rx="1.5" fill="#9aa6ae" />
        <rect x={34 + i * 9} y="70" width="4" height="8" rx="1.5" fill="#9aa6ae" />
        <rect x="26" y={34 + i * 9} width="8" height="4" rx="1.5" fill="#9aa6ae" />
        <rect x="86" y={34 + i * 9} width="8" height="4" rx="1.5" fill="#9aa6ae" />
      </g>
    ))}
    <rect x="32" y="28" width="56" height="44" rx="6" fill={c} />
    <rect x="40" y="35" width="40" height="30" rx="4" fill="#fff" opacity=".14" />
    <path d="M38 34h6v6h-6z" fill="#fff" opacity=".35" />
    <text x="60" y="55" textAnchor="middle" fontSize="12" fontWeight="800" fill="#fff">{t}</text>
  </g>
);

const Gpu = ({ c = "#1c2b3a", t = "" }) => (
  <g>
    <ellipse cx="60" cy="88" rx="40" ry="4" fill="#000" opacity=".08" />
    <rect x="14" y="66" width="86" height="6" rx="2" fill="#7f8a92" />
    <rect x="14" y="34" width="92" height="34" rx="5" fill={c} />
    <circle cx="40" cy="51" r="12" fill="#0d1620" />
    <circle cx="74" cy="51" r="12" fill="#0d1620" />
    {[40, 74].map((x) => [0, 1, 2, 3, 4].map((i) => (
      <path key={x + "-" + i} d={"M" + x + " 42 A9 9 0 0 1 " + (x + 7) + " 56"} transform={"rotate(" + i * 72 + " " + x + " 51)"}
        stroke="#4d6070" strokeWidth="2.5" fill="none" strokeLinecap="round" />
    )))}
    <circle cx="40" cy="51" r="3" fill="#7f8a92" />
    <circle cx="74" cy="51" r="3" fill="#7f8a92" />
    <rect x="100" y="30" width="6" height="42" rx="2" fill="#9aa6ae" />
    <text x="60" y="30" textAnchor="middle" fontSize="10" fontWeight="800" fill={c}>{t}</text>
  </g>
);

const Ram = ({ c = "#0f5f4a", t = "" }) => (
  <g>
    <ellipse cx="60" cy="90" rx="34" ry="4" fill="#000" opacity=".08" />
    <path d="M18 24h84v34a6 6 0 0 1-3 5l-8 5H29l-8-5a6 6 0 0 1-3-5z" fill={c} />
    <path d="M22 18h76l4 6H18z" fill={c} opacity=".75" />
    {[0, 1, 2, 3, 4, 5, 6].map((i) => <rect key={i} x={26 + i * 10} y="30" width="7" height="18" rx="2" fill="#0b3b2e" opacity=".55" />)}
    <rect x="20" y="68" width="80" height="6" rx="1" fill="#c9a227" />
    <rect x="54" y="68" width="5" height="6" fill="#f4f6f8" />
    <text x="60" y="62" textAnchor="middle" fontSize="10" fontWeight="800" fill="#fff" fillOpacity=".8">{t}</text>
  </g>
);

const Motherboard = ({ c = "#14532d", t = "" }) => (
  <g>
    <ellipse cx="60" cy="92" rx="38" ry="4" fill="#000" opacity=".08" />
    <rect x="18" y="14" width="84" height="74" rx="5" fill={c} />
    {[24, 96].map((x) => [20, 82].map((y) => <circle key={x + "-" + y} cx={x} cy={y} r="2.5" fill="#0b3b2e" />))}
    <rect x="28" y="24" width="26" height="26" rx="3" fill="#8fa3ae" />
    <rect x="33" y="29" width="16" height="16" rx="2" fill="#5f7480" />
    <rect x="64" y="22" width="6" height="30" rx="2" fill="#1f2a31" opacity=".6" />
    <rect x="74" y="22" width="6" height="30" rx="2" fill="#1f2a31" opacity=".6" />
    <rect x="84" y="22" width="6" height="30" rx="2" fill="#1f2a31" opacity=".6" />
    <rect x="28" y="60" width="62" height="7" rx="2" fill="#8a5a1e" />
    <rect x="28" y="72" width="44" height="7" rx="2" fill="#8a5a1e" />
    <path d="M22 54h70" stroke="#fff" strokeOpacity=".18" strokeDasharray="4 4" />
    <text x="60" y="12" textAnchor="middle" fontSize="10" fontWeight="800" fill={c}>{t}</text>
  </g>
);

const Keyboard = ({ c = "#26323a", t = "" }) => (
  <g>
    <ellipse cx="60" cy="86" rx="42" ry="4" fill="#000" opacity=".08" />
    <rect x="12" y="34" width="96" height="46" rx="7" fill={c} />
    <rect x="16" y="38" width="88" height="34" rx="4" fill="#0f181e" opacity=".45" />
    {[0, 1, 2].map((r) => [0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => (
      <rect key={r + "-" + i} x={20 + i * 8.2} y={42 + r * 9} width="6" height="6" rx="1.5" fill="#fff" opacity={r === 2 && i > 6 ? ".5" : ".22"} />
    )))}
    <rect x="42" y="69" width="36" height="6" rx="1.5" fill="#fff" opacity=".22" />
    <text x="60" y="30" textAnchor="middle" fontSize="10" fontWeight="800" fill={c}>{t}</text>
  </g>
);

const Mouse = ({ c = "#2b3a42", t = "" }) => (
  <g>
    <ellipse cx="60" cy="90" rx="24" ry="4" fill="#000" opacity=".08" />
    <path d="M60 16c16 0 26 12 26 28v22c0 12-11 20-26 20s-26-8-26-20V44c0-16 10-28 26-28z" fill={c} />
    <path d="M60 16c-16 0-26 12-26 28v6h26z" fill="#fff" opacity=".16" />
    <path d="M60 18v32" stroke="#fff" strokeOpacity=".3" strokeWidth="2" />
    <rect x="56" y="26" width="8" height="14" rx="4" fill="#5fa8d3" />
    <text x="60" y="72" textAnchor="middle" fontSize="10" fontWeight="800" fill="#fff" fillOpacity=".6">{t}</text>
  </g>
);

const Monitor = ({ c = "#1b2a35", t = "" }) => (
  <g>
    <ellipse cx="60" cy="92" rx="30" ry="4" fill="#000" opacity=".08" />
    <rect x="10" y="14" width="100" height="58" rx="6" fill={c} />
    <rect x="15" y="19" width="90" height="46" rx="3" fill="#2f7fb8" />
    <path d="M15 19h90v46z" fill="#fff" opacity=".10" />
    <rect x="52" y="72" width="16" height="10" fill={c} />
    <rect x="38" y="82" width="44" height="6" rx="3" fill={c} />
    <text x="60" y="48" textAnchor="middle" fontSize="12" fontWeight="800" fill="#fff" fillOpacity=".85">{t}</text>
  </g>
);

const Psu = ({ c = "#37424a", t = "" }) => (
  <g>
    <ellipse cx="60" cy="88" rx="34" ry="4" fill="#000" opacity=".08" />
    <rect x="18" y="26" width="84" height="56" rx="6" fill={c} />
    <circle cx="54" cy="54" r="21" fill="#1b2228" />
    {[0, 1, 2, 3, 4, 5, 6].map((i) => (
      <path key={i} d="M54 35a19 19 0 0 1 13 6" transform={"rotate(" + i * 51 + " 54 54)"} stroke="#6b7a85" strokeWidth="3" fill="none" strokeLinecap="round" />
    ))}
    <circle cx="54" cy="54" r="5" fill="#8c9aa4" />
    <rect x="84" y="36" width="12" height="10" rx="2" fill="#1b2228" />
    <rect x="84" y="52" width="12" height="16" rx="2" fill="#1b2228" />
    <text x="60" y="78" textAnchor="middle" fontSize="10" fontWeight="800" fill="#fff" fillOpacity=".55">{t}</text>
  </g>
);

const Cooler = ({ c = "#4a5a66", t = "" }) => (
  <g>
    <ellipse cx="60" cy="90" rx="30" ry="4" fill="#000" opacity=".08" />
    <rect x="28" y="44" width="64" height="40" rx="4" fill="#c3ccd2" />
    {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => <rect key={i} x={31 + i * 7.6} y="46" width="3.4" height="36" fill="#96a3ab" />)}
    <circle cx="60" cy="34" r="22" fill={c} />
    <circle cx="60" cy="34" r="18" fill="#1b2228" opacity=".75" />
    {[0, 1, 2, 3, 4, 5, 6].map((i) => (
      <path key={i} d="M60 18a16 16 0 0 1 11 5" transform={"rotate(" + i * 51 + " 60 34)"} stroke="#8ea2ae" strokeWidth="3" fill="none" strokeLinecap="round" />
    ))}
    <circle cx="60" cy="34" r="5" fill="#c3ccd2" />
    <text x="60" y="97" textAnchor="middle" fontSize="10" fontWeight="800" fill={c}>{t}</text>
  </g>
);

const Cabinet = ({ c = "#222b33", t = "" }) => (
  <g>
    <ellipse cx="60" cy="92" rx="26" ry="4" fill="#000" opacity=".08" />
    <rect x="34" y="8" width="52" height="82" rx="6" fill={c} />
    <rect x="39" y="14" width="26" height="70" rx="3" fill="#0e151b" />
    {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => <circle key={"a" + i} cx="46" cy={22 + i * 8} r="1.6" fill="#4c5a64" />)}
    {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => <circle key={"b" + i} cx="56" cy={22 + i * 8} r="1.6" fill="#4c5a64" />)}
    <rect x="70" y="16" width="12" height="52" rx="3" fill="#5fa8d3" opacity=".25" />
    <circle cx="76" cy="78" r="3" fill="#5fe0a0" />
    <text x="60" y="99" textAnchor="middle" fontSize="10" fontWeight="800" fill={c}>{t}</text>
  </g>
);

const Router = ({ c = "#1f3b4d", t = "" }) => (
  <g>
    <ellipse cx="60" cy="88" rx="38" ry="4" fill="#000" opacity=".08" />
    <path d="M26 22l6 20M94 22l-6 20" stroke="#7f8a92" strokeWidth="4" strokeLinecap="round" />
    <circle cx="26" cy="20" r="3" fill="#7f8a92" />
    <circle cx="94" cy="20" r="3" fill="#7f8a92" />
    <rect x="16" y="44" width="88" height="30" rx="8" fill={c} />
    <rect x="16" y="44" width="88" height="10" rx="8" fill="#fff" opacity=".10" />
    {[0, 1, 2, 3].map((i) => <circle key={i} cx={34 + i * 17} cy="64" r="3" fill={i === 0 ? "#5fe0a0" : "#5fa8d3"} opacity={i === 0 ? 1 : ".7"} />)}
    <text x="60" y="84" textAnchor="middle" fontSize="10" fontWeight="800" fill={c}>{t}</text>
  </g>
);

const Laptop = ({ c = "#37424a", t = "" }) => (
  <g>
    <ellipse cx="60" cy="88" rx="42" ry="4" fill="#000" opacity=".08" />
    <path d="M28 18h64a4 4 0 0 1 4 4v42H24V22a4 4 0 0 1 4-4z" fill={c} />
    <rect x="29" y="23" width="62" height="36" rx="2" fill="#2f7fb8" />
    <path d="M29 23h62v36z" fill="#fff" opacity=".10" />
    <path d="M14 64h92l6 12a3 3 0 0 1-3 4H11a3 3 0 0 1-3-4z" fill="#c3ccd2" />
    <rect x="50" y="70" width="20" height="4" rx="2" fill="#8ea2ae" />
    <text x="60" y="46" textAnchor="middle" fontSize="11" fontWeight="800" fill="#fff" fillOpacity=".85">{t}</text>
  </g>
);

const Cable = ({ c = "#2b3a42", t = "" }) => (
  <g>
    <ellipse cx="60" cy="90" rx="34" ry="4" fill="#000" opacity=".08" />
    <path d="M26 30c22 0 22 18 0 18s-22 18 0 18h40" stroke={c} strokeWidth="6" fill="none" strokeLinecap="round" />
    <rect x="18" y="22" width="14" height="14" rx="3" fill="#9aa6ae" />
    <rect x="21" y="18" width="8" height="5" rx="1.5" fill="#7f8a92" />
    <rect x="64" y="58" width="22" height="14" rx="3" fill="#9aa6ae" />
    <rect x="86" y="62" width="6" height="6" rx="1.5" fill="#7f8a92" />
    <text x="60" y="40" textAnchor="middle" fontSize="11" fontWeight="800" fill={c}>{t}</text>
  </g>
);

const Adapter = ({ c = "#2f7fb8", t = "" }) => (
  <g>
    <ellipse cx="60" cy="88" rx="28" ry="4" fill="#000" opacity=".08" />
    <rect x="40" y="18" width="16" height="10" rx="4" fill="#9aa6ae" />
    <path d="M48 28v10" stroke="#7f8a92" strokeWidth="5" strokeLinecap="round" />
    <rect x="30" y="38" width="60" height="30" rx="8" fill={c} />
    <rect x="34" y="42" width="52" height="10" rx="3" fill="#fff" opacity=".18" />
    <rect x="88" y="46" width="10" height="14" rx="2" fill="#9aa6ae" />
    <circle cx="44" cy="61" r="2.5" fill="#5fe0a0" />
    <text x="66" y="63" textAnchor="middle" fontSize="10" fontWeight="800" fill="#fff" fillOpacity=".8">{t}</text>
  </g>
);
const ART = { Cpu, Gpu, Ram, Motherboard, Keyboard, Mouse, Monitor, Psu, Cooler, Cabinet, Router, Laptop, Cable, Adapter, Soap, SoapBar, Tomato, Onion, Leafy, Pack, Bottle, Box, Jar, Bar, Banana, Apple, Pomegranate, Orange, Grapes, Headphones, Speaker, Charger, Ssd, Webcam, Lamp, Plates, Flask, Towels, Board, Basket };

export default function ProductArt({ art = "Pack", color, label }) {
  const A = ART[art] || Pack;
  return (
    <svg viewBox="0 0 120 100" role="img" aria-hidden="true" className="hm-art">
      <A c={color} t={label} />
    </svg>
  );
}
