import * as React from 'react';
import { ChevronDown, Globe2 } from 'lucide-react';
import * as RPNInput from 'react-phone-number-input';
import flags from 'react-phone-number-input/flags';

import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

type PhoneInputProps = Omit<
  React.ComponentProps<'input'>,
  'onChange' | 'value' | 'ref'
> &
  Omit<RPNInput.Props<typeof RPNInput.default>, 'onChange'> & {
    onChange?: (value: RPNInput.Value | '') => void;
    inputClassName?: string;
    countrySelectClassName?: string;
  };

const PhoneInput = React.forwardRef<
  React.ElementRef<typeof RPNInput.default>,
  PhoneInputProps
>(
  (
    {
      className,
      countrySelectClassName,
      inputClassName,
      numberInputProps,
      countrySelectProps,
      onChange,
      value,
      ...props
    },
    ref,
  ) => (
    <RPNInput.default
      ref={ref}
      className={cn('flex w-full', className)}
      flagComponent={FlagComponent}
      countrySelectComponent={CountrySelect}
      inputComponent={InputComponent}
      smartCaret={false}
      value={value || undefined}
      numberInputProps={{
        ...(numberInputProps as React.ComponentProps<'input'> | undefined),
        className: cn(
          (numberInputProps as React.ComponentProps<'input'> | undefined)?.className,
          inputClassName,
        ),
      }}
      countrySelectProps={{
        ...(countrySelectProps as CountrySelectExtraProps | undefined),
        className: cn(
          (countrySelectProps as CountrySelectExtraProps | undefined)?.className,
          countrySelectClassName,
        ),
      }}
      onChange={(nextValue) => onChange?.(nextValue ?? '')}
      {...props}
    />
  ),
);
PhoneInput.displayName = 'PhoneInput';

const InputComponent = React.forwardRef<
  HTMLInputElement,
  React.ComponentProps<'input'>
>(({ className, ...props }, ref) => (
  <Input
    ref={ref}
    className={cn(className, 'rounded-s-none')}
    {...props}
  />
));
InputComponent.displayName = 'PhoneInputNumber';

type CountryEntry = {
  label: string;
  value?: RPNInput.Country;
};

type CountrySelectExtraProps = {
  className?: string;
  'aria-label'?: string;
};

type CountrySelectProps = CountrySelectExtraProps & {
  disabled?: boolean;
  value?: RPNInput.Country;
  options: CountryEntry[];
  onChange: (country?: RPNInput.Country) => void;
};

function CountrySelect({
  className,
  disabled,
  value: selectedCountry,
  options,
  onChange,
  'aria-label': ariaLabel = 'Country calling code',
}: CountrySelectProps) {
  const selectedOption = options.find(({ value }) => value === selectedCountry);

  return (
    <div
      className={cn(
        'relative flex min-w-24 shrink-0 items-center gap-2 rounded-s-xl border border-r-0 border-border bg-card px-3 text-sm',
        'focus-within:z-10 focus-within:border-cobalt focus-within:ring-2 focus-within:ring-cobalt/30',
        disabled && 'cursor-not-allowed opacity-50',
        className,
      )}
    >
      <FlagComponent country={selectedCountry} countryName={selectedOption?.label ?? 'International'} />
      <span className="tabular-nums text-muted-foreground" aria-hidden="true">
        {selectedCountry ? `+${RPNInput.getCountryCallingCode(selectedCountry)}` : '+'}
      </span>
      <ChevronDown className="size-3.5 text-muted-foreground" aria-hidden="true" />
      <select
        aria-label={ariaLabel}
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
        disabled={disabled}
        value={selectedCountry ?? ''}
        onChange={(event) => {
          const country = event.target.value || undefined;
          onChange(country as RPNInput.Country | undefined);
        }}
      >
        {options.map(({ value, label }) => (
          <option key={value ?? 'international'} value={value ?? ''}>
            {value ? `${label} +${RPNInput.getCountryCallingCode(value)}` : label}
          </option>
        ))}
      </select>
    </div>
  );
}

function FlagComponent({
  country,
  countryName,
}: {
  country?: RPNInput.Country;
  countryName: string;
}) {
  const Flag = country ? flags[country] : undefined;

  return (
    <span className="flex h-4 w-6 shrink-0 items-center justify-center overflow-hidden rounded-sm bg-muted">
      {Flag ? (
        <Flag title={countryName} />
      ) : (
        <Globe2 className="size-4 text-muted-foreground" aria-hidden="true" />
      )}
    </span>
  );
}

export { PhoneInput };
