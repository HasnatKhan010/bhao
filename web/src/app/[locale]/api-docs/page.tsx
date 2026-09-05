import { API_BASE } from "@/lib/api";

export default function ApiDocsPage() {
  return (
    <div className="h-[calc(100vh-8rem)] w-full">
      <iframe
        src={`${API_BASE}/api-docs`}
        title="Swagger UI"
        className="h-full w-full rounded-xl border border-slate-200 bg-white"
      />
    </div>
  );
}
