export default function ApiDocsPage() {
  return (
    <div className="h-[calc(100vh-8rem)] w-full">
      <iframe
        src="/api-docs"
        title="Swagger UI"
        className="h-full w-full rounded-xl border border-slate-200 bg-white"
      />
    </div>
  );
}
