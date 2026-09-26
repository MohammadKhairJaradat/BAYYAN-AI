/* ============================================================
   BAYYAN — Button. Variants: primary / ghost / clay / quiet.
   Sizes: lg / sm (default base). Optional leading/trailing icon.
   ============================================================ */
import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";
import Icon from "./Icon";
import type { IconName } from "./IconPaths";

type Variant = "primary" | "ghost" | "clay" | "quiet";
type Size = "lg" | "sm";

interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  children?: ReactNode;
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  iconRight?: IconName;
  type?: "button" | "submit" | "reset";
  style?: CSSProperties;
}

export default function Button({
  children,
  variant = "primary",
  size,
  icon,
  iconRight,
  type = "button",
  className,
  style,
  ...rest
}: ButtonProps) {
  const cls = `btn btn-${variant}` + (size ? ` btn-${size}` : "") + (className ? ` ${className}` : "");
  return (
    <button type={type} className={cls} style={style} {...rest}>
      {icon && <Icon name={icon} size={18} />}
      {children}
      {iconRight && <Icon name={iconRight} size={18} className={iconRight === "arrow" ? "i-arrow" : undefined} />}
    </button>
  );
}
