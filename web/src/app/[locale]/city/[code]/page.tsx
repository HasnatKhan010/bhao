import CityClient from "./CityClient";

export function generateStaticParams() {
  const cities = Array.from({ length: 17 }, (_, i) => String(i + 1).padStart(2, "0"));
  return ["en", "ur"].flatMap((locale) =>
    cities.map((code) => ({ locale, code }))
  );
}

export default function CityPage() {
  return <CityClient />;
}
