interface MaskedValueProps {
  className?: string;
}

export default function MaskedValue({ className }: MaskedValueProps) {
  return (
    <span
      className={className}
      aria-label="masked value"
      title="This field is restricted"
    >
      ••••••
    </span>
  );
}
