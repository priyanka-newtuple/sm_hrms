import WorkflowsListWidget from './WorkflowsListWidget';

export default function WorkflowsPage() {
  return (
    <div className="flex h-[calc(100svh-6rem)] min-w-0 flex-col overflow-hidden lg:h-[calc(100svh-8rem)]">
      <WorkflowsListWidget />
    </div>
  );
}
