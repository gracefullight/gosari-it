import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

const buttonVariants = cva(
  "group/button inline-flex shrink-0 cursor-pointer items-center justify-center rounded-lg border font-semibold whitespace-nowrap transition-all duration-150 outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40 active:not-aria-[haspopup]:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "border-[#1e5f22] bg-[#2e7d32] text-white shadow-sm hover:bg-[#246528] active:bg-[#1b4d1e]",
        outline:
          "border-[#2e7d32]/60 bg-white text-[#1e5f22] shadow-2xs hover:border-[#2e7d32] hover:bg-[#f1f8f2] hover:text-[#1b4d1e] aria-expanded:bg-[#e8f5e9]",
        secondary:
          "border-[#2e7d32]/30 bg-[#e8f5e9] text-[#1b4d1e] shadow-2xs hover:border-[#2e7d32]/60 hover:bg-[#d5ecd7] aria-expanded:bg-[#d5ecd7]",
        ghost:
          "border-transparent bg-transparent text-foreground hover:border-[#dce2dc] hover:bg-[#f1f8f2] hover:text-[#1b4d1e] aria-expanded:bg-[#e8f5e9]",
        destructive:
          "border-red-300 bg-red-50 text-red-700 shadow-2xs hover:border-red-400 hover:bg-red-100 focus-visible:border-destructive/40 focus-visible:ring-destructive/20",
        link: "border-transparent text-[#2e7d32] underline-offset-4 hover:underline",
      },
      size: {
        default:
          "min-h-10 gap-2 px-4 py-2 text-sm in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3",
        xs: "min-h-7 gap-1 rounded-md px-2.5 py-1 text-xs [&_svg:not([class*='size-'])]:size-3",
        sm: "min-h-9 gap-1.5 rounded-lg px-3.5 py-1.5 text-sm",
        lg: "min-h-11 gap-2 rounded-lg px-5 py-2.5 text-base",
        icon: "size-10",
        "icon-xs": "size-7 rounded-md [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-9 rounded-lg",
        "icon-lg": "size-11 rounded-lg",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
