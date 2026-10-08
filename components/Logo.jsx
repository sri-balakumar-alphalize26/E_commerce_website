/* The 369 Mart logo, one picture for every place that shows it. The clear
   (transparent) copy sits straight on a white header; on a dark background it
   goes on a white chip (`.brand-chip`), because "MART" is navy and would vanish.
   Its size comes from the CSS of the place it sits in - set a height there. */
export default function Logo({ className = "" }) {
  return <img className={"brand-logo " + className} src="/brand/369mart-logo-clear.png" alt="369 Mart" width="332" height="176" />;
}
