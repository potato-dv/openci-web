import { useId } from "react";
import { Select as SelectPrimitive } from "radix-ui";
import { Check, ChevronDown } from "lucide-react";

export type WorkspaceSelectOption = { value: string; label: string };

type WorkspaceSelectProps = {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  options: WorkspaceSelectOption[];
  className?: string;
  disabled?: boolean;
  compact?: boolean;
  inlineLabel?: boolean;
  portalContainer?: HTMLElement | null;
};

const EMPTY_VALUE = "__collector_empty__";

export function WorkspaceSelect({
  label,
  value,
  onValueChange,
  options,
  className = "",
  disabled,
  compact = false,
  inlineLabel = false,
  portalContainer,
}: WorkspaceSelectProps) {
  const labelId = useId();
  return (
    <div
      className={`${inlineLabel ? "grid w-max grid-cols-[max-content_72px] items-center gap-2" : "grid min-w-0 gap-1.5"} ${className}`}
    >
      <span
        id={labelId}
        className={`text-[11px] font-medium text-[#66758b] ${inlineLabel ? "whitespace-nowrap" : ""}`}
      >
        {label}
      </span>
      <SelectPrimitive.Root
        value={value || EMPTY_VALUE}
        onValueChange={(next) =>
          onValueChange(next === EMPTY_VALUE ? "" : next)
        }
        disabled={disabled}
      >
        <SelectPrimitive.Trigger
          aria-labelledby={labelId}
          className={`inline-flex w-full min-w-0 items-center justify-between gap-2 rounded-lg border border-[#d6e0ed] bg-white px-3 text-left text-[12px] font-medium text-[#283b5a] shadow-[0_1px_2px_rgba(22,43,77,0.03)] transition-colors hover:border-[#aabbd5] focus-visible:border-[#3565c7] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3565c7]/15 data-[state=open]:border-[#3565c7] data-[state=open]:ring-2 data-[state=open]:ring-[#3565c7]/15 disabled:opacity-50 ${compact ? "h-8" : "h-10"}`}
        >
          <SelectPrimitive.Value />
          <SelectPrimitive.Icon asChild>
            <ChevronDown
              className="size-4 shrink-0 text-[#8190a8]"
              aria-hidden="true"
            />
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal container={portalContainer}>
          <SelectPrimitive.Content
            position="popper"
            sideOffset={5}
            className="z-[100] min-w-[var(--radix-select-trigger-width)] max-h-[min(360px,var(--radix-select-content-available-height))] overflow-hidden rounded-lg border border-[#dce5f0] bg-white p-1 shadow-[0_12px_32px_rgba(25,45,79,0.14)]"
          >
            <SelectPrimitive.Viewport>
              {options.map((option) => (
                <SelectPrimitive.Item
                  key={option.value}
                  value={option.value || EMPTY_VALUE}
                  className="relative flex min-h-9 cursor-default select-none items-center rounded-md py-2 pl-3 pr-8 text-[12px] font-medium text-[#354968] outline-none data-[highlighted]:bg-[#eef4ff] data-[highlighted]:text-[#2857b0] data-[state=checked]:text-[#2857b0]"
                >
                  <SelectPrimitive.ItemText>
                    {option.label}
                  </SelectPrimitive.ItemText>
                  <SelectPrimitive.ItemIndicator className="absolute right-2 grid place-items-center">
                    <Check className="size-3.5" aria-hidden="true" />
                  </SelectPrimitive.ItemIndicator>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
    </div>
  );
}
