import { cva } from "class-variance-authority";

export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[11px] text-sm font-semibold transition-colors focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--green)] text-[#FFFCF5] hover:bg-[var(--green-deep)]",
        outline:
          "border border-[var(--line-strong)] bg-transparent text-[var(--ink)] hover:bg-[var(--paper-2)] hover:border-[var(--green)]",
        secondary:
          "bg-[var(--paper-2)] text-[var(--ink)] hover:bg-[var(--green-tint)]",
        ghost: "text-[var(--ink-soft)] hover:bg-[var(--paper-2)] hover:text-[var(--green)]",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-[10px] px-3",
        lg: "h-11 rounded-[12px] px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);
