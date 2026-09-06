import ItemClient from "./ItemClient";

// the catalog's stable code space; the real basket grows via new codes at ingest,
// so a rebundled release picks up new pages. The deployed web stays dynamic.
const ITEM_CODES = Array.from({ length: 57 }, (_, i) => String(i + 1).padStart(3, "0"));

export function generateStaticParams() {
  return ["en", "ur"].flatMap((locale) =>
    ITEM_CODES.map((code) => ({ locale, code }))
  );
}

export default function ItemPage() {
  return <ItemClient />;
}
