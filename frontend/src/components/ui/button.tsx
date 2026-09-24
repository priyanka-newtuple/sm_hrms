import { forwardRef, type ReactNode } from 'react';
import { Button as ButtonPrimitive } from '@base-ui/react/button';
import { Loader2 } from 'lucide-react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'group/button relative inline-flex shrink-0 items-center justify-center rounded-md border border-transparent bg-clip-padding text-xs/relaxed font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 active:scale-[0.97] active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-2 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*=size-])]:size-4',
  {
    variants: {
      variant: {
        default: 'bg-transparent text-inherit hover:bg-transparent',
        primary: 'bg-primary text-primary-foreground hover:bg-primary/80',
        outline:
          'border-border hover:bg-input/50 hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:bg-input/30',
        secondary:
          'bg-secondary text-secondary-foreground hover:bg-secondary/80 aria-expanded:bg-secondary aria-expanded:text-secondary-foreground',
        ghost:
          'hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:hover:bg-muted/50',
        'ghost-action': 'text-muted-foreground hover:bg-primary/10 hover:text-primary',
        'ghost-danger': 'text-muted-foreground hover:bg-destructive/10 hover:text-destructive',
        destructive:
          'bg-destructive/10 text-destructive hover:bg-destructive/20 focus-visible:border-destructive/40 focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:hover:bg-destructive/30 dark:focus-visible:ring-destructive/40',
        danger: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        success: 'bg-success text-success-foreground hover:bg-success/90',
        warning: 'bg-warning text-warning-foreground hover:bg-warning/90',
        'outline-danger': 'border-destructive/30 bg-transparent text-destructive hover:bg-destructive/10',
        'outline-info': 'border-primary/25 bg-transparent text-primary hover:bg-primary/10',
        ai: 'overflow-hidden border-primary/20 bg-[linear-gradient(135deg,var(--color-cobalt)_0%,var(--color-cyan)_50%,var(--color-violet)_100%)] bg-[length:200%_200%] text-white shadow-sm animate-gradient-x hover:shadow-primary/30',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        default:
          'h-7 gap-1 px-2 text-xs/relaxed has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*=size-])]:size-3.5',
        xs: 'h-5 gap-1 rounded-sm px-2 text-[0.625rem] has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*=size-])]:size-2.5',
        sm: 'h-6 gap-1 px-2 text-xs/relaxed has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*=size-])]:size-3',
        md: 'h-9 gap-2 px-4 text-sm has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3',
        lg: 'h-11 gap-2 px-4 text-sm has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3 [&_svg:not([class*=size-])]:size-4',
        icon: 'size-7 [&_svg:not([class*=size-])]:size-3.5',
        'icon-xs': 'size-5 rounded-sm [&_svg:not([class*=size-])]:size-2.5',
        'icon-sm': 'size-6 [&_svg:not([class*=size-])]:size-3',
        'icon-lg': 'size-8 [&_svg:not([class*=size-])]:size-4',
      },
      rounded: {
        default: '',
        lg: 'rounded-lg',
        full: 'rounded-full',
      },
      fullWidth: {
        false: '',
        true: 'w-full',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
      rounded: 'default',
      fullWidth: false,
    },
  },
);

type ButtonVariant = NonNullable<VariantProps<typeof buttonVariants>['variant']>;
type ButtonSize = NonNullable<VariantProps<typeof buttonVariants>['size']>;
type ButtonRounded = Extract<NonNullable<VariantProps<typeof buttonVariants>['rounded']>, 'default' | 'lg' | 'full'>;

type PrimitiveButtonProps = Omit<ButtonPrimitive.Props, 'children'>;

interface ButtonProps extends PrimitiveButtonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  rounded?: ButtonRounded;
  loading?: boolean;
  icon?: ReactNode;
  iconPosition?: 'left' | 'right';
  fullWidth?: boolean;
  glow?: boolean;
  children?: ReactNode;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = 'default',
      size = 'default',
      rounded = 'default',
      loading = false,
      icon,
      iconPosition = 'left',
      fullWidth = false,
      glow = false,
      children,
      disabled,
      ...props
    },
    ref,
  ) => {
    const isDisabled = disabled || loading;

    const renderContent = () => {
      if (loading) {
        return icon ? (
          <>
            <Loader2 className="size-4 animate-spin" />
            {children}
          </>
        ) : (
          <Loader2 className="size-4 animate-spin" />
        );
      }

      return (
        <>
          {icon && iconPosition === 'left' ? <span data-icon="inline-start">{icon}</span> : null}
          {children}
          {icon && iconPosition === 'right' ? <span data-icon="inline-end">{icon}</span> : null}
        </>
      );
    };

    return (
      <ButtonPrimitive
        ref={ref}
        data-slot="button"
        disabled={isDisabled}
        className={cn(buttonVariants({ variant, size, rounded, fullWidth }), glow && 'btn-glow', className)}
        {...props}
      >
        {renderContent()}
      </ButtonPrimitive>
    );
  },
);

Button.displayName = 'Button';

export { Button, buttonVariants };
export default Button;
export type { ButtonProps, ButtonRounded, ButtonSize, ButtonVariant };
