type RequiredWorkflowsPanelProps = {
  workflows: { name: string; description: string }[];
};

export function RequiredWorkflowsPanel({
  workflows,
}: RequiredWorkflowsPanelProps) {
  return (
    <section className="mb-5 min-w-0 rounded-openci-md border border-openci-border bg-openci-surface p-4 max-[680px]:p-[14px]">
      <h2 className="m-0 text-[15px] font-semibold tracking-[-0.015em]">
        Required workflows
      </h2>
      <p className="mt-[5px] mb-0 text-[13px] text-openci-text-muted">
        These checks cannot be disabled by a feature override.
      </p>
      <ul className="mt-3.5 mb-3.5 grid list-none gap-2 p-0">
        {workflows.map((workflow) => (
          <li
            className="grid gap-1 border-t border-openci-border py-2.5"
            key={workflow.name}
          >
            <strong>{workflow.name}</strong>
            <span className="text-[13px] text-openci-text-muted">
              {workflow.description}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
