/* The 369 Mart logo, one picture for every place that shows it. The clear
   (transparent) copy sits straight on a white header; on a dark background it
   goes on a white chip (`.brand-chip`), because "MART" is navy and would vanish.
   Its size comes from the CSS of the place it sits in - set a height there. */
export default function Logo({ className = "" }) {
  /* /369mart/logo is the logo uploaded in the console (Settings > Store), the
     same one the WhatsApp and payment pages show; with none uploaded it hands
     back the clear copy that ships with the site. */
  return <img className={"brand-logo " + className} src="/369mart/logo" alt="369 Mart" width="332" height="176" />;
}
