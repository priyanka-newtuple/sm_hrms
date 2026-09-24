export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-muted/50 px-4 py-10 sm:py-16">
      <div className="mx-auto w-full max-w-xl">
        <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
          {children}
        </div>
        {/* Todo: make flowtuple dynamic with skins */}
        <p className="mt-4 text-center text-xs text-muted-foreground">Powered by FlowTuple</p>
      </div>
    </div>
  );
}
